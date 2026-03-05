"""
导出“上周所有异动游戏 + 玩法”到一个新的 CSV：
- 数据来源：
  - 周维度 & 榜单原始字段：来自 weekly_rankings.ranking（JSON，包含原 anomalies CSV 的 header/rows）
  - 玩法相关字段：来自 games 表的 gameplay_analysis（按游戏名称匹配）
- 只导出“最新一周”的记录（按 week_start / created_at 倒序取一周）

玩法字段提取：
- 从 gameplay_analysis 解析 JSON（VideoAnalyzer._parse_analysis_json），并抽取：
  - core_gameplay.mechanism
  - core_gameplay.operation
  - core_gameplay.rules
  - core_gameplay.features
  - baseline_and_innovation.base_genre
  - baseline_and_innovation.baseline_loop
  - baseline_and_innovation.micro_innovations（list -> "；" 连接）
  若数据库中没有该游戏，或无法解析 JSON，则以上字段留空。

输出文件：
- 默认路径：data/周报谷歌表单.csv

用法（项目根目录）：
  python -m scripts.tools.export_weekly_anomalies_with_gameplay_to_csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from modules.database import VideoDatabase  # noqa: E402
from modules.video_analyzer import VideoAnalyzer  # noqa: E402


def _get_db_path() -> Path:
    """与 VideoDatabase 默认行为保持一致：data/videos.db"""
    db_dir = Path(config.RANKINGS_CSV_PATH).parent
    return db_dir / "videos.db"


def _get_latest_week_info(conn: sqlite3.Connection) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    从 weekly_rankings 中找出“最新一周”的所有记录。
    返回 (week_range, rows)，其中 rows 为 dict 列表。
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 优先按 week_start 降序；如果为空则按 created_at 降序
    cur.execute(
        """
        SELECT *
        FROM weekly_rankings
        WHERE week_start IS NOT NULL AND week_start != ''
        ORDER BY week_start DESC, created_at DESC
        LIMIT 1
        """
    )
    first = cur.fetchone()
    if not first:
        # 兜底：按 created_at 找最新一条
        cur.execute(
            """
            SELECT *
            FROM weekly_rankings
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        first = cur.fetchone()
        if not first:
            return None

    latest_week_range = first["week_range"]
    # 取该 week_range 下的所有平台记录
    cur.execute(
        """
        SELECT *
        FROM weekly_rankings
        WHERE week_range = ?
        ORDER BY platform
        """,
        (latest_week_range,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    return latest_week_range, rows


def _extract_gameplay_fields(
    analyzer: VideoAnalyzer, analysis_text: str
) -> Tuple[str, str, str, str, str, str, str]:
    """
    从 gameplay_analysis 文本中解析 7 个玩法相关字段。
    返回：
      (core_mechanism, core_operation, core_rules, core_features,
       base_genre, baseline_loop, micro_innovations_joined)
    """
    if not analysis_text:
        return "", "", "", "", "", "", ""

    data = analyzer._parse_analysis_json(analysis_text)  # type: ignore[attr-defined]
    if not isinstance(data, dict):
        return "", "", "", "", "", "", ""

    core = data.get("core_gameplay") or {}
    base = data.get("baseline_and_innovation") or {}

    core_mech = str(core.get("mechanism") or "").strip()
    core_op = str(core.get("operation") or "").strip()
    core_rules = str(core.get("rules") or "").strip()
    core_feat = str(core.get("features") or "").strip()

    base_genre = str(base.get("base_genre") or "").strip()
    baseline_loop = str(base.get("baseline_loop") or "").strip()

    mi = base.get("micro_innovations") or []
    if isinstance(mi, list):
        mi_joined = "；".join(str(x).strip() for x in mi if str(x).strip())
    else:
        mi_joined = str(mi).strip()

    return core_mech, core_op, core_rules, core_feat, base_genre, baseline_loop, mi_joined


def _collect_rows_for_week(
    week_range: str,
    weekly_rows: List[Dict[str, Any]],
    db: VideoDatabase,
    analyzer: VideoAnalyzer,
) -> Tuple[List[str], List[List[str]]]:
    """
    根据 weekly_rankings 的 ranking JSON，展开为逐游戏行，并附加玩法字段。
    返回 (header, data_rows)。
    """
    # 统一的 CSV 输出表头
    header = [
        "周区间",
        "平台",
        "来源",
        "榜单",
        "地区",
        "排名",
        "游戏名称",
        "游戏类型",
        "标签",
        "热度指数",
        "监控日期",
        "发布时间",
        "开发公司",
        "排名变化",
        # 玩法相关字段
        "核心玩法_mechanism",
        "核心玩法_operation",
        "核心玩法_rules",
        "核心玩法_features",
        "基线_base_genre",
        "基线_baseline_loop",
        "基线_micro_innovations",
    ]

    rows_out: List[List[str]] = []

    for wk in weekly_rows:
        platform = wk.get("platform") or ""
        source = wk.get("source") or ""
        board_name = wk.get("board_name") or ""
        region = wk.get("region") or ""
        ranking_json = wk.get("ranking") or ""

        try:
            parsed = json.loads(ranking_json)
            src_header = parsed.get("header") or []
            src_rows = parsed.get("rows") or []
        except Exception:
            continue

        # 建索引方便取字段（如果行是列表时使用）
        col_index = {col: idx for idx, col in enumerate(src_header)}

        def safe_get(src_row: Any, col_name: str) -> str:
            """
            兼容两种行结构：
            - list：按 header 下标取值
            - dict：按列名 key 取值（这是当前 import_weekly_rankings_to_db 写入的结构）
            """
            if isinstance(src_row, dict):
                val = src_row.get(col_name, "")
                return str(val).strip() if val is not None else ""

            idx = col_index.get(col_name)
            if idx is None or not isinstance(src_row, (list, tuple)):
                return ""
            val = src_row[idx] if idx < len(src_row) else ""
            return str(val).strip() if val is not None else ""

        for src_row in src_rows:
            rank = safe_get(src_row, "排名")
            game_name = safe_get(src_row, "游戏名称")
            game_type = safe_get(src_row, "游戏类型")
            tag = safe_get(src_row, "标签")
            heat = safe_get(src_row, "热度指数")
            monitor_date = safe_get(src_row, "监控日期")
            publish_time = safe_get(src_row, "发布时间")
            company = safe_get(src_row, "开发公司")
            rank_change = safe_get(src_row, "排名变化")

            # 从 games 表中按游戏名称取玩法
            gameplay_text = ""
            core_mech = core_op = core_rules = core_feat = ""
            base_genre = baseline_loop = mi_joined = ""

            if game_name:
                game = db.get_game(game_name) or {}
                gameplay_text = (game.get("gameplay_analysis") or "").strip()
                if gameplay_text:
                    (
                        core_mech,
                        core_op,
                        core_rules,
                        core_feat,
                        base_genre,
                        baseline_loop,
                        mi_joined,
                    ) = _extract_gameplay_fields(analyzer, gameplay_text)

            row_out = [
                week_range or "",
                platform,
                source,
                board_name,
                region,
                rank,
                game_name,
                game_type,
                tag,
                heat,
                monitor_date,
                publish_time,
                company,
                rank_change,
                core_mech,
                core_op,
                core_rules,
                core_feat,
                base_genre,
                baseline_loop,
                mi_joined,
            ]
            rows_out.append(row_out)

    return header, rows_out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="导出最新一周的所有“异动游戏 + 玩法”到 CSV（周报谷歌表单）"
    )
    ap.add_argument(
        "--output",
        default="data/周报谷歌表单.csv",
        help="输出 CSV 路径（默认：data/周报谷歌表单.csv）",
    )
    args = ap.parse_args()

    db_path = _get_db_path()
    if not db_path.exists():
        print(f"错误：数据库不存在：{db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    latest = _get_latest_week_info(conn)
    if not latest:
        print("错误：weekly_rankings 中未找到任何周表记录，请先运行 import_weekly_rankings_to_db")
        return 1

    week_range, weekly_rows = latest
    print(f"[*] 即将导出周区间：{week_range}，共 {len(weekly_rows)} 个平台记录")

    db = VideoDatabase()
    analyzer = VideoAnalyzer(use_database=False)

    header, data_rows = _collect_rows_for_week(week_range, weekly_rows, db, analyzer)
    if not data_rows:
        print("错误：未展开出任何游戏行")
        return 1

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)

    print(f"✅ 导出完成：{out_path}（共 {len(data_rows)} 行，含表头）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

