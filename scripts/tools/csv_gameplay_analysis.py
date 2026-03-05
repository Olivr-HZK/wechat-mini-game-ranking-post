"""
从 CSV 读入一批游戏，按 main.py 的流程做玩法分析（搜索视频 -> 下载 -> 上传 GDrive -> AI 分析），
不落库，将「核心玩法」等写回原 CSV。

用法（在项目根目录）：
    python -m scripts.tools.csv_gameplay_analysis <input.csv> [--limit N] [--no-upload]

CSV 要求：
    - 必须包含列「游戏名称」
    - 可选列「游戏类型」「排名变化」等会传给分析器作为 game_info

输出：
    - 在原 CSV 中新增/覆盖列：核心玩法、基线游戏、创新点（创新点为多行合并为一段）
"""

import os
import sys
import csv
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from modules.video_searcher import VideoSearcher  # noqa: E402
from modules.video_analyzer import VideoAnalyzer  # noqa: E402


# CSV 编码尝试顺序
ENCODINGS = ["utf-8-sig", "utf-8", "gbk", "gb2312"]

# 写回 CSV 时使用的编码
OUTPUT_ENCODING = "utf-8-sig"

# 新增/覆盖的列名
COL_CORE_GAMEPLAY = "核心玩法"
COL_BASELINE_GAME = "基线游戏"
COL_INNOVATION = "创新点"


def read_csv_rows(csv_path: Path, limit: Optional[int] = None) -> Tuple[List[Dict], List[str]]:
    """
    读取 CSV，返回 (行字典列表, 表头列名列表)。
    若 limit 有值则只读前 limit 行（不含表头）。
    """
    for enc in ENCODINGS:
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                rows = []
                for i, row in enumerate(reader):
                    if limit is not None and i >= limit:
                        break
                    rows.append(row)
                return rows, fieldnames
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法用 {ENCODINGS} 解码文件：{csv_path}")


def ensure_columns(fieldnames: List[str]) -> List[str]:
    """确保表头包含 核心玩法、基线游戏、创新点，且不重复。"""
    extra = [COL_CORE_GAMEPLAY, COL_BASELINE_GAME, COL_INNOVATION]
    out = list(fieldnames)
    for col in extra:
        if col not in out:
            out.append(col)
    return out


