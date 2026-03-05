#!/usr/bin/env python3
"""
清空数据库中的周报玩法趋势表 weekly_report_trends。
用于在重算周报前清理旧数据。
"""
import argparse
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.database import VideoDatabase


def main() -> int:
    ap = argparse.ArgumentParser(
        description="清空 weekly_report_trends 表中的所有周报趋势记录"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将删除的行数，不执行删除",
    )
    args = ap.parse_args()

    import sqlite3
    db = VideoDatabase()
    db_path = getattr(db, "db_path", str(ROOT / "data" / "videos.db"))
    print(f"数据库：{db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM weekly_report_trends")
    count = cursor.fetchone()[0]

    if count == 0:
        print("weekly_report_trends 表为空，无需清空。")
        conn.close()
        return 0

    if args.dry_run:
        print(f"【dry-run】将删除 {count} 条周报趋势记录（未执行删除）。")
        conn.close()
        return 0

    cursor.execute("DELETE FROM weekly_report_trends")
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    print(f"已清空 weekly_report_trends，共删除 {deleted} 条记录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
