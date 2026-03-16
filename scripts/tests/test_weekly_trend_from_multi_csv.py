"""
测试脚本：从多 CSV（微信 / 抖音异动 + SensorTower 排名）抽取样本，
跑通完整工作流，并验证四个平台的周报玩法趋势写入数据库。

目标：
- 从 data/人气榜/ 最近一周目录下的三个 CSV：
  - wx_anomalies.csv（微信）
  - dy_anomalies.csv（抖音）
  - sensortower_rankings.csv（SensorTower 排名）
 里各抽取一条记录，组成一个新的测试 CSV：
  - 微信：1 条
  - 抖音：1 条
  - iOS：1 条（SensorTower 中平台为 iOS）
  - Android：1 条（SensorTower 中平台为 Android）

- 使用这个测试 CSV：
  - 创建独立测试数据库（与正式结构一致），路径：data/test_workflow/videos.db
  - 调用 GameAnalysisWorkflow：
    - step0：检查 CSV
    - step1：提取排行榜并写入测试库
    - step2：搜索/获取玩法视频
    - step3：AI 玩法解析（可配置是否强制刷新）
    - step4：生成日报
    - step4b：写入 weekly_report_trends（四个平台各一条）

运行方式（在项目根目录）：

    python scripts/tests/test_weekly_trend_from_multi_csv.py
"""

import os
import sys
import csv
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from main import GameAnalysisWorkflow  # noqa: E402
from modules.database import VideoDatabase  # noqa: E402


def _find_latest_week_dir() -> Path:
    """在 data/人气榜 下找到最近一周的目录。"""
    base_dir = PROJECT_ROOT / "data" / "人气榜"
    if not base_dir.exists():
        raise FileNotFoundError(f"目录不存在：{base_dir}")

    week_dirs = [p for p in base_dir.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError(f"在 {base_dir} 下未找到任何周目录")

    week_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return week_dirs[0]


def _read_csv_first_row(csv_path: Path) -> Dict:
    """读取 CSV 的首条有效数据（跳过表头、空游戏名）。"""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{csv_path}")

    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312"]
    last_err = None
    for enc in encodings:
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("游戏名称") or "").strip()
                    if name:
                        return row
            return {}
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise RuntimeError(f"读取 CSV 失败（编码问题）：{csv_path}，最后错误：{last_err}")


