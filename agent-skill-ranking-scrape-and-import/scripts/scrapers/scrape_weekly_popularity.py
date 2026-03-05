"""
爬取“上周-人气周榜”CSV（用于后续工作流）。

支持两种平台：
- wechat：微信小游戏（只筛选【休闲】，排名取“休闲:X名”的 X，周平均排名写入“发布时间”）
- douyin：抖音小游戏（先切到抖音 tab 再点周榜；排名取第 x 条；“排名变化”写标签内容）

每次运行输出四个榜单（当 --platform all 时）或两个榜单（单平台时）：
- 完整休闲榜：wx_full.csv（微信休闲完整）、dy_full.csv（抖音周榜完整）
- 异动榜：wx_anomalies.csv、dy_anomalies.csv（排名飙升>10 或 新进榜）

统一 CSV 格式（11 列）：
排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区

用法（在 Skill 根目录运行）：
  python scripts/scrapers/scrape_weekly_popularity.py --platform all   # 一次拉取四份榜单（推荐）
  python scripts/scrapers/scrape_weekly_popularity.py --platform wechat
  python scripts/scrapers/scrape_weekly_popularity.py --platform douyin --monitor-date 2026-01-19
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple, Dict

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


def _week_range_str(start: date, end: date) -> str:
    """返回周区间字符串，例如 2026-01-19~2026-01-25（月份/日期一律补零），用于文件夹命名。"""
    return (
        f"{start.year}-{start.month:02d}-{start.day:02d}"
        f"~{end.year}-{end.month:02d}-{end.day:02d}"
    )


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


# 引力引擎页面上升/下降图标的 SVG path d 特征（用于判断排名变化方向）
_SVG_UP_PATH_SIGNATURE = "704h639"  # 上升三角形 path d 含此片段，如 M512 320 192 704h639.936z
_SVG_DOWN_PATH_SIGNATURE = "320-384"  # 下降三角形 path d 含此片段，如 m192 384 320 384 320-384z


def _parse_rank_change(tag_texts: List[str]) -> str:
    """
    从标签文案里提取排名变化（文案中已带 ↑/↓/- 时用）。
    若仅靠文案无法区分方向，由调用方结合图标再判断。
    """
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
        if "↓" in t or (t.startswith("-") and t[1:].strip().isdigit()) or "下降" in t:
            num = re.search(r"\d+", t)
            if num:
                return f"↓{num.group(0)}"
        if "↑" in t or (t.startswith("+") and t[1:].strip().isdigit()) or re.fullmatch(r"\d+", t):
            num = re.search(r"\d+", t)
            if num:
                return f"↑{num.group(0)}"
    return "--"


def _get_rank_change_from_node(node) -> str:
    """
    从当前 rank-item 节点中根据「图标 + 文案」解析排名变化。
    优先识别 el-icon 内 SVG path：上升三角形 -> ↑N，下降三角形 -> ↓N；
    否则回退到仅用 el-tag__content 文案的 _parse_rank_change。
    """
    try:
        # 该条目的所有「标签」容器（通常含图标 + 文案）
        tag_containers = node.locator("xpath=.//span[contains(@class,'el-tag__content')]/..")
        n = tag_containers.count()
        for idx in range(n):
            container = tag_containers.nth(idx)
            text = ""
            try:
                text = container.locator("xpath=.//span[contains(@class,'el-tag__content')]").first.inner_text().strip()
            except Exception:
                continue
            if not text:
                continue
            if text in {"新进榜", "新入榜"}:
                return text
            # 同一容器内找 SVG path 的 d 属性，判断上升/下降
            try:
                path_el = container.locator("svg path[fill='currentColor']").first
                if path_el.count() == 0:
                    path_el = container.locator("svg path").first
                d = path_el.get_attribute("d") or ""
                num = re.search(r"\d+", text)
                if num:
                    if _SVG_DOWN_PATH_SIGNATURE in d:
                        return f"↓{num.group(0)}"
                    if _SVG_UP_PATH_SIGNATURE in d:
                        return f"↑{num.group(0)}"
            except Exception:
                pass
            # 无图标或未匹配到时，纯数字按上升处理
            if re.fullmatch(r"\d+", text.strip()):
                return f"↑{text.strip()}"
        # 没有通过容器解析到，用整条目的所有 tag 文案再试一次
        tag_texts = [t.strip() for t in node.locator("xpath=.//span[contains(@class,'el-tag__content')]").all_inner_texts()]
        return _parse_rank_change(tag_texts)
    except Exception:
        tag_texts = []
        try:
            tag_texts = [t.strip() for t in node.locator("xpath=.//span[contains(@class,'el-tag__content')]").all_inner_texts()]
        except Exception:
            pass
        return _parse_rank_change(tag_texts)


def _heat(rank: int) -> str:
    return str(max(0, 100 - (rank - 1) * 2))


def _parse_rank_change_value(rank_change_str: str) -> Optional[int]:
    """
    解析排名变化字符串为数值（用于异动筛选：>10 为飙升）
    - "↑25" -> 25（上升）
    - "↓10" -> -10（下降）
    - 新进榜 -> None
    """
    if not rank_change_str or rank_change_str == "--":
        return None

    if "新进榜" in rank_change_str or "新入榜" in rank_change_str:
        return None  # 新进榜

    # 下降：↓10、-10
    if "↓" in rank_change_str or (rank_change_str.strip().startswith("-") and rank_change_str.strip()[1:].strip().isdigit()):
        match = re.search(r"\d+", rank_change_str)
        if match:
            try:
                return -int(match.group(0))
            except Exception:
                pass
        return None
    # 上升：↑25、+25、25
    match = re.search(r"\d+", rank_change_str)
    if match:
        try:
            return int(match.group(0))
        except Exception:
            return None
    return None


def filter_anomalies_only(
    items: List[WeeklyItem],
    rank_surge_threshold: int = 10
) -> List[WeeklyItem]:
    """
    只保留异动游戏：新进榜，或 上升>阈值，或 下降>阈值（绝对值）。
    直接使用「排名变化」字段判断。
    """
    anomalies = []
    for item in items:
        rank_change = item.rank_change or "--"
        if "新进榜" in rank_change or "新入榜" in rank_change:
            anomalies.append(item)
            continue
        change_value = _parse_rank_change_value(rank_change)
        if change_value is None:
            continue
        # 上升 > 阈值 或 下降 > 阈值（绝对值）
        if change_value > rank_surge_threshold or change_value < -rank_surge_threshold:
            anomalies.append(item)
    return anomalies


def scrape_one_platform(
    page,
    platform: str,
    limit: int,
) -> List[WeeklyItem]:
    """
    在当前页面上抓取一个平台的周榜（微信=休闲周榜，抖音=抖音小游戏周榜）。
    - platform "douyin" 时会先点击抖音 tab 再点周榜。
    - limit 为 0 表示不限制条数；否则最多抓取 limit 条。
    返回解析后的 WeeklyItem 列表。
    """
    # 抖音：先关闭可能遮挡的弹窗，再切换到抖音小游戏 tab
    if platform == "douyin":
        # 页面上常有 el-overlay-dialog 弹窗遮挡，导致无法点击抖音 tab，先尝试关闭
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
        for close_sel in [
            ".el-dialog__headerbtn",
            ".el-dialog__close",
            "[class*='dialog'] [class*='close']",
            "button:has-text('关闭')",
            "button:has-text('确定')",
        ]:
            try:
                btn = page.locator(close_sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=2000)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                continue
        try:
            douyin_tab = page.locator("xpath=//img[contains(@src,'douyin_tab_rank')]").first
            douyin_tab.wait_for(state="visible", timeout=60000)
            douyin_tab.click(timeout=8000)
            page.wait_for_timeout(3000)
            print("[*] 已切换到抖音小游戏榜")
        except Exception as e:
            # 若仍被遮挡，尝试强制点击（force 可穿透 overlay）
            try:
                douyin_tab = page.locator("xpath=//img[contains(@src,'douyin_tab_rank')]").first
                douyin_tab.click(force=True, timeout=3000)
                page.wait_for_timeout(3000)
                print("[*] 已切换到抖音小游戏榜（force click）")
            except Exception as e2:
                print(f"[!] 切换到抖音小游戏榜失败：{e2}")
                return []

    # 点击「周榜」
    week_xpath = "//div[contains(@class,'button-item') and contains(normalize-space(.), '周榜')]"
    week_btn = page.locator(f"xpath={week_xpath}").first
    try:
        week_btn.wait_for(state="visible", timeout=60000)
        week_btn.click(timeout=5000)
    except Exception as e:
        print(f"[!] 点击「周榜」失败：{e}")
        return []

    try:
        page.wait_for_selector("xpath=//div[contains(@class,'rank-item')]", timeout=60000)
    except Exception:
        print("[!] 未检测到 rank-item（可能未切到周榜或未加载完成）")
        return []

    all_items = page.locator("xpath=//div[contains(@class,'rank-item')]")
    total = all_items.count()
    if total <= 0:
        print("[!] 未抓到任何榜单条目")
        return []

    want = limit if limit > 0 else total
    if platform == "douyin":
        print(f"[*] 找到 rank-item: {total}，将读取前 {min(want, total)} 条作为【抖音小游戏周榜】")
    else:
        print(f"[*] 找到 rank-item: {total}，将筛选【休闲】并最多输出 {want} 条")

    results: List[WeeklyItem] = []
    for i in range(total):
        node = all_items.nth(i)
        overall_rank_no = i + 1
        if platform != "douyin":
            try:
                rank_text = node.locator("xpath=.//div[contains(@class,'rank-index')]//span[contains(@class,'index')]").first.inner_text().strip()
            except Exception:
                rank_text = ""
            overall_rank_no = _safe_int(rank_text, i + 1)

        try:
            name = node.locator("xpath=.//span[contains(@class,'font-bold')]").first.inner_text().strip()
        except Exception:
            name = ""

        try:
            desc_texts = [t.strip() for t in node.locator("xpath=.//div[contains(@class,'desc')]").all_inner_texts()]
        except Exception:
            desc_texts = []
        main_desc, avg_desc = _extract_desc_and_avg(desc_texts)

        try:
            tag_texts = [t.strip() for t in node.locator("xpath=.//span[contains(@class,'el-tag__content')]").all_inner_texts()]
        except Exception:
            tag_texts = []

        avg_rank = _parse_avg_rank(avg_desc)

        # 排名变化：优先按节点内「图标 + 文案」解析（上升/下降三角形），否则用文案
        rank_change = _get_rank_change_from_node(node)
        if not rank_change or rank_change == "--":
            rank_change = _parse_rank_change(tag_texts) if tag_texts else "--"

        if platform == "douyin":
            rank_no = overall_rank_no
            game_type = "--"
            company = "--"
            tags: List[str] = []
            if avg_desc:
                tags.append(avg_desc)
            elif desc_texts:
                tags.append(desc_texts[0])
        else:
            game_type, tag_rank_no, company = _parse_main_desc(main_desc)
            if (game_type or "").strip() != "休闲":
                continue
            rank_no = tag_rank_no if tag_rank_no is not None else overall_rank_no
            tags = []
            if tag_rank_no is not None:
                tags.append(f"{game_type}:{tag_rank_no}名")
            for t in tag_texts:
                if t and t not in tags:
                    tags.append(t)
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
        if limit > 0 and len(results) >= limit:
            break

    return results


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
    # 新的统一格式：删除热度指数和标签，增加地区列
    fieldnames = [
        "排名",
        "游戏名称",
        "游戏类型",
        "平台",
        "来源",
        "榜单",
        "监控日期",
        "发布时间",
        "开发公司",
        "排名变化",
        "地区",
    ]

    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            # wechat：周平均排名写到“发布时间”；douyin：周平均排名写到“标签”，这里发布时间填 --
            # 统一处理：微信和抖音都将周平均排名写到"发布时间"
            publish = f"周平均排名:{it.avg_rank}" if it.avg_rank is not None else "--"
            w.writerow(
                {
                    "排名": str(it.rank),
                    "游戏名称": it.name,
                    "游戏类型": it.game_type or "--",
                    "平台": platform,
                    "来源": source,
                    "榜单": board_name,
                    "监控日期": monitor_date,
                    "发布时间": publish,
                    "开发公司": it.company or "--",
                    "排名变化": it.rank_change or "--",
                    "地区": "中国",  # 微信/抖音固定为中国
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="爬取上周人气周榜，输出完整榜+异动榜（wx/dy 各两份）")
    ap.add_argument("--monitor-date", default="", help="监控日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--limit", type=int, default=0, help="每平台最多抓取条数，0=不限制（默认0）")
    ap.add_argument("--user-data-dir", default=str(DEFAULT_USER_DATA_DIR), help="持久化浏览器目录（用于复用登录态）")
    ap.add_argument("--platform", choices=["wechat", "douyin", "all"], default="all",
                    help="平台：wechat=仅微信，douyin=仅抖音，all=两个都要（默认 all）")
    ap.add_argument("--rank-surge-threshold", type=int, default=10, help="异动判定：排名飙升阈值（默认10）")
    args = ap.parse_args()

    ref = _parse_ymd(args.monitor_date) or datetime.now().date()
    prev_monday, prev_sunday = _prev_week_range(ref)
    week_range = _week_range_str(prev_monday, prev_sunday)
    monitor_date = (args.monitor_date.strip() or datetime.now().strftime("%Y-%m-%d"))

    week_dir = Path("data") / "人气榜" / week_range
    week_dir.mkdir(parents=True, exist_ok=True)

    platforms: List[str] = ["wechat", "douyin"] if args.platform == "all" else [args.platform]
    limit = max(0, args.limit)

    with sync_playwright() as p:
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
            print("[!] 页面加载超时（domcontentloaded），继续执行")

        any_ok = False
        for platform in platforms:
            base_name = "dy" if platform == "douyin" else "wx"
            platform_cn = "抖音小游戏" if platform == "douyin" else "微信小游戏"
            board_full = "抖音小游戏周榜" if platform == "douyin" else "微信小游戏人气周榜（休闲完整）"
            board_anomaly = "抖音小游戏周榜异动" if platform == "douyin" else "微信小游戏人气周榜异动"

            print(f"\n{'='*50}")
            print(f"【{platform_cn}】")
            print(f"{'='*50}")
            results = scrape_one_platform(page, platform, limit)
            if not results:
                if platform == "douyin":
                    print("[!] 未抓取到任何抖音条目")
                else:
                    print("[!] 未筛选到任何【休闲】条目")
                continue
            any_ok = True

            # 完整榜
            full_csv = week_dir / f"{base_name}_full.csv"
            write_csv(
                results,
                full_csv,
                monitor_date=monitor_date,
                platform=platform_cn,
                source="引力引擎",
                board_name=board_full,
            )
            print(f"✅ 完整榜：{full_csv.name}（{len(results)} 条）")

            # 异动榜：新进榜 或 上升/下降 > 阈值（默认 10）
            anomalies = filter_anomalies_only(results, args.rank_surge_threshold)
            anomaly_csv = week_dir / f"{base_name}_anomalies.csv"
            write_csv(
                anomalies,
                anomaly_csv,
                monitor_date=monitor_date,
                platform=platform_cn,
                source="引力引擎",
                board_name=board_anomaly,
            )
            print(f"✅ 异动榜：{anomaly_csv.name}（{len(anomalies)} 条，新进榜 或 上升/下降>{args.rank_surge_threshold}）")

        context.close()
        if not any_ok:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