def write_csv_rows(csv_path: Path, rows: List[Dict], fieldnames: List[str]) -> None:
    """将行写回 CSV。"""
    fieldnames = ensure_columns(fieldnames)
    with open(csv_path, "w", encoding=OUTPUT_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def row_to_game_info(row: Dict) -> Dict:
    """从 CSV 行提取传给分析器的 game_info（仅需要的字段）。"""
    return {
        "游戏名称": (row.get("游戏名称") or "").strip(),
        "游戏类型": (row.get("游戏类型") or "").strip(),
        "排名变化": (row.get("排名变化") or "").strip(),
        "平台": (row.get("平台") or "").strip(),
        "来源": (row.get("来源") or "").strip(),
    }


def get_video_url_for_analysis(
    game_name: str,
    game_type: Optional[str],
    video_searcher: VideoSearcher,
    upload_to_gdrive: bool,
) -> Tuple[Optional[str], Optional[str]]:
    """
    搜索并下载视频，可选上传到 GDrive，返回 (video_url, local_path)。
    video_url 为 None 表示无法得到可用于分析的链接（分析需 GDrive 链接）。
    """
    local_path = video_searcher.search_and_download(
        game_name=game_name,
        game_type=game_type or None,
        max_results=1,
    )
    if not local_path or not os.path.exists(local_path):
        return None, None

    # 分析器需要 Google Drive 链接；若不上传则无法分析
    if not upload_to_gdrive:
        return None, local_path

    try:
        from modules.gdrive_uploader import GoogleDriveUploader
        uploader = GoogleDriveUploader()
        result = uploader.upload_video(local_path, folder_name="Game Videos")
        if result and result.get("public_url"):
            return result["public_url"], local_path
    except Exception as e:
        print(f"  ⚠ 上传 GDrive 失败：{e}")
    return None, local_path


def analyze_and_fill_row(
    row: Dict,
    video_searcher: VideoSearcher,
    video_analyzer: VideoAnalyzer,
    upload_to_gdrive: bool,
) -> None:
    """
    对一行进行：获取视频 URL -> 分析 -> 将核心玩法、基线游戏、创新点写回 row（原地修改）。
    """
    game_name = (row.get("游戏名称") or "").strip()
    if not game_name:
        row[COL_CORE_GAMEPLAY] = ""
        row[COL_BASELINE_GAME] = ""
        row[COL_INNOVATION] = ""
        return

    game_info = row_to_game_info(row)
    game_type = game_info.get("游戏类型") or None

    video_url, _ = get_video_url_for_analysis(
        game_name=game_name,
        game_type=game_type,
        video_searcher=video_searcher,
        upload_to_gdrive=upload_to_gdrive,
    )

    if not video_url or not video_url.startswith("https://drive.google.com"):
        row[COL_CORE_GAMEPLAY] = "无法获取视频或未上传至 GDrive，跳过分析"
        row[COL_BASELINE_GAME] = ""
        row[COL_INNOVATION] = ""
        return

    analysis = video_analyzer.analyze_video(
        video_path=None,
        game_name=game_name,
        game_info=game_info,
        video_url=video_url,
        force_refresh=True,
    )

    if not analysis:
        row[COL_CORE_GAMEPLAY] = "分析失败"
        row[COL_BASELINE_GAME] = ""
        row[COL_INNOVATION] = ""
        return

    ad = analysis.get("analysis_data") or {}
    if isinstance(ad, dict):
        core = (ad.get("core_gameplay") or "").strip()
        baseline = (ad.get("baseline_game") or "").strip()
        innovations = ad.get("innovation_points") or []
        if isinstance(innovations, list):
            innovation_text = "\n".join(str(x).strip() for x in innovations if x)
        else:
            innovation_text = str(innovations).strip()
    else:
        core = (analysis.get("analysis") or "").strip()[:500]
        baseline = ""
        innovation_text = ""

    row[COL_CORE_GAMEPLAY] = core or ""
    row[COL_BASELINE_GAME] = baseline or ""
    row[COL_INNOVATION] = innovation_text or ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 CSV 读入游戏列表，做玩法分析并写回原 CSV（不落库）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "csv_path",
        type=Path,
        help="输入 CSV 路径（含「游戏名称」列）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理前 N 行（不含表头），不指定则处理全部",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="不上传视频到 GDrive（仍会搜索下载，但无法做 AI 分析，核心玩法将写“无法获取视频或未上传至 GDrive”）",
    )
    args = parser.parse_args()

    csv_path = args.csv_path
    if not csv_path.is_absolute():
        csv_path = (Path.cwd() / csv_path).resolve()
    if not csv_path.exists():
        print(f"错误：文件不存在 {csv_path}")
        sys.exit(1)

    rows, fieldnames = read_csv_rows(csv_path, limit=args.limit)
    if not rows:
        print("CSV 无数据行，退出")
        sys.exit(0)

    # 检查是否有「游戏名称」列
    if "游戏名称" not in fieldnames:
        print("错误：CSV 必须包含列「游戏名称」")
        sys.exit(1)

    print(f"已读取 {len(rows)} 行，开始按 main 流程做玩法分析（不落库）...")
    print("  - 使用 VideoSearcher(use_database=False)")
    print("  - 使用 VideoAnalyzer(use_database=False)")
    print(f"  - 上传 GDrive：{'否' if args.no_upload else '是'}")
    print()

    video_searcher = VideoSearcher(use_database=False)
    video_analyzer = VideoAnalyzer(use_database=False)
    upload_to_gdrive = not args.no_upload

    for i, row in enumerate(rows, 1):
        name = (row.get("游戏名称") or "").strip()
        print(f"[{i}/{len(rows)}] {name or '(无游戏名)'}")
        try:
            analyze_and_fill_row(
                row,
                video_searcher=video_searcher,
                video_analyzer=video_analyzer,
                upload_to_gdrive=upload_to_gdrive,
            )
        except Exception as e:
            print(f"  ✗ 处理失败：{e}")
            row[COL_CORE_GAMEPLAY] = f"处理异常：{e}"
            row[COL_BASELINE_GAME] = ""
            row[COL_INNOVATION] = ""

    write_csv_rows(csv_path, rows, fieldnames)
    print()
    print(f"✓ 已将「核心玩法」「基线游戏」「创新点」写回：{csv_path}")


if __name__ == "__main__":
    main()
