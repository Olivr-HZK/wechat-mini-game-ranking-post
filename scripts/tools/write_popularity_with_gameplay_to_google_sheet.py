"""
将“人气榜”目录下的周榜 CSV（微信/抖音/SensorTower 等）
按游戏名补充数据库中的玩法拆解，并写入 Google Sheet。

功能要点：
- 从 config.RANKINGS_CSV_PATH（默认 data/人气榜）下找到所有 CSV
- 每个 CSV 单独写入一个工作表（Sheet），表名来自 CSV 内的“榜单”字段或文件名
- 玩法信息从数据库 games 表中读取（game_name 匹配“游戏名称”列）
- 如果数据库中有 JSON 结构的玩法分析，则拆成 3 个字段：
  - 核心玩法：core_gameplay.mechanism
  - 基线：baseline_and_innovation.base_genre
  - 创新点：baseline_and_innovation.micro_innovations（多条用分号连接）
  若数据库中没有分析结果或非 JSON 结构，则这三个字段置空
- 视频链接：优先 share_url > gdrive_url > original_video_url > video_url

用法示例（项目根目录）：
  python -m scripts.tools.write_popularity_with_gameplay_to_google_sheet
  python -m scripts.tools.write_popularity_with_gameplay_to_google_sheet --sheet-prefix "周榜_"

环境变量（沿用现有写表脚本的配置）：
  GOOGLE_SHEET_ID              目标表格 ID 或 URL
  GOOGLE_SHEETS_CREDENTIALS    Sheets 专用凭证 JSON 路径
  GOOGLE_SHEETS_TOKEN          可选，token 保存路径
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

# 保证可以导入 scripts.tools.write_rankings_to_google_sheet
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.tools import write_rankings_to_google_sheet as base_sheet  # type: ignore
from modules.database import VideoDatabase
from modules.video_analyzer import VideoAnalyzer


def _read_csv_generic(csv_path: Path) -> Tuple[List[str], List[List[str]]]:
    """读取 CSV，返回 (header, rows)。自动尝试多种编码。"""
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312"]
    last_err: Optional[Exception] = None
    for enc in encodings:
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                all_rows = list(reader)
            if not all_rows:
                raise ValueError(f"CSV 为空：{csv_path}")
            header = all_rows[0]
            data = all_rows[1:]
            return header, data
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"无法读取 CSV：{csv_path}，最后错误：{last_err}")


def _best_video_link_from_game(game: Dict[str, Any]) -> str:
    """优先 share_url > gdrive_url > original_video_url > video_url。"""
    for key in ("share_url", "gdrive_url", "original_video_url", "video_url"):
        v = (game.get(key) or "").strip()
        if v:
            return v
    return ""


def _extract_gameplay_tags_from_analysis_text(
    analyzer: VideoAnalyzer, analysis_text: str
) -> Tuple[str, str, str]:
    """
    从 gameplay_analysis 文本中解析 JSON，并抽取 3 个玩法标签：
    - 核心玩法：core_gameplay.mechanism
    - 基线：baseline_and_innovation.base_genre
    - 创新点：baseline_and_innovation.micro_innovations（list -> "；" 连接）
    解析失败时返回空字符串。
    """
    if not analysis_text:
        return "", "", ""

    analysis_data = analyzer._parse_analysis_json(analysis_text)  # type: ignore[attr-defined]
    if not isinstance(analysis_data, dict):
        return "", "", ""

    core = analysis_data.get("core_gameplay") or {}
    baseline = analysis_data.get("baseline_and_innovation") or {}

    core_play = str(core.get("mechanism") or "").strip()
    base_genre = str(baseline.get("base_genre") or "").strip()

    micro_innovations = baseline.get("micro_innovations") or []
    innovations_str = ""
    if isinstance(micro_innovations, list):
        innovations_str = "；".join(str(x).strip() for x in micro_innovations if str(x).strip())
    else:
        innovations_str = str(micro_innovations).strip()

    return core_play, base_genre, innovations_str


def _enrich_rows_with_db_info(
    header: List[str],
    rows: List[List[str]],
    db: VideoDatabase,
    analyzer: VideoAnalyzer,
) -> Tuple[List[str], List[List[str]]]:
    """
    根据“游戏名称”列到数据库中查找玩法 & 视频链接，为每行补充：
    - 核心玩法
    - 基线
    - 创新点
    - 视频链接
    若数据库无记录或无 JSON 玩法分析，则相应字段置空。
    """
    try:
        idx_name = header.index("游戏名称")
    except ValueError:
        # 没有游戏名称列，直接返回原始数据
        print("⚠ CSV 中没有“游戏名称”列，跳过玩法补充")
        return header, rows

    new_header = header + ["核心玩法", "基线", "创新点", "视频链接"]

    enriched_rows: List[List[str]] = []

    for row in rows:
        # 防御：行长度可能小于表头
        if len(row) <= idx_name:
            game_name = ""
        else:
            game_name = (row[idx_name] or "").strip()

        core_play = ""
        base_genre = ""
        innovations_str = ""
        video_link = ""

        if game_name:
            game = db.get_game(game_name) or {}
            if game:
                # 玩法
                analysis_text = (game.get("gameplay_analysis") or "").strip()
                if analysis_text:
                    core_play, base_genre, innovations_str = _extract_gameplay_tags_from_analysis_text(
                        analyzer, analysis_text
                    )

                # 视频链接
                video_link = _best_video_link_from_game(game)

        enriched_row = list(row) + [core_play, base_genre, innovations_str, video_link]
        enriched_rows.append(enriched_row)

    return new_header, enriched_rows


def _guess_sheet_name_from_csv(csv_path: Path, header: List[str], rows: List[List[str]]) -> str:
    """
    从 CSV 内容中猜测一个较友好的 Sheet 名称：
    - 若存在“榜单”列，则取第一行该列的值
    - 否则用文件名（不含扩展名）
    """
    sheet_name = csv_path.stem
    try:
        idx_board = header.index("榜单")
        if rows:
            candidate = (rows[0][idx_board] or "").strip()
            if candidate:
                sheet_name = candidate
    except ValueError:
        # 没有“榜单”列，保持文件名
        pass

    # Google Sheets 的 Sheet 名长度有限，这里简单截断到 80 字符以内
    return sheet_name[:80]


def _write_one_csv_with_gameplay(
    csv_path: Path,
    db: VideoDatabase,
    analyzer: VideoAnalyzer,
    spreadsheet_id: str,
    sheet_name_prefix: str = "",
) -> None:
    """处理单个 CSV：读取 -> 补充玩法 & 链接 -> 写入指定 Sheet。"""
    print(f"\n[*] 处理 CSV：{csv_path}")
    header, rows = _read_csv_generic(csv_path)
    print(f"    行数（含表头）：{len(rows) + 1}")

    new_header, new_rows = _enrich_rows_with_db_info(header, rows, db, analyzer)
    all_rows: List[List[str]] = [new_header] + new_rows

    raw_sheet_name = _guess_sheet_name_from_csv(csv_path, header, rows)
    sheet_name = f"{sheet_name_prefix}{raw_sheet_name}" if sheet_name_prefix else raw_sheet_name
    sheet_name = sheet_name.strip() or "Sheet1"

    print(f"    目标 Sheet 名称：{sheet_name}")

    creds = base_sheet._get_credentials()
    if not creds:
        raise RuntimeError("获取 Google Sheets 凭证失败")

    from googleapiclient.discovery import build  # type: ignore

    service = build("sheets", "v4", credentials=creds)
    base_sheet._get_or_create_sheet(service, spreadsheet_id, sheet_name)
    ok = base_sheet._write_to_sheet(service, spreadsheet_id, sheet_name, all_rows, clear_first=True)
    if not ok:
        raise RuntimeError(f"写入 Sheet 失败：{sheet_name}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="将人气榜 CSV + 数据库玩法拆解写入 Google Sheet（含核心玩法/基线/创新点/视频链接）"
    )
    ap.add_argument(
        "--csv-dir",
        default="",
        help="人气榜 CSV 目录（默认使用 config.RANKINGS_CSV_PATH）",
    )
    ap.add_argument(
        "--sheet-prefix",
        default="",
        help="为每个工作表名称增加前缀（可选，如：周榜_）",
    )
    args = ap.parse_args()

    # 1) 解析 Spreadsheet ID
    raw_id = (config.GOOGLE_SHEET_ID or "").strip()
    if not raw_id:
        print("错误：未配置 GOOGLE_SHEET_ID，请在 .env 中设置")
        return 1
    spreadsheet_id = base_sheet._extract_spreadsheet_id(raw_id)
    print(f"[*] Spreadsheet ID: {spreadsheet_id}")

    # 2) 确定 CSV 目录
    csv_dir_str = (args.csv_dir or "").strip() or config.RANKINGS_CSV_PATH
    csv_dir = Path(csv_dir_str)
    if not csv_dir.exists() or not csv_dir.is_dir():
        print(f"错误：CSV 目录不存在：{csv_dir}")
        return 1

    # 只处理“有异动”的周榜 CSV：文件名中包含 anomalies（例如 *_anomalies.csv）
    csv_files = sorted(csv_dir.glob("*anomalies*.csv"))
    if not csv_files:
        print(f"错误：目录下未找到带 anomalies 后缀的 CSV：{csv_dir}")
        return 1

    print(f"[*] 在目录 {csv_dir} 中找到 {len(csv_files)} 个 CSV 文件")

    # 3) 初始化数据库 & 分析器（仅用于解析 JSON）
    db = VideoDatabase()
    analyzer = VideoAnalyzer(use_database=False)

    # 4) 逐个 CSV 写入各自 Sheet
    for csv_path in csv_files:
        try:
            _write_one_csv_with_gameplay(
                csv_path=csv_path,
                db=db,
                analyzer=analyzer,
                spreadsheet_id=spreadsheet_id,
                sheet_name_prefix=args.sheet_prefix,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ 处理 {csv_path.name} 时出错：{e}")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    print("\n✅ 全部处理完成")
    print(f"   表格链接：{sheet_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

