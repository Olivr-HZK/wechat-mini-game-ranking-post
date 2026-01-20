"""
从 Playwright 保存的 HTML（page.content）里提取“月榜”榜单文本并解析排行榜。

你给的规则：
- 从“月榜”开始往下就是排行榜信息
- 排名：如果出现 `NO.<n>` 用它；前三名可能没有 NO，按出现顺序补 1/2/3
- 游戏名：只有一行
- 标签：在公司上面，可能多行（每行一个标签）
- 公司：一般为 `--` 或包含“公司/有限公司/股份有限公司/个人开发者”等

输出：
- 默认输出 3 个榜单（每榜 20 个）到 `data/`：
  - `gravity_rankings_1.csv`
  - `gravity_rankings_2.csv`
  - `gravity_rankings_3.csv`
- 同时写入 JSON（包含 tags 列表）：`gravity_rankings_1.json` 等
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional


NO_RE = re.compile(r"^NO\.\s*(\d+)\s*$", re.IGNORECASE)
CATE_RANK_RE = re.compile(r"^(.+?):\s*(\d+)\s*名\s*$")  # 休闲:1名
DOMINATE_DAYS_RE = re.compile(r"霸榜\s*(\d+)\s*天")


def is_company_like(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if s == "--":
        return True
    keywords = [
        "有限公司",
        "有限责任公司",
        "股份有限公司",
        "公司",
        "工作室",
        "个人开发者",
    ]
    return any(k in s for k in keywords)


class VisibleTextExtractor(HTMLParser):
    """提取HTML中的所有文本（跳过 script/style/noscript）。"""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if data and data.strip():
            self.parts.append(data.strip())


@dataclass
class RankItem:
    rank: Optional[int] = None
    name: str = ""
    tags: List[str] = None  # type: ignore[assignment]
    company: str = ""
    publish_days: str = ""

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []


def _parse_keywords(raw: str) -> List[str]:
    kws = []
    for part in (raw or "").split(","):
        s = part.strip()
        if s:
            kws.append(s)
    return kws


def _matches_keywords(item: RankItem, keywords: List[str]) -> bool:
    if not keywords:
        return True
    game_type = item.tags[0] if item.tags else ""
    for kw in keywords:
        if kw in game_type:
            return True
        for t in item.tags:
            if kw in t:
                return True
    return False


def filter_top_n_by_keywords(items: List[RankItem], keywords: List[str], top_n: int) -> List[RankItem]:
    """
    按榜单顺序从前往后筛选：
    只保留“游戏类型/标签中包含任意关键词”的前 top_n 个。
    """
    if top_n <= 0:
        return items
    selected: List[RankItem] = []
    for it in items:
        if _matches_keywords(it, keywords):
            selected.append(it)
            if len(selected) >= top_n:
                break
    return selected


def extract_text_lines(html: str) -> List[str]:
    parser = VisibleTextExtractor()
    parser.feed(html)
    # 这里不做复杂分句，直接把提取到的片段按换行/空白拆分
    raw = "\n".join(parser.parts)
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip().replace("\u00a0", " ")
        if not ln:
            continue
        # 有些片段可能包含多个空格分隔项，尽量保留原样，只去掉重复空白
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            lines.append(ln)
    return lines


def find_section_start(lines: List[str], section_keyword: str) -> int:
    """找到“月榜”等关键字所在的位置。找不到则返回 0。"""
    for i, ln in enumerate(lines):
        if section_keyword in ln:
            return i
    return 0


def looks_like_game_name(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    if NO_RE.match(line):
        return False
    if CATE_RANK_RE.match(line):
        return False
    if DOMINATE_DAYS_RE.search(line):
        return False
    if is_company_like(line):
        return False
    # 过滤一些明显的导航/标题
    if any(k in line for k in ["月榜", "周榜", "日榜", "榜单", "排行榜", "返回", "登录"]):
        return False
    return True


def _next_nonempty(lines: List[str], start_idx: int) -> Optional[str]:
    for j in range(start_idx, len(lines)):
        s = lines[j].strip()
        if s:
            return s
    return None


def _is_confirmed_game_name(lines: List[str], idx: int) -> bool:
    """
    更稳的“游戏名”判断：
    - 当前行看起来像游戏名
    - 下一条非空行是 “xxx:数字名”（如 休闲:1名 / 棋牌:1名）
    """
    ln = lines[idx].strip()
    if not looks_like_game_name(ln):
        return False
    nxt = _next_nonempty(lines, idx + 1)
    if not nxt:
        return False
    return CATE_RANK_RE.match(nxt) is not None


def parse_three_boards_from_lines(
    lines: List[str],
    section_keyword: str = "月榜",
    boards: int = 3,
    per_board: int = 20,
) -> List[List[RankItem]]:
    start = find_section_start(lines, section_keyword)
    lines = lines[start + 1 :] if start < len(lines) else lines

    result: List[List[RankItem]] = []
    board_items: List[RankItem] = []
    cur: Optional[RankItem] = None
    next_auto_rank = 1

    def finalize() -> None:
        nonlocal cur, next_auto_rank, board_items, result
        if not cur or not cur.name:
            cur = None
            return
        if cur.rank is None:
            cur.rank = next_auto_rank
        # 更新自动排名游标（遇到 NO.4 时自动跳到 5）
        next_auto_rank = max(next_auto_rank, (cur.rank or 0) + 1)
        # 去重 tags
        dedup = []
        seen = set()
        for t in cur.tags:
            if t and t not in seen:
                dedup.append(t)
                seen.add(t)
        cur.tags = dedup
        if not cur.company:
            cur.company = "--"
        board_items.append(cur)

        # 如果达到每榜数量（或遇到 rank==per_board），切榜
        if (cur.rank == per_board) or (len(board_items) >= per_board):
            result.append(board_items)
            board_items = []
            next_auto_rank = 1
        cur = None

    i = 0
    while i < len(lines) and len(result) < boards:
        ln = lines[i].strip()
        if not ln:
            i += 1
            continue

        m_no = NO_RE.match(ln)
        if m_no:
            # NO.x 通常是“新条目开始”
            finalize()
            cur = RankItem(rank=int(m_no.group(1)))
            i += 1
            continue

        if cur is None:
            # 没有 NO.1/2/3 的前三名：按出现顺序开新条目
            if _is_confirmed_game_name(lines, i):
                cur = RankItem(rank=None, name=ln)
            i += 1
            continue

        # cur 已存在
        if not cur.name:
            if _is_confirmed_game_name(lines, i):
                cur.name = ln
            i += 1
            continue

        # 跳过“分类:名次”行（休闲:1名）
        if CATE_RANK_RE.match(ln):
            i += 1
            continue

        # 霸榜天数
        m_days = DOMINATE_DAYS_RE.search(ln)
        if m_days:
            cur.publish_days = f"{m_days.group(1)}天"
            i += 1
            continue

        # 公司行
        if is_company_like(ln):
            cur.company = ln
            i += 1
            continue

        # 经验规则：如果已经读到公司行，后面再出现一个“像游戏名”的行，认为是下一条（前三名无 NO 的情况）
        if cur.company and _is_confirmed_game_name(lines, i):
            finalize()
            cur = RankItem(rank=None, name=ln)
            i += 1
            continue

        # 否则当作标签
        if ln != "--" and ln not in cur.tags:
            cur.tags.append(ln)
        i += 1

    finalize()

    # 如果循环结束但还有残余 board_items，也收尾（但不强制满20）
    if board_items and len(result) < boards:
        result.append(board_items)

    # 规范化：确保每个榜排序 & 自动补足缺失排名（尤其前三名）
    fixed: List[List[RankItem]] = []
    for board in result[:boards]:
        # 若某些 item rank 为空，按出现顺序补
        next_rank = 1
        for it in board:
            if it.rank is None:
                it.rank = next_rank
            next_rank = max(next_rank, (it.rank or 0) + 1)
        board.sort(key=lambda x: x.rank if x.rank is not None else 999999)
        fixed.append(board)

    return fixed


def write_csv(
    items: List[RankItem],
    output_csv: Path,
    *,
    monitor_date: str = "",
    platform: str = "",
    source: str = "榜单",
    board_name: str = "",
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    # 增加“标签”列（|拼接），满足“标签类型要全部获取”
    # 同时补充：监控日期、来源、榜单（用于后续报告/落库/溯源）
    fieldnames = [
        "排名",
        "游戏名称",
        "游戏类型",
        "标签",
        "热度指数",
        "平台",      # vx / dy（或你自定义）
        "来源",      # 榜单
        "榜单",      # 月榜1/月榜2/月榜3（或自定义名称）
        "监控日期",  # YYYY-MM-DD
        "发布时间",
        "开发公司",
        "排名变化",
    ]

    def heat(rank: int) -> str:
        return str(max(0, 100 - (rank - 1) * 2))

    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            r = it.rank or 0
            game_type = it.tags[0] if it.tags else ""
            tags_joined = "|".join(it.tags) if it.tags else ""
            w.writerow(
                {
                    "排名": str(it.rank or ""),
                    "游戏名称": it.name,
                    "游戏类型": game_type,
                    "标签": tags_joined,
                    "热度指数": heat(r) if r else "",
                    "平台": platform or "vx",
                    "来源": source or "榜单",
                    "榜单": board_name or "",
                    "监控日期": monitor_date or "",
                    "发布时间": it.publish_days,
                    "开发公司": it.company or "--",
                    "排名变化": "--",
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="从 HTML 提取“月榜”文本并解析排行榜")
    ap.add_argument(
        "-i",
        "--input",
        default="data/debug_page_source.html",
        help="输入HTML路径（默认 data/debug_page_source.html）",
    )
    ap.add_argument(
        "--output-dir",
        default="data",
        help="输出目录（默认 data）",
    )
    ap.add_argument(
        "--prefix",
        default="gravity_rankings",
        help="输出文件前缀（默认 gravity_rankings，将生成 gravity_rankings_1.csv 等）",
    )
    ap.add_argument("--section", default="月榜", help="从哪个榜单关键字开始解析（默认 月榜）")
    ap.add_argument("--boards", type=int, default=3, help="榜单数量（默认 3）")
    ap.add_argument("--per-board", type=int, default=20, help="每个榜单条数（默认 20）")
    ap.add_argument(
        "--platform",
        choices=["vx", "dy"],
        default="vx",
        help="平台标识（默认 vx；抖音可用 dy）",
    )
    ap.add_argument("--source", default="榜单", help="来源字段（默认 榜单）")
    ap.add_argument(
        "--monitor-date",
        default="",
        help="监控日期 YYYY-MM-DD（默认空则取今天）",
    )
    ap.add_argument(
        "--board-names",
        default="",
        help="三个榜单名称，逗号分隔（可选），例如：畅销榜,热门榜,新品榜；不填则用“月榜1/月榜2/月榜3”",
    )
    ap.add_argument(
        "--keywords",
        default="益智,休闲",
        help="仅保留：游戏类型/标签包含这些关键词的条目（逗号分隔，默认 益智,休闲）",
    )
    ap.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="每个榜单最多输出匹配条件的前 N 个（默认 10，<=0 表示不限制）",
    )
    ap.add_argument("--no-filter", action="store_true", help="不做关键词过滤，输出整榜")
    args = ap.parse_args()

    html_path = Path(args.input)
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    lines = extract_text_lines(html)
    boards = parse_three_boards_from_lines(
        lines,
        section_keyword=args.section,
        boards=args.boards,
        per_board=args.per_board,
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    keywords = _parse_keywords(args.keywords)
    monitor_date = args.monitor_date.strip() or datetime.now().strftime("%Y-%m-%d")
    board_names = [s.strip() for s in (args.board_names or "").split(",") if s.strip()]

    for idx, board_items in enumerate(boards, start=1):
        if not args.no_filter:
            board_items = filter_top_n_by_keywords(board_items, keywords, args.top_n)
        csv_path = out_dir / f"{args.prefix}_{idx}.csv"
        json_path = out_dir / f"{args.prefix}_{idx}.json"
        board_name = (
            board_names[idx - 1]
            if idx - 1 < len(board_names)
            else f"{args.section}{idx}"
        )
        write_csv(
            board_items,
            csv_path,
            monitor_date=monitor_date,
            platform=args.platform,
            source=args.source,
            board_name=board_name,
        )
        json_path.write_text(
            json.dumps(
                [
                    {
                        **asdict(x),
                        "监控日期": monitor_date,
                        "平台": args.platform,
                        "来源": args.source,
                        "榜单": board_name,
                    }
                    for x in board_items
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"✅ 榜单{idx}: {len(board_items)} 条 -> {csv_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

