"""
将当前“人气榜”目录下的周榜 CSV 导入到数据库的 weekly_rankings 表。

目前支持的 CSV 结构：
- 微信小游戏人气周榜：wx_anomalies.csv
- 抖音小游戏周榜：dy_anomalies.csv
- SensorTower 榜单：sensortower_rankings.csv（从该文件获取 iOS/Android 数据，不再使用 sensortower_anomalies）

新的“周表”模型：
- weekly_rankings 表：每周 × 每平台一行（例如：2026-1-19~2026-1-25 × wx/dy/ios/android 共四行）
- 每一行有一个 ranking 字段，保存该周该平台的完整榜单 JSON（从对应 anomalies CSV 转换而来）
- 日期：
  - week_range/monitor_date 字段形如 2026-1-19~2026-1-25（从文件名解析）
  - 若无法解析周范围，则退回 CSV 原始“监控日期”
- 平台归一：
  - 微信小游戏 → wx
  - 抖音小游戏 → dy
  - SensorTower iOS → ios
  - SensorTower Android → android

用法（项目根目录）：
  python -m scripts.tools.import_weekly_rankings_to_db
  python -m scripts.tools.import_weekly_rankings_to_db --csv-dir "data/人气榜"
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from modules.database import VideoDatabase  # noqa: E402


def _read_csv_with_header(csv_path: Path) -> Tuple[List[str], List[List[str]]]:
    """读取 CSV，返回 (header, rows)，自动尝试多种常见编码。"""
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312"]
    last_err: Exception | None = None
    for enc in encodings:
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                all_rows = list(reader)
            if not all_rows:
                raise ValueError(f"CSV 为空：{csv_path}")
            header = all_rows[0]
            rows = all_rows[1:]
            return header, rows
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"无法读取 CSV：{csv_path}，最后错误：{last_err}")


def _parse_week_from_filename(csv_path: Path) -> Tuple[str | None, str | None]:
    """
    从“周目录名或文件名”中解析周起止日期（如 2026-1-19~2026-1-25）。
    优先使用上一级目录名（适配 data/人气榜/{周区间}/xxx.csv 的结构），
    解析失败则回退到文件名本身。
    返回 (week_start, week_end)，解析失败则 (None, None)。
    """
    # 1) 优先从父目录名解析
    parent_name = csv_path.parent.name
    m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})~(\d{4}-\d{1,2}-\d{1,2})", parent_name)
    if m:
        return m.group(1), m.group(2)

    # 2) 回退到文件名本身
    name = csv_path.stem
    m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})~(\d{4}-\d{1,2}-\d{1,2})", name)
    if m:
        return m.group(1), m.group(2)

    return None, None


def _normalize_platform_value(platform_raw: str, source: str) -> str:
    """将平台字段归一到 wx/dy/ios/android 四种。"""
    p = (platform_raw or "").lower()
    s = (source or "").lower()

    if "微信小游戏" in platform_raw:
        return "wx"
    if "抖音小游戏" in platform_raw:
        return "dy"

    if "sensortower" in s:
        if "ios" in p:
            return "ios"
        if "android" in p:
            return "android"

    # 兜底：直接返回原值
    return platform_raw or ""


def _build_weekly_records_from_csv(csv_path: Path) -> List[Dict]:
    """
    读取单个 anomalies CSV，并构建一批 weekly_rankings 记录：
    - 对于微信/抖音周榜：仅产生一条（wx 或 dy）
    - 对于 SensorTower：按平台拆分为 ios / android 两条（如果都有的话）
    """
    header, rows = _read_csv_with_header(csv_path)
    if not rows:
        return []

    header_index = {col: idx for idx, col in enumerate(header)}

    def col(name: str) -> int | None:
        return header_index.get(name)

    # 解析周范围
    week_start, week_end = _parse_week_from_filename(csv_path)

    # 公共字段索引
    idx_platform = col("平台")
    idx_source = col("来源")
    idx_board = col("榜单")
    idx_monitor = col("监控日期")
    idx_region = col("地区")

    def safe_get(row: List[str], idx: int | None) -> str:
        if idx is None:
            return ""
        return row[idx].strip() if idx < len(row) and row[idx] is not None else ""

    # 首先确定所有出现过的平台（已归一化）
    norm_platforms: List[str] = []
    per_row_platform: List[str] = []

    for row in rows:
        plat_raw = safe_get(row, idx_platform)
        src_raw = safe_get(row, idx_source)
        plat_norm = _normalize_platform_value(plat_raw, src_raw)
        per_row_platform.append(plat_norm)
        if plat_norm not in norm_platforms:
            norm_platforms.append(plat_norm)

    records: List[Dict] = []

    # 公共元数据：以第一行作为代表
    first_row = rows[0]
    source_val = safe_get(first_row, idx_source)
    board_name = safe_get(first_row, idx_board)
    monitor_raw = safe_get(first_row, idx_monitor)

    # week_range：优先文件名中的周范围，否则回退到监控日期
    if week_start and week_end:
        week_range = f"{week_start}~{week_end}"
    else:
        week_range = monitor_raw or None

    for plat_norm in norm_platforms:
        # 按当前平台过滤行
        filtered_rows: List[Dict] = []
        regions_in_rows: List[str] = []

        for row, row_platform_norm in zip(rows, per_row_platform):
            if row_platform_norm != plat_norm:
                continue

            row_dict: Dict[str, str] = {}
            for col_name, idx in header_index.items():
                val = safe_get(row, idx)
                row_dict[col_name] = val
                if col_name == "地区" and val:
                    regions_in_rows.append(val)
            filtered_rows.append(row_dict)

        if not filtered_rows:
            continue

        # 计算 region 汇总：微信/抖音 → 中国；SensorTower → 如果只有一个地区就用单个，否则“多地区”
        if plat_norm in ("wx", "dy"):
            region_val = "中国"
        else:
            distinct_regions = sorted({r for r in regions_in_rows if r})
            if len(distinct_regions) == 1:
                region_val = distinct_regions[0]
            elif len(distinct_regions) > 1:
                region_val = "多地区"
            else:
                region_val = ""

        ranking_json = json.dumps(
            {"header": header, "rows": filtered_rows},
            ensure_ascii=False,
        )

        records.append(
            {
                "week_range": week_range,
                "week_start": week_start,
                "week_end": week_end,
                "platform": plat_norm,
                "source": source_val,
                "board_name": board_name,
                "region": region_val,
                "ranking": ranking_json,
            }
        )

    return records


def main() -> int:
    ap = argparse.ArgumentParser(
        description="将人气榜 anomalies CSV 导入数据库 weekly_rankings 周表（一周×平台一行，ranking 为完整榜单 JSON）"
    )
    ap.add_argument(
        "--csv-dir",
        default="",
        help="人气榜 CSV 目录（默认使用 config.RANKINGS_CSV_PATH）",
    )
    ap.add_argument(
        "--db",
        default="",
        help="数据库文件路径（默认 data/videos.db）。若使用「videos copy.db」请指定 --db \"data/videos copy.db\"",
    )
    args = ap.parse_args()

    csv_dir_str = (args.csv_dir or "").strip() or config.RANKINGS_CSV_PATH
    csv_dir = Path(csv_dir_str)
    if not csv_dir.is_absolute():
        csv_dir = (PROJECT_ROOT / csv_dir).resolve()
    if not csv_dir.exists() or not csv_dir.is_dir():
        print(f"错误：CSV 目录不存在：{csv_dir}")
        return 1

    # 微信/抖音用异动榜；SensorTower 用 sensortower_rankings.csv（不用 sensortower_anomalies）
    csv_files = (
        sorted(csv_dir.rglob("wx_anomalies.csv"))
        + sorted(csv_dir.rglob("dy_anomalies.csv"))
        + sorted(csv_dir.rglob("sensortower_rankings.csv"))
    )
    if not csv_files:
        print(f"错误：目录下未找到 wx_anomalies.csv / dy_anomalies.csv / sensortower_rankings.csv：{csv_dir}")
        return 1

    db_path_arg = (args.db or "").strip()
    if db_path_arg:
        db_path = (PROJECT_ROOT / db_path_arg).resolve() if not Path(db_path_arg).is_absolute() else Path(db_path_arg)
        db = VideoDatabase(db_path=str(db_path))
    else:
        db = VideoDatabase()
        db_path = db.db_path
    print(f"[*] 数据库文件：{getattr(db, 'db_path', 'data/videos.db')}")
    print(f"[*] 在目录 {csv_dir} 中发现 {len(csv_files)} 个 CSV（wx/dy 异动 + sensortower_rankings），将按“每周×每平台”写入 weekly_rankings")

    records: List[Dict] = []

    for csv_path in csv_files:
        try:
            print(f"\n[*] 处理文件：{csv_path.name}")
            recs = _build_weekly_records_from_csv(csv_path)
            if not recs:
                print("    ⚠ 未生成有效周表记录，跳过")
                continue
            records.extend(recs)
            for rec in recs:
                print(
                    f"    ✓ 生成周表记录：week_range={rec.get('week_range')}, "
                    f"platform={rec.get('platform')}, rows_in_ranking={len(json.loads(rec['ranking'])['rows'])}"
                )
        except Exception as e:  # noqa: BLE001
            print(f"    ✗ 处理 {csv_path.name} 时出错：{e}")

    if not records:
        print("错误：未生成任何周表记录")
        return 1

    inserted = db.insert_weekly_rankings(records)
    print(f"\n✅ 导入完成，本次写入 weekly_rankings 行数：{inserted}")

    # 验证：直接查询表内总数，确认数据落在当前数据库
    try:
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM weekly_rankings")
        total = cur.fetchone()[0]
        conn.close()
        print(f"[*] 验证：数据库 {db.db_path} 中 weekly_rankings 表当前共 {total} 条记录")
    except Exception as e:
        print(f"[*] 验证时出错：{e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

