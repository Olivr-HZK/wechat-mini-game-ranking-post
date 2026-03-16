"""
将 top20_ranking 和 rank_changes 表中的 week_range 从非补零格式
（如 2026-1-19~2026-1-25）迁移为补零格式（如 2026-01-19~2026-01-25）。

只更新 week_range 字段，其他字段不变。可重复运行（幂等）。

用法（项目根目录）：
  python scripts/tools/migrate_week_range_zero_pad.py
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.database import VideoDatabase  # noqa: E402


def normalize_week_range(week_range: str) -> str:
    """
    将形如 YYYY-M-D~YYYY-M-D 的 week_range 规范为 YYYY-MM-DD~YYYY-MM-DD。
    不符合格式的字符串将原样返回。
    """
    if not week_range or "~" not in week_range:
        return week_range
    parts = week_range.split("~", 1)
    if len(parts) != 2:
        return week_range

    def _norm(part: str) -> str | None:
        m = re.fullmatch(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*", part)
        if not m:
            return None
        y, mth, d = map(int, m.groups())
        return f"{y}-{mth:02d}-{d:02d}"

    left = _norm(parts[0])
    right = _norm(parts[1])
    if not left or not right:
        return week_range
    return f"{left}~{right}"


def migrate_table(conn: sqlite3.Connection, table: str) -> Dict[str, str]:
    """
    迁移指定表的 week_range 字段，返回 {old: new} 映射（仅包含发生变化的）。
    """
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT week_range FROM {table}")
    rows = cursor.fetchall()
    mapping: Dict[str, str] = {}
    for (old,) in rows:
        if old is None:
            continue
        new = normalize_week_range(old)
        if new != old:
            mapping[old] = new

    for old, new in mapping.items():
        cursor.execute(
            f"UPDATE {table} SET week_range = ? WHERE week_range = ?", (new, old)
        )
    return mapping


def main() -> int:
    db = VideoDatabase()
    conn = sqlite3.connect(db.db_path)

    total_mapping: Dict[str, str] = {}
    for table in ("top20_ranking", "rank_changes"):
        mapping = migrate_table(conn, table)
        if mapping:
            print(f"[{table}] 将以下 week_range 规范为补零格式：")
            for old, new in mapping.items():
                print(f"  {old}  ->  {new}")
            total_mapping.update(mapping)
        else:
            print(f"[{table}] 无需更新。")

    conn.commit()
    conn.close()

    if not total_mapping:
        print("没有发现需要更新的 week_range，已保持不变。")
    else:
        print("迁移完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

