"""
将每周人气榜目录下的 4 个 CSV 导入到数据库两张新表：
- full 榜（wx_full.csv, dy_full.csv）-> top20_ranking
- 异动榜（wx_anomalies.csv, dy_anomalies.csv）-> rank_changes

CSV 的 11 列与表字段一一对应：排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区

用法（项目根目录）：
  python scripts/tools/import_ranking_csv_to_tables.py
  python scripts/tools/import_ranking_csv_to_tables.py "data/人气榜/2026-2-2~2026-2-8"
  python scripts/tools/import_ranking_csv_to_tables.py --week-dir "data/人气榜/2026-2-2~2026-2-8"
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from modules.database import VideoDatabase


def read_csv_as_dicts(csv_path: Path) -> list[dict]:
    """读取 CSV 为 list[dict]，key 为表头。尝试多种编码。"""
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312"]
    for enc in encodings:
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception:
            continue
    raise RuntimeError(f"无法读取 CSV：{csv_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="将每周 full/异动 CSV 导入 top20_ranking 与 rank_changes")
    parser.add_argument(
        "week_dir",
        nargs="?",
        default=None,
        help="周目录，如 data/人气榜/2026-2-2~2026-2-8；不传则自动选最新一周",
    )
    parser.add_argument("--week-dir", dest="week_dir_flag", help="同 week_dir 位置参数")
    args = parser.parse_args()
    week_dir = args.week_dir_flag or args.week_dir

    if not week_dir:
        base = Path(config.RANKINGS_CSV_PATH)
        if not base.is_dir():
            base = PROJECT_ROOT / "data" / "人气榜"
        if not base.exists():
            print(f"未找到人气榜目录：{base}")
            return 1
        dirs = [d for d in base.iterdir() if d.is_dir() and "~" in d.name]
        if not dirs:
            print(f"未找到任何周目录（含 ~）：{base}")
            return 1
        week_dir = str(max(dirs, key=lambda d: d.stat().st_mtime))

    week_path = Path(week_dir)
    if not week_path.is_dir():
        week_path = PROJECT_ROOT / week_dir
    if not week_path.is_dir():
        print(f"目录不存在：{week_path}")
        return 1

    week_range = week_path.name
    db = VideoDatabase()

    # full -> top20_ranking
    for platform_key, filename in [("wx", "wx_full.csv"), ("dy", "dy_full.csv")]:
        fp = week_path / filename
        if not fp.exists():
            print(f"[跳过] 不存在：{fp}")
            continue
        rows = read_csv_as_dicts(fp)
        n = db.insert_top20_ranking(week_range, platform_key, rows)
        print(f"[top20_ranking] {filename} -> {n} 行")

    # anomalies -> rank_changes
    for platform_key, filename in [("wx", "wx_anomalies.csv"), ("dy", "dy_anomalies.csv")]:
        fp = week_path / filename
        if not fp.exists():
            print(f"[跳过] 不存在：{fp}")
            continue
        rows = read_csv_as_dicts(fp)
        n = db.insert_rank_changes(week_range, platform_key, rows)
        print(f"[rank_changes] {filename} -> {n} 行")

    print(f"完成：{week_range}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