def _pick_sensor_rows_from_rankings(csv_path: Path) -> Dict[str, Dict]:
    """
    从 SensorTower 排名 CSV 中各取一条 iOS / Android 记录。

    返回：
        {"ios": row_dict, "android": row_dict}
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{csv_path}")

    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312"]
    last_err = None
    for enc in encodings:
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                ios_row = None
                android_row = None
                for row in reader:
                    platform = (row.get("平台") or "").lower()
                    if (not ios_row) and ("ios" in platform):
                        ios_row = row
                    if (not android_row) and ("android" in platform):
                        android_row = row
                    if ios_row and android_row:
                        break
                return {"ios": ios_row, "android": android_row}
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise RuntimeError(f"读取 SensorTower 排名 CSV 失败（编码问题）：{csv_path}，最后错误：{last_err}")


def build_test_csv() -> Path:
    """
    从最新一周的人气榜 CSV 中抽取四个平台各 1 条，合成为单一 CSV。

    返回：
        新测试 CSV 的路径
    """
    week_dir = _find_latest_week_dir()
    print(f"使用最近一周目录：{week_dir.name}")

    wx_csv = week_dir / "wx_anomalies.csv"
    dy_csv = week_dir / "dy_anomalies.csv"
    st_rank_csv = week_dir / "sensortower_rankings.csv"

    if not wx_csv.exists():
        raise FileNotFoundError(f"未找到微信 CSV：{wx_csv}")
    if not dy_csv.exists():
        raise FileNotFoundError(f"未找到抖音 CSV：{dy_csv}")
    if not st_rank_csv.exists():
        raise FileNotFoundError(f"未找到 SensorTower 排名 CSV：{st_rank_csv}")

    print("  - 从 wx_anomalies.csv 抽取 1 条微信游戏")
    wx_row = _read_csv_first_row(wx_csv)
    print("  - 从 dy_anomalies.csv 抽取 1 条抖音游戏")
    dy_row = _read_csv_first_row(dy_csv)
    print("  - 从 sensortower_rankings.csv 抽取 iOS / Android 各 1 条")
    st_rows = _pick_sensor_rows_from_rankings(st_rank_csv)

    if not wx_row:
        raise RuntimeError("wx_anomalies.csv 中未找到有效记录")
    if not dy_row:
        raise RuntimeError("dy_anomalies.csv 中未找到有效记录")
    if not st_rows.get("ios"):
        raise RuntimeError("sensortower_rankings.csv 中未找到 iOS 记录")
    if not st_rows.get("android"):
        raise RuntimeError("sensortower_rankings.csv 中未找到 Android 记录")

    # 统一列头：使用 wx_csv 的表头
    with wx_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

    out_dir = PROJECT_ROOT / "data" / "test_workflow"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "test_rankings_from_multi_csv.csv"

    rows: List[Dict] = [wx_row, dy_row, st_rows["ios"], st_rows["android"]]

    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"\n✓ 已生成测试 CSV：{out_csv}")
    print(f"  共 {len(rows)} 条记录（wx/dy/ios/android 各一条）")
    return out_csv


def run_full_workflow_and_trend(csv_path: Path, force_refresh_analysis: bool = True) -> None:
    """
    使用指定 CSV & 独立数据库跑通完整工作流，
    并验证 weekly_report_trends 中写入四个平台的玩法趋势。
    """
    test_db_dir = csv_path.parent
    # 将 config.RANKINGS_CSV_PATH 指向测试 CSV，同一目录下会生成 videos.db
    config.RANKINGS_CSV_PATH = str(csv_path)

    print("\n===== 使用测试 CSV + 独立数据库跑完整工作流（含周报玩法趋势） =====")
    print(f"测试 CSV ：{csv_path}")
    print(f"测试数据库：{test_db_dir / 'videos.db'}（若已存在，将保留其他数据，仅 AI 玩法通过 force_refresh_analysis 强制重算）")

    # 构建工作流实例
    workflow = GameAnalysisWorkflow(
        rankings_csv_path=str(csv_path),
        force_refresh_analysis=bool(force_refresh_analysis),
        skip_screenshots=True,
        platform=None,
        send_to=None,
    )

    # step0：检查 CSV
    print("\n--- Step 0: 检查测试 CSV ---")
    ok = workflow.step0_scrape_rankings()
    if not ok:
        print("Step 0 失败，中止测试。")
        return

    # step1：提取排行榜
    print("\n--- Step 1: 提取排行榜并写入测试库 ---")
    games = workflow.step1_extract_rankings(max_games=None)
    if not games:
        print("Step 1 未能提取到游戏信息，中止测试。")
        return

    print(f"Step 1 提取到 {len(games)} 个游戏：")
    for g in games:
        print(f"  - {g.get('游戏名称')}（平台：{g.get('平台')}，来源：{g.get('来源')}）")

    # step2：搜索并下载视频
    print("\n--- Step 2: 搜索并下载视频 ---")
    video_results = workflow.step2_search_videos(games)
    if not video_results:
        print("Step 2 未能获取到任何视频信息，中止测试。")
        return

    print(f"Step 2 获取到 {len(video_results)} 个视频记录。")

    # step3：分析视频
    print("\n--- Step 3: 分析视频（AI 玩法解析） ---")
    analyses = workflow.step3_analyze_videos(video_results)
    if not analyses:
        print("Step 3 未能生成任何玩法分析，中止测试。")
        return

    print(f"Step 3 生成 {len(analyses)} 条分析结果。")

    # step4：生成日报
    print("\n--- Step 4: 生成日报（不发送） ---")
    _ = workflow.step4_generate_report(analyses)
    print("Step 4 已生成日报 JSON，中间产物写入 data/step4_report_*.json\n")

    # step4b：玩法趋势分析并写入周报表
    print("\n--- Step 4b: 玩法趋势分析并写入 weekly_report_trends ---")
    inserted = workflow.step4b_play_trend_and_save(analyses)
    print(f"Step 4b 已写入 {inserted} 条周报玩法趋势记录。\n")

    # 简单检查 weekly_report_trends 中的平台覆盖情况
    db_path = test_db_dir / "videos.db"
    if not db_path.exists():
        print(f"警告：未找到测试数据库文件：{db_path}，无法验证 weekly_report_trends。")
        return

    test_db = VideoDatabase(db_path=str(db_path))
    import sqlite3

    conn = sqlite3.connect(test_db.db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT monitor_date, week_range, platform, source, substr(trend_analysis, 1, 80) "
        "FROM weekly_report_trends ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("警告：weekly_report_trends 中没有记录。")
        return

    print("===== weekly_report_trends 最新记录预览 =====")
    for row in rows:
        md, wr, pf, src, preview = row
        print(f"- 日期:{md} 周:{wr or '-'} 平台:{pf} 来源:{src} 趋势摘要:{preview}...")


def main() -> None:
    print("=" * 60)
    print("测试：从多 CSV 抽样跑完整工作流（wx/dy/ios/android 各一条）并写入周报趋势")
    print("=" * 60)

    test_csv = build_test_csv()
    # 默认强制重新分析玩法，确保测试不依赖旧缓存
    run_full_workflow_and_trend(test_csv, force_refresh_analysis=True)


if __name__ == "__main__":
    main()

