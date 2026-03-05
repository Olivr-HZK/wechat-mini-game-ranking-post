"""
独立版：将每周人气榜目录下的 4 个 CSV 导入到 SQLite 数据库中的两张表：
- full 榜（wx_full.csv, dy_full.csv）-> top20_ranking
- 异动榜（wx_anomalies.csv, dy_anomalies.csv）-> rank_changes

CSV 的 11 列与表字段一一对应：
排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区

数据库文件：data/videos.db
人气榜根目录：data/人气榜

用法（在 Skill 根目录运行）：
  python scripts/tools/import_ranking_csv_to_tables.py
  python scripts/tools/import_ranking_csv_to_tables.py "data/人气榜/2026-02-16~2026-02-22"
  python scripts/tools/import_ranking_csv_to_tables.py --week-dir "data/人气榜/2026-02-16~2026-02-22"
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Dict, List


SKILL_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = SKILL_ROOT / "data"
RANKINGS_ROOT = DATA_DIR / "人气榜"
DB_PATH = DATA_DIR / "videos.db"


def ensure_db_schema() -> None:
    """确保 SQLite 中存在 top20_ranking / rank_changes 两张表及索引。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS top20_ranking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_range TEXT NOT NULL,
            platform_key TEXT NOT NULL,
            rank TEXT,
            game_name TEXT,
            game_type TEXT,
            platform TEXT,
            source TEXT,
            board_name TEXT,
            monitor_date TEXT,
            publish_time TEXT,
            company TEXT,
            rank_change TEXT,
            region TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_top20_week_platform
        ON top20_ranking(week_range, platform_key)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rank_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_range TEXT NOT NULL,
            platform_key TEXT NOT NULL,
            rank TEXT,
            game_name TEXT,
            game_type TEXT,
            platform TEXT,
            source TEXT,
            board_name TEXT,
            monitor_date TEXT,
            publish_time TEXT,
            company TEXT,
            rank_change TEXT,
            region TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rank_changes_week_platform
        ON rank_changes(week_range, platform_key)
        """
    )

    conn.commit()
    conn.close()


def read_csv_as_dicts(csv_path: Path) -> List[Dict]:
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


_RANKING_CSV_COLUMNS = [
    ("排名", "rank"),
    ("游戏名称", "game_name"),
    ("游戏类型", "game_type"),
    ("平台", "platform"),
    ("来源", "source"),
    ("榜单", "board_name"),
    ("监控日期", "monitor_date"),
    ("发布时间", "publish_time"),
    ("开发公司", "company"),
    ("排名变化", "rank_change"),
    ("地区", "region"),
]


def _row_to_tuple(row: Dict, week_range: str, platform_key: str) -> tuple:
    """将 CSV 行（中文 key 或英文 key）转为插入元组。"""
    out = [week_range, platform_key]
    for cn, en in _RANKING_CSV_COLUMNS:
        val = row.get(cn) or row.get(en) or ""
        out.append(val if isinstance(val, str) else str(val))
    return tuple(out)


def insert_table(table: str, week_range: str, platform_key: str, rows: List[Dict]) -> int:
    """将给定 rows 写入指定表（top20_ranking / rank_changes），同一 key 先删后插。"""
    if not rows:
        return 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        f"DELETE FROM {table} WHERE week_range = ? AND platform_key = ?",
        (week_range, platform_key),
    )
    cols = ["week_range", "platform_key"] + [en for _, en in _RANKING_CSV_COLUMNS]
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    tuples = [_row_to_tuple(r, week_range, platform_key) for r in rows]
    cursor.executemany(sql, tuples)
    conn.commit()
    n = cursor.rowcount
    conn.close()
    return n


def pick_latest_week_dir() -> Path:
    """从 data/人气榜 下选择最新修改时间的周目录（目录名包含 ~）。"""
    if not RANKINGS_ROOT.exists():
        raise RuntimeError(f"未找到人气榜目录：{RANKINGS_ROOT}")
    dirs = [d for d in RANKINGS_ROOT.iterdir() if d.is_dir() and "~" in d.name]
    if not dirs:
        raise RuntimeError(f"未找到任何周目录（含 ~）：{RANKINGS_ROOT}")
    return max(dirs, key=lambda d: d.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser(description="将每周 full/异动 CSV 导入 SQLite 中的 top20_ranking / rank_changes")
    parser.add_argument(
        "week_dir",
        nargs="?",
        default=None,
        help="周目录，如 data/人气榜/2026-02-16~2026-02-22；不传则自动选最新一周",
    )
    parser.add_argument("--week-dir", dest="week_dir_flag", help="同 week_dir 位置参数")
    args = parser.parse_args()
    week_dir = args.week_dir_flag or args.week_dir

    ensure_db_schema()

    if not week_dir:
        week_path = pick_latest_week_dir()
    else:
        week_path = Path(week_dir)
        if not week_path.is_dir():
            week_path = SKILL_ROOT / week_dir
        if not week_path.is_dir():
            print(f"目录不存在：{week_path}")
            return 1

    week_range = week_path.name

    # full -> top20_ranking
    for platform_key, filename in [("wx", "wx_full.csv"), ("dy", "dy_full.csv")]:
        fp = week_path / filename
        if not fp.exists():
            print(f"[跳过] 不存在：{fp}")
            continue
        rows = read_csv_as_dicts(fp)
        n = insert_table("top20_ranking", week_range, platform_key, rows)
        print(f"[top20_ranking] {filename} -> {n} 行")

    # anomalies -> rank_changes
    for platform_key, filename in [("wx", "wx_anomalies.csv"), ("dy", "dy_anomalies.csv")]:
        fp = week_path / filename
        if not fp.exists():
            print(f"[跳过] 不存在：{fp}")
            continue
        rows = read_csv_as_dicts(fp)
        n = insert_table("rank_changes", week_range, platform_key, rows)
        print(f"[rank_changes] {filename} -> {n} 行")

    print(f"完成：{week_range} -> {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

