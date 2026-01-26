"""
爬取“上周-人气周榜”CSV（用于后续工作流）。

支持两种平台：
- wechat：微信小游戏（原逻辑：只筛选【休闲】，排名取“休闲:X名”的 X，周平均排名写入“发布时间”）
- douyin：抖音小游戏（新增：先切到抖音tab，再点周榜；排名取第x条；“标签”写周平均排名；“排名变化”写标签内容）

参考：test copy.py 的DOM结构（rank-item / rank-index / font-bold / desc / el-tag__content）

输出CSV字段（与现有工作流一致，12列）：
排名,游戏名称,游戏类型,标签,热度指数,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化

其中：
- “描述”里包含的信息会被拆解：
  - 标签排名：例如 “其他:2名”（写入 标签 列，同时也用于 游戏类型）
  - 开发公司：例如 “杭州起源优游科技有限公司”（写入 开发公司 列；可能为空）
- “周平均排名:xx” 会写入 发布时间 列（格式：周平均排名:xx）

用法：
  python scrape_weekly_popularity.py
  python scrape_weekly_popularity.py --monitor-date 2026-01-19
  python scrape_weekly_popularity.py --platform douyin --monitor-date 2026-01-19
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


TARGET_URL = "https://web.gravity-engine.com/#/manage/rank"
DEFAULT_USER_DATA_DIR = Path("data") / "pw_user_data"


@dataclass
class WeeklyItem:
    rank: int
    name: str
    game_type: str
    tags: List[str]
    avg_rank: Optional[float]
    company: str
    rank_change: str


def _parse_ymd(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    parts = re.split(r"[-/]", s)
    if len(parts) >= 3 and all(p.strip().isdigit() for p in parts[:3]):
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            return None
    return None


def _prev_week_range(ref: date) -> Tuple[date, date]:
    """上一周（周一~周日）"""
    this_monday = ref - timedelta(days=ref.weekday())
    prev_monday = this_monday - timedelta(days=7)
    prev_sunday = this_monday - timedelta(days=1)
    return prev_monday, prev_sunday


def _week_range_filename(start: date, end: date) -> str:
    return f"{start.year}-{start.month}-{start.day}~{end.year}-{end.month}-{end.day}"


def _safe_int(s: str, fallback: int) -> int:
    s = (s or "").strip()
    m = re.search(r"\d+", s)
    if not m:
        return fallback
    try:
        return int(m.group(0))
    except Exception:
        return fallback


def _parse_avg_rank(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _extract_desc_and_avg(desc_texts: List[str]) -> Tuple[str, str]:
    """
    从多个 desc 文本里拆出：
    - main_desc：包含“类型:名次 + 公司”
    - avg_desc：包含“周平均排名:xx”
    """
    main_parts: List[str] = []
    avg_parts: List[str] = []
    for t in desc_texts:
        t = (t or "").strip()
        if not t:
            continue
        if "周平均排名" in t:
            avg_parts.append(t)
        else:
            main_parts.append(t)
    return "".join(main_parts).strip(), " ".join(avg_parts).strip()


def _parse_main_desc(main_desc: str) -> Tuple[str, Optional[int], str]:
    """
    main_desc 示例：其他:2名杭州起源优游科技有限公司
    返回：(game_type, tag_rank_no, company)
    """
    s = (main_desc or "").strip()
    if not s:
        return "", None, "--"

    m = re.search(r"(?P<cate>[^:：\s]+)\s*[:：]\s*(?P<no>\d+)\s*名", s)
    if not m:
        # 没有“类型:名次”结构，尽量把整段当公司
        company = s.strip() or "--"
        return "", None, company

    cate = m.group("cate").strip()
    no = m.group("no").strip()
    try:
        tag_rank_no = int(no)
    except Exception:
        tag_rank_no = None

    # 去掉“类型:名次”，剩余当公司
    company = re.sub(r"(?P<cate>[^:：\s]+)\s*[:：]\s*(?P<no>\d+)\s*名", "", s, count=1).strip()
    if not company:
        company = "--"
    return cate, tag_rank_no, company


def _parse_rank_change(tag_texts: List[str]) -> str:
    """从标签里提取排名变化（如 3 / +3 / -1 / 新进榜），否则 --"""
    # 新进榜/新入榜 优先写入“排名变化”
    for t in tag_texts:
        t = (t or "").strip()
        if not t:
            continue
        if t in {"新进榜", "新入榜"}:
            return t

    for t in tag_texts:
        t = (t or "").strip()
        if not t:
            continue
        m = re.fullmatch(r"[+-]?\d+", t)
        if m:
            return t
    return "--"


def _heat(rank: int) -> str:
    return str(max(0, 100 - (rank - 1) * 2))


def write_csv(
    items: List[WeeklyItem],
    output_csv: Path,
    *,
    monitor_date: str,
    platform: str,
    source: str,
    board_name: str,
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "排名",
        "游戏名称",
        "游戏类型",
        "标签",
        "热度指数",
        "平台",
        "来源",
        "榜单",
        "监控日期",
        "发布时间",
        "开发公司",
        "排名变化",
    ]

    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            tags_joined = "|".join([x for x in it.tags if x]) if it.tags else ""
            # wechat：周平均排名写到“发布时间”；douyin：周平均排名写到“标签”，这里发布时间填 --
            if platform == "抖音小游戏":
                publish = "--"
            else:
                publish = f"周平均排名:{it.avg_rank}" if it.avg_rank is not None else ""
            w.writerow(
                {
                    "排名": str(it.rank),
                    "游戏名称": it.name,
                    "游戏类型": it.game_type or "--",
                    "标签": tags_joined,
                    "热度指数": _heat(it.rank),
                    "平台": platform,
                    "来源": source,
                    "榜单": board_name,
                    "监控日期": monitor_date,
                    "发布时间": publish,
                    "开发公司": it.company or "--",
                    "排名变化": it.rank_change or "--",
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="爬取上周人气周榜并写入CSV（支持微信/抖音）")
    ap.add_argument("--monitor-date", default="", help="监控日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--limit", type=int, default=20, help="最多抓取条数（默认20）")
    ap.add_argument("--user-data-dir", default=str(DEFAULT_USER_DATA_DIR), help="持久化浏览器目录（用于复用登录态）")
    ap.add_argument("--platform", choices=["wechat", "douyin"], default="wechat", help="平台：wechat=微信小游戏，douyin=抖音小游戏")
    args = ap.parse_args()

    ref = _parse_ymd(args.monitor_date) or datetime.now().date()
    prev_monday, prev_sunday = _prev_week_range(ref)
    base_filename = _week_range_filename(prev_monday, prev_sunday) + ".csv"
    monitor_date = (args.monitor_date.strip() or datetime.now().strftime("%Y-%m-%d"))

    # 为避免覆盖微信周榜文件，抖音文件名前加 dy_
    filename = ("dy_" + base_filename) if args.platform == "douyin" else base_filename
    out_csv = Path("data") / "人气榜" / filename

    with sync_playwright() as p:
        # 用持久化 profile（推荐）：可复用登录态，同时默认 headless，不弹出物理浏览器窗口
        user_data_dir = Path(args.user_data_dir).expanduser()
        user_data_dir.mkdir(parents=True, exist_ok=True)
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        print(f"[*] 打开: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120000)
        except PlaywrightTimeout:
            print("[!] 页面加载超时（domcontentloaded），继续执行（可手动刷新）")

        # 抖音：先切换到“抖音小游戏”tab
        if args.platform == "douyin":
            try:
                douyin_tab = page.locator("xpath=//img[contains(@src,'douyin_tab_rank')]").first
                douyin_tab.wait_for(state="visible", timeout=60000)
                douyin_tab.click(timeout=5000)
                # 给页面一点时间渲染
                page.wait_for_timeout(3000)
                print("[*] 已切换到抖音小游戏榜")
            except Exception as e:
                print(f"[!] 切换到抖音小游戏榜失败：{e}")
                context.close()
                return 1

        # 点击“周榜”（参考 test copy.py 的 XPath）
        week_xpath = "//div[contains(@class,'button-item') and contains(normalize-space(.), '周榜')]"
        week_btn = page.locator(f"xpath={week_xpath}").first
        try:
            week_btn.wait_for(state="visible", timeout=60000)
            week_btn.click(timeout=5000)
        except Exception as e:
            print(f"[!] 点击‘周榜’失败：{e}")
            context.close()
            return 1

        # 等待榜单渲染
        try:
            page.wait_for_selector("xpath=//div[contains(@class,'rank-item')]", timeout=60000)
        except Exception:
            print("[!] 未检测到 rank-item（可能未切到周榜或未加载完成）")

        all_items = page.locator("xpath=//div[contains(@class,'rank-item')]")
        total = all_items.count()
        if total <= 0:
            print("[!] 未抓到任何榜单条目")
            context.close()
            return 1

        want = max(1, int(args.limit))
        if args.platform == "douyin":
            print(f"[*] 找到 rank-item: {total}，将读取前 {want} 条作为【抖音小游戏周榜】")
        else:
            print(f"[*] 找到 rank-item: {total}，将筛选【休闲】并最多输出 {want} 条")

        results: List[WeeklyItem] = []
        for i in range(total):
            node = all_items.nth(i)

            # 排名：douyin 直接用第x条；wechat 仍做兜底解析
            overall_rank_no = i + 1
            if args.platform != "douyin":
                try:
                    rank_text = node.locator("xpath=.//div[contains(@class,'rank-index')]//span[contains(@class,'index')]").first.inner_text().strip()
                except Exception:
                    rank_text = ""
                overall_rank_no = _safe_int(rank_text, i + 1)

            # 名称
            try:
                name = node.locator("xpath=.//span[contains(@class,'font-bold')]").first.inner_text().strip()
            except Exception:
                name = ""

            # desc（可能有多个）
            try:
                desc_texts = [t.strip() for t in node.locator("xpath=.//div[contains(@class,'desc')]").all_inner_texts()]
            except Exception:
                desc_texts = []
            main_desc, avg_desc = _extract_desc_and_avg(desc_texts)

            # 标签（可能多个）
            try:
                tag_texts = [t.strip() for t in node.locator("xpath=.//span[contains(@class,'el-tag__content')]").all_inner_texts()]
            except Exception:
                tag_texts = []

            # 周平均排名
            avg_rank = _parse_avg_rank(avg_desc)

            if args.platform == "douyin":
                # 抖音规则：
                # - 排名：第x条
                # - 标签列：周平均排名（来自 desc）
                # - 排名变化：标签内容（el-tag__content）
                rank_no = overall_rank_no
                game_type = "--"
                company = "--"
                tags: List[str] = []
                if avg_desc:
                    tags.append(avg_desc)
                elif desc_texts:
                    # 兜底：desc里只有一条时也可能就是周平均排名
                    tags.append(desc_texts[0])
                rank_change = _parse_rank_change(tag_texts) if tag_texts else "--"
            else:
                # 微信规则（原逻辑）：只要休闲，排名取“休闲:X名”
                game_type, tag_rank_no, company = _parse_main_desc(main_desc)

                # 只要“休闲”
                if (game_type or "").strip() != "休闲":
                    continue

                # “标签的排名”作为游戏排名：取 “休闲: X名”里的 X
                rank_no = tag_rank_no if tag_rank_no is not None else overall_rank_no

                # 拼标签：tag_rank + 页面标签（如 新进榜）
                tags = []
                if tag_rank_no is not None:
                    tags.append(f"{game_type}:{tag_rank_no}名")
                for t in tag_texts:
                    if t and t not in tags:
                        tags.append(t)

                rank_change = _parse_rank_change(tag_texts)
                if not rank_change or rank_change == "--":
                    rank_change = "--"

            it = WeeklyItem(
                rank=rank_no,
                name=name,
                game_type=game_type or "--",
                tags=tags,
                avg_rank=avg_rank,
                company=company or "--",
                rank_change=rank_change,
            )
            results.append(it)

            print(f"第 {i+1} 条：")
            print(f"  排名: {it.rank}")
            print(f"  名称: {it.name}")
            if args.platform == "douyin":
                # 抖音示例里描述主要就是周平均排名
                print(f"  描述: {avg_desc or ''.join(desc_texts)}")
            else:
                print(f"  描述: {main_desc}")
            print(f"  标签: {'|'.join(it.tags) if it.tags else ''}")
            print(f"  周平均排名: {avg_desc}")

            if len(results) >= want:
                break

        if not results:
            if args.platform == "douyin":
                print("[!] 未抓取到任何抖音条目（可能未加载到周榜，或未登录导致DOM不同）")
            else:
                print("[!] 未筛选到任何【休闲】条目（可能未加载到周榜，或未登录导致DOM不同）")
            context.close()
            return 1

        # 写CSV
        if args.platform == "douyin":
            platform_cn = "抖音小游戏"
            board_name = "抖音小游戏周榜"
        else:
            platform_cn = "微信小游戏"
            board_name = "微信小游戏人气周榜"
        write_csv(
            results,
            out_csv,
            monitor_date=monitor_date,
            platform=platform_cn,
            source="引力引擎",
            board_name=board_name,
        )
        print(f"\n✅ 已写入：{out_csv.resolve()}（{len(results)} 条）")

        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

