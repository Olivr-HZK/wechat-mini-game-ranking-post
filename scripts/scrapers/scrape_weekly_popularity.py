"""
爬取“上周-人气周榜”CSV（用于后续工作流）。

支持两种平台：
- wechat：微信小游戏（只筛选【休闲】，排名取“休闲:X名”的 X，周平均排名写入“发布时间”）
- douyin：抖音小游戏（先切到抖音 tab 再点周榜；排名取第 x 条；“排名变化”写标签内容）

每次运行输出四个榜单（当 --platform all 时）或两个榜单（单平台时）：
- 完整休闲榜：wx_full.csv（微信休闲完整）、dy_full.csv（抖音周榜完整）
- 异动榜：wx_anomalies.csv、dy_anomalies.csv（排名飙升>10 或 新进榜）
- 榜单类型由 --chart 控制（均在对应区块内点「周榜」）：
  - popularity：人气榜（DOM 含 popularity）
  - bestseller：畅销榜（DOM 含 bestseller）
  - casual_play：畅玩榜（DOM 含 most_played，与接口 rank_type 一致）
- 输出目录：`data/人气榜/`、`data/畅销榜/`、`data/畅玩榜/` 下各接 `{周范围}/`，文件名均为 wx_full、dy_full 等

统一 CSV 格式（11 列）：
排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区

用法：
  python scrape_weekly_popularity.py --platform all   # 一次拉取四份榜单（推荐）
  python scrape_weekly_popularity.py --platform wechat
  python scrape_weekly_popularity.py --platform douyin --monitor-date 2026-01-19
  python scrape_weekly_popularity.py --chart bestseller --platform douyin --limit 30
  python scrape_weekly_popularity.py --chart both --platform douyin   # 人气+畅销
  python scrape_weekly_popularity.py --chart all --platform all       # 人气+畅销+畅玩
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


def read_previous_csv(csv_path: Path) -> Dict[str, int]:
    """
    读取上周 CSV 文件，构建游戏名称到排名的映射
    
    Args:
        csv_path: CSV 文件路径
    
    Returns:
        字典：{游戏名称: 排名}
    """
    if not csv_path.exists():
        return {}
    
    previous_map = {}
    try:
        with csv_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                game_name = row.get("游戏名称", "").strip()
                rank_str = row.get("排名", "").strip()
                if game_name and rank_str:
                    try:
                        rank = int(rank_str)
                        previous_map[game_name] = rank
                    except:
                        pass
    except Exception as e:
        print(f"  ⚠ 读取上周 CSV 失败：{e}")
    
    return previous_map


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


def _chart_section_class(chart: str) -> str:
    """
    页面 rank-list-item-header 上的区块 class（与引力页面一致）。
    畅玩榜在 DOM 上为 most_played；人气榜为 popularity（勿与畅玩混淆）。
    """
    if chart == "bestseller":
        return "bestseller"
    if chart == "casual_play":
        return "most_played"
    return "popularity"


def _week_button_locator(page, section_class: str):
    """在指定榜单区块（header 含 popularity / bestseller / most_played）内点击「周榜」。"""
    # 使用 contains(@class) 与页面实际 class 列表一致（避免 CSS 多类名在部分环境下匹配不到）
    return page.locator(
        f"xpath=//div[contains(@class,'rank-list-item-header') and contains(@class,'{section_class}')]"
        f"//div[contains(@class,'button-item') and contains(normalize-space(.), '周榜')]"
    ).first


def _week_button_locator_by_column_index(page, col_index: int):
    """
    按「第几个榜单头」取周榜按钮（0=左/第一块，1=右/第二块）。
    部分平台（如抖音）人气列可能不带 popularity class，需按列索引回退。
    """
    # XPath 下标从 1 开始
    n = col_index + 1
    return page.locator(
        f"xpath=(//div[contains(@class,'rank-list-item-header')])[{n}]"
        f"//div[contains(@class,'button-item') and contains(normalize-space(.), '周榜')]"
    ).first


def _rank_items_locator_by_column_index(page, col_index: int):
    """与 _week_button_locator_by_column_index 同一列下的 rank-item。"""
    n = col_index + 1
    header = page.locator(
        f"xpath=(//div[contains(@class,'rank-list-item-header')])[{n}]"
    ).first
    col = header.locator("xpath=..")
    items = col.locator("xpath=.//div[contains(@class,'rank-item')]")
    try:
        if items.count() > 0:
            return items
    except Exception:
        pass
    try:
        sib = header.locator("xpath=following-sibling::*").first
        items2 = sib.locator("xpath=.//div[contains(@class,'rank-item')]")
        if items2.count() > 0:
            return items2
    except Exception:
        pass
    return page.locator("xpath=//div[contains(@class,'rank-item')]")


def _rank_items_locator(page, section_class: str):
    """
    抓取指定榜单列下的 rank-item（header 与列表通常在同一个父容器内）。
    若结构不符则回退为全页 rank-item（兼容旧 DOM）。
    """
    headers = page.locator(
        f"xpath=//div[contains(@class,'rank-list-item-header') and contains(@class,'{section_class}')]"
    )
    try:
        if headers.count() == 0:
            return page.locator("xpath=//div[contains(@class,'rank-item')]")
    except Exception:
        pass
    header = headers.first
    col = header.locator("xpath=..")
    items = col.locator("xpath=.//div[contains(@class,'rank-item')]")
    try:
        if items.count() > 0:
            return items
    except Exception:
        pass
    # header 与列表为兄弟节点时
    try:
        sib = header.locator("xpath=following-sibling::*").first
        items2 = sib.locator("xpath=.//div[contains(@class,'rank-item')]")
        if items2.count() > 0:
            return items2
    except Exception:
        pass
    return page.locator("xpath=//div[contains(@class,'rank-item')]")


def _dismiss_overlays(page) -> None:
    """关闭可能遮挡 tab/周榜 的弹窗。"""
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


def _chart_label_cn(chart: str, platform: str) -> str:
    """控制台短标签；抖音侧人气/畅玩与微信产品名不同（热门榜、新游榜）。"""
    if platform == "douyin":
        if chart == "popularity":
            return "热门榜"
        if chart == "casual_play":
            return "新游榜"
    return {"bestseller": "畅销榜", "casual_play": "畅玩榜", "popularity": "人气榜"}.get(chart, "人气榜")


def scrape_one_platform(
    page,
    platform: str,
    limit: int,
    chart: str = "popularity",
) -> List[WeeklyItem]:
    """
    在当前页面上抓取一个平台的周榜（微信=休闲周榜，抖音=抖音小游戏周榜）。
    - platform "wechat" 时会先切到微信小游戏 tab（与抖音对称，避免默认停在抖音榜）。
    - platform "douyin" 时会先点击抖音 tab 再点周榜。
    - chart：popularity=人气，bestseller=畅销，casual_play=畅玩（DOM 为 most_played）。
    - limit 为 0 表示不限制条数；否则最多抓取 limit 条。
    返回解析后的 WeeklyItem 列表。
    """
    _dismiss_overlays(page)
    section_class = _chart_section_class(chart)
    chart_label = _chart_label_cn(chart, platform)

    # 微信：显式切到微信小游戏 tab（资源名含 wx_tab_rank，如 wx_tab_rank_select-xxx.png）
    if platform == "wechat":
        try:
            wx_tab = page.locator("xpath=//img[contains(@src,'wx_tab_rank')]").first
            wx_tab.wait_for(state="visible", timeout=60000)
            wx_tab.click(timeout=8000)
            page.wait_for_timeout(3000)
            print("[*] 已切换到微信小游戏榜")
        except Exception as e:
            try:
                wx_tab = page.locator("xpath=//img[contains(@src,'wx_tab_rank')]").first
                wx_tab.click(force=True, timeout=3000)
                page.wait_for_timeout(3000)
                print("[*] 已切换到微信小游戏榜（force click）")
            except Exception as e2:
                print(f"[!] 切换到微信小游戏榜失败：{e2}，继续尝试当前视图")

    # 抖音：切换到抖音小游戏 tab
    if platform == "douyin":
        try:
            douyin_tab = page.locator("xpath=//img[contains(@src,'douyin_tab_rank')]").first
            douyin_tab.wait_for(state="visible", timeout=60000)
            douyin_tab.click(timeout=8000)
            page.wait_for_timeout(3000)
            print("[*] 已切换到抖音小游戏榜")
        except Exception as e:
            try:
                douyin_tab = page.locator("xpath=//img[contains(@src,'douyin_tab_rank')]").first
                douyin_tab.click(force=True, timeout=3000)
                page.wait_for_timeout(3000)
                print("[*] 已切换到抖音小游戏榜（force click）")
            except Exception as e2:
                print(f"[!] 切换到抖音小游戏榜失败：{e2}")
                return []

    # 在指定榜单区块内点击「周榜」，并在未出现 rank-item 时重试几次（SPA 加载慢或首次点击未生效）
    week_btn = _week_button_locator(page, section_class)

    def _rank_scope():
        return _rank_items_locator(page, section_class)

    rank_scope = _rank_scope
    try:
        week_btn.scroll_into_view_if_needed(timeout=10000)
    except Exception:
        pass
    try:
        week_btn.wait_for(state="visible", timeout=60000)
    except Exception as e1:
        # 人气：抖音等可能不带 popularity class，用第 2 个榜单头
        if chart == "popularity":
            print("[*] 未找到带 popularity 的区块，尝试第 2 个榜单头内的「周榜」（人气列）…")
            week_btn = _week_button_locator_by_column_index(page, 1)

            def _rank_scope_fb():
                return _rank_items_locator_by_column_index(page, 1)

            rank_scope = _rank_scope_fb
            try:
                week_btn.scroll_into_view_if_needed(timeout=10000)
            except Exception:
                pass
            try:
                week_btn.wait_for(state="visible", timeout=60000)
            except Exception as e2:
                print(f"[!] 仍无法定位人气榜「周榜」按钮：{e2}")
                return []
        elif chart == "casual_play":
            # 畅玩：DOM 为 most_played；若无则尝试第 3 个榜单头（三榜并排时）
            print("[*] 未找到带 most_played 的畅玩区块，尝试第 3 个榜单头内的「周榜」…")
            week_btn = _week_button_locator_by_column_index(page, 2)

            def _rank_scope_c():
                return _rank_items_locator_by_column_index(page, 2)

            rank_scope = _rank_scope_c
            try:
                week_btn.scroll_into_view_if_needed(timeout=10000)
            except Exception:
                pass
            try:
                week_btn.wait_for(state="visible", timeout=60000)
            except Exception as e2:
                print(f"[!] 仍无法定位畅玩榜「周榜」按钮：{e2}")
                return []
        else:
            print(f"[!] 未找到「{chart_label}」区块内的「周榜」按钮：{e1}")
            return []

    rank_ready = False
    for attempt in range(5):
        try:
            week_btn.click(timeout=5000)
        except Exception as e:
            print(f"[!] 点击「{chart_label}」内「周榜」失败：{e}")
            return []
        page.wait_for_timeout(1500)
        try:
            scoped = rank_scope()
            scoped.first.wait_for(state="visible", timeout=20000)
            rank_ready = True
            break
        except Exception:
            print(f"[*] 等待 rank-item（第 {attempt + 1}/5 次）…")
            _dismiss_overlays(page)
            page.wait_for_timeout(2000)

    if not rank_ready:
        print("[!] 未检测到 rank-item（可能未切到周榜或未加载完成）")
        return []

    all_items = rank_scope()
    total = all_items.count()
    if total <= 0:
        print("[!] 未抓到任何榜单条目")
        return []

    want = limit if limit > 0 else total
    if platform == "douyin":
        print(
            f"[*] 找到 rank-item: {total}，将读取前 {min(want, total)} 条作为"
            f"【抖音小游戏·{chart_label}·周榜】"
        )
    else:
        print(
            f"[*] 找到 rank-item: {total}，将筛选【休闲】并最多输出 {want} 条"
            f"（{chart_label}）"
        )

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


def _board_names_for(platform: str, chart: str) -> Tuple[str, str]:
    """返回 (完整榜名称, 异动榜名称)。抖音侧：人气→热门榜、畅玩→新游榜（与产品文案一致）。"""
    if platform == "douyin":
        if chart == "bestseller":
            return ("抖音小游戏畅销周榜", "抖音小游戏畅销周榜异动")
        if chart == "casual_play":
            return ("抖音小游戏新游周榜", "抖音小游戏新游周榜异动")
        if chart == "popularity":
            return ("抖音小游戏热门周榜", "抖音小游戏热门周榜异动")
        return ("抖音小游戏热门周榜", "抖音小游戏热门周榜异动")
    if chart == "bestseller":
        return ("微信小游戏畅销周榜（休闲完整）", "微信小游戏畅销周榜异动")
    if chart == "casual_play":
        return ("微信小游戏畅玩周榜（休闲完整）", "微信小游戏畅玩周榜异动")
    return ("微信小游戏人气周榜（休闲完整）", "微信小游戏人气周榜异动")


def _csv_base_prefix(platform: str) -> str:
    """wx / dy。人气榜与畅销榜分目录存放，文件名均用此前缀。"""
    return "dy" if platform == "douyin" else "wx"


def _week_output_dir(chart: str, week_range: str) -> Path:
    """人气 / 畅销 / 畅玩 各自子目录。"""
    root = {
        "bestseller": "畅销榜",
        "casual_play": "畅玩榜",
        "popularity": "人气榜",
    }.get(chart, "人气榜")
    return Path("data") / root / week_range


def _charts_from_arg(chart_arg: str) -> List[str]:
    if chart_arg == "both":
        return ["popularity", "bestseller"]
    if chart_arg == "all":
        return ["popularity", "bestseller", "casual_play"]
    return [chart_arg]


def print_results_preview(
    items: List[WeeklyItem],
    title: str,
    *,
    max_rows: int = 80,
) -> None:
    """控制台打印榜单：排名、游戏名、排名变化（便于对照两个榜）。"""
    print(f"\n┌── {title} ──")
    if not items:
        print("│ （无数据）")
        print("└" + "─" * 60)
        return
    show_n = len(items) if max_rows <= 0 else min(len(items), max_rows)
    for i in range(show_n):
        it = items[i]
        name = (it.name or "")[:42]
        rc = it.rank_change or "--"
        print(f"│ {it.rank:>3}  {name:<42}  {rc}")
    if len(items) > show_n:
        print(f"│ … 共 {len(items)} 条，仅显示前 {show_n} 条（可用 --print-max-rows 0 显示全部）")
    print("└" + "─" * 60)


def main() -> int:
    ap = argparse.ArgumentParser(description="爬取上周人气周榜，输出完整榜+异动榜（wx/dy 各两份）")
    ap.add_argument("--monitor-date", default="", help="监控日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--limit", type=int, default=0, help="每平台最多抓取条数，0=不限制（默认0）")
    ap.add_argument("--user-data-dir", default=str(DEFAULT_USER_DATA_DIR), help="持久化浏览器目录（用于复用登录态）")
    ap.add_argument("--platform", choices=["wechat", "douyin", "all"], default="all",
                    help="平台：wechat=仅微信，douyin=仅抖音，all=两个都要（默认 all）")
    ap.add_argument(
        "--chart",
        choices=["popularity", "bestseller", "casual_play", "both", "all", "most_played"],
        default="popularity",
        help="popularity=人气，bestseller=畅销，casual_play=畅玩（DOM most_played）；"
        "both=人气+畅销；all=人气+畅销+畅玩；most_played 弃用同 popularity",
    )
    ap.add_argument(
        "--print-max-rows",
        type=int,
        default=80,
        help="控制台打印每个完整榜的最大行数，0=不限制（默认 80）",
    )
    ap.add_argument(
        "--no-print-preview",
        action="store_true",
        help="不写控制台榜单预览（仍写 CSV）",
    )
    ap.add_argument("--rank-surge-threshold", type=int, default=10, help="异动判定：排名飙升阈值（默认10）")
    args = ap.parse_args()
    chart_arg = args.chart
    if chart_arg == "most_played":
        print("[!] --chart most_played 已弃用，请改用 --chart popularity（人气榜）；本运行按 popularity 处理。")
        chart_arg = "popularity"

    ref = _parse_ymd(args.monitor_date) or datetime.now().date()
    prev_monday, prev_sunday = _prev_week_range(ref)
    week_range = _week_range_str(prev_monday, prev_sunday)
    monitor_date = (args.monitor_date.strip() or datetime.now().strftime("%Y-%m-%d"))

    charts = _charts_from_arg(chart_arg)
    # 仅创建本次运行会写入的子目录
    for ch in charts:
        _week_output_dir(ch, week_range).mkdir(parents=True, exist_ok=True)

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
            page.goto(TARGET_URL, wait_until="load", timeout=120000)
        except PlaywrightTimeout:
            print("[!] 页面加载超时（load），继续执行")
        page.wait_for_timeout(2500)

        any_ok = False
        print_max = args.print_max_rows
        for platform in platforms:
            platform_cn = "抖音小游戏" if platform == "douyin" else "微信小游戏"
            for chart in charts:
                week_dir = _week_output_dir(chart, week_range)
                base_name = _csv_base_prefix(platform)
                board_full, board_anomaly = _board_names_for(platform, chart)
                chart_cn = _chart_label_cn(chart, platform)

                print(f"\n{'='*50}")
                print(f"【{platform_cn} · {chart_cn}】→ {week_dir}")
                print(f"{'='*50}")
                results = scrape_one_platform(page, platform, limit, chart=chart)
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

                if not args.no_print_preview:
                    preview_title = f"{platform_cn} · {chart_cn} · 完整榜（{board_full}）"
                    print_results_preview(results, preview_title, max_rows=print_max)

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

