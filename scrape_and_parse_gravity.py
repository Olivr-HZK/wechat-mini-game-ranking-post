"""
一键工作流：先用 Playwright 打开引力引擎榜单页 -> 抓取 HTML -> 解析文本 -> 导出 3 个榜单 CSV/JSON。

说明：
- 由于榜单页通常需要登录/手动点“月榜”的三个榜单（tab），本脚本默认交互模式：
  1) 打开浏览器
  2) 你完成登录并把三个榜单都点一遍
  3) 回到终端按回车
  4) 脚本抓取 page.content() 保存到 data/debug_page_source.html
  5) 解析并导出 data/gravity_rankings_1.csv~3.csv（每榜20条，前三名无 NO 自动补）
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from datetime import datetime, date, timedelta
import re

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from parse_gravity_rank_from_html import (
    extract_text_lines,
    parse_three_boards_from_lines,
    write_csv,
    filter_top_n_by_keywords,
)
from dataclasses import asdict
import json


TARGET_URL = "https://web.gravity-engine.com/#/manage/rank"

def _wait_rank_response(page, timeout_ms: int = 15000) -> bool:
    """等待榜单接口返回一次（不依赖 networkidle）。"""
    try:
        page.wait_for_response(
            lambda r: "apprank/api/v1/rank/public_list" in r.url and r.status == 200,
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def _try_click_text_maybe_new_page(context, page, text: str, timeout_ms: int = 2000):
    """
    尽量点击带某个文本的元素（按钮/Tab/普通文本）。
    - 若点击会打开新窗口/新标签页：返回 (True, new_page)
    - 若未打开新页面：返回 (True, None)
    - 若点击失败：返回 (False, None)
    """
    text = (text or "").strip()
    if not text:
        return False, None
    candidates = [
        page.get_by_role("button", name=text),
        page.get_by_role("tab", name=text),
        page.get_by_text(text, exact=True),
        page.locator(f"text={text}"),
    ]
    for loc in candidates:
        try:
            if loc.count() <= 0:
                continue
            pages_before = list(context.pages)

            # 1) 优先捕获 popup（window.open / target=_blank）
            try:
                with page.expect_popup(timeout=1500) as pinfo:
                    loc.first.click(timeout=timeout_ms)
                new_page = pinfo.value
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=60000)
                except Exception:
                    pass
                return True, new_page
            except PlaywrightTimeout:
                pass

            # 2) 普通点击（可能是同页切换，也可能新开 tab）
            loc.first.click(timeout=timeout_ms)
            page.wait_for_timeout(400)

            pages_after = list(context.pages)
            new_pages = [p for p in pages_after if p not in pages_before]
            if new_pages:
                new_page = new_pages[-1]
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=60000)
                except Exception:
                    pass
                return True, new_page

            return True, None
        except Exception:
            continue
    return False, None


def _ensure_period_and_boards_loaded(context, page, period_label: str):
    """
    确保切到指定周期（日榜/周榜/月榜），并把三张榜都点一遍触发加载。
    这样 DOM 里才会有对应周期的数据，供后续 extract_text_lines + parser 使用。
    """
    period_label = (period_label or "").strip()
    if period_label in {"日榜", "周榜", "月榜"}:
        ok, new_page = _try_click_text_maybe_new_page(context, page, period_label, timeout_ms=3000)
        if ok:
            # 月榜可能会在新窗口打开：切到新页面继续操作
            if new_page is not None:
                page = new_page
            _wait_rank_response(page, timeout_ms=20000)
            page.wait_for_timeout(800)

    # 三榜：按顺序点一遍，让三张榜的数据都加载过（人气/畅销/畅玩）
    for board_label in ["人气榜", "畅销榜", "畅玩榜"]:
        ok, new_page = _try_click_text_maybe_new_page(context, page, board_label, timeout_ms=3000)
        if ok:
            if new_page is not None:
                page = new_page
            _wait_rank_response(page, timeout_ms=20000)
            page.wait_for_timeout(600)

    return page


def _date_for_filename(monitor_date: str) -> str:
    """
    将监控日期转成文件名格式：YYYY-M-D（不补0）
    例：2026-01-20 -> 2026-1-20
    """
    s = (monitor_date or "").strip()
    if not s:
        now = datetime.now()
        return f"{now.year}-{now.month}-{now.day}"

    parts = re.split(r"[-/]", s)
    if len(parts) >= 3 and all(p.strip().isdigit() for p in parts[:3]):
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{y}-{m}-{d}"
    return s


def _parse_ymd_to_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    parts = re.split(r"[-/]", s)
    if len(parts) >= 3 and all(p.strip().isdigit() for p in parts[:3]):
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return date(y, m, d)
        except Exception:
            return None
    return None


def _prev_week_range_filename(monitor_date: str) -> str:
    """
    周榜：用“上一周（周一~周日）”的日期范围命名文件。
    例：monitor_date=2026-01-19 -> 2026-1-12~2026-1-18
    """
    ref = _parse_ymd_to_date(monitor_date) or datetime.now().date()
    this_monday = ref - timedelta(days=ref.weekday())  # 本周周一
    prev_monday = this_monday - timedelta(days=7)
    prev_sunday = this_monday - timedelta(days=1)
    return f"{prev_monday.year}-{prev_monday.month}-{prev_monday.day}~{prev_sunday.year}-{prev_sunday.month}-{prev_sunday.day}"


def main() -> int:
    ap = argparse.ArgumentParser(description="打开网页抓HTML并解析三榜单")
    ap.add_argument("--url", default=TARGET_URL, help="目标URL")
    ap.add_argument("--headless", action="store_true", help="无头模式（通常登录场景不建议）")
    ap.add_argument("--section", default="月榜", help="从哪个关键字开始解析（默认 月榜）")
    ap.add_argument("--boards", type=int, default=3, help="榜单数量（默认 3）")
    ap.add_argument("--per-board", type=int, default=20, help="每个榜单条数（默认 20）")
    ap.add_argument("--output-dir", default="data", help="输出目录（默认 data）")
    ap.add_argument("--prefix", default="gravity_rankings", help="输出文件前缀")
    ap.add_argument("--save-html", action="store_true", help="额外保存HTML到 data/debug_page_source.html")
    ap.add_argument("--save-screenshot", action="store_true", help="额外保存截图到 data/debug_screenshot.png")
    ap.add_argument("--platform", default="微信小游戏", help="平台字段（默认 微信小游戏）")
    ap.add_argument("--source", default="引力引擎", help="来源字段（默认 引力引擎）")
    ap.add_argument("--monitor-date", default="", help="监控日期 YYYY-MM-DD（默认空则取今天）")
    ap.add_argument("--board-names", default="", help="三个榜单名称，逗号分隔（可选）")
    ap.add_argument(
        "--no-to-folders",
        action="store_true",
        help="不输出到 data/人气榜、data/畅销榜、data/畅玩榜（默认会输出）",
    )
    ap.add_argument(
        "--also-flat-output",
        action="store_true",
        help="同时输出 data/gravity_rankings_1.csv 这类平铺文件（默认不输出，只写入三个榜单文件夹）",
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
    ap.add_argument(
        "--auto-click",
        action="store_true",
        help="抓取前自动点击周期(tab)与三榜（适合周榜/月榜需要手动切换的情况）",
    )
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_out = out_dir / "debug_page_source.html"
    screenshot_out = out_dir / "debug_screenshot.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        print(f"[*] 打开: {args.url}")
        try:
            page.goto(args.url, wait_until="networkidle", timeout=90000)
        except PlaywrightTimeout:
            print("[!] 首次加载超时，继续执行（你可以在浏览器里手动刷新/登录）")

        if not args.headless:
            print("\n" + "=" * 60)
            print("请在弹出的浏览器里：")
            print("1) 完成登录（如需要）")
            if args.auto_click:
                print(f"2) 切到“{args.section}”（如需要），并确保页面能看到榜单区域")
                print("   回到终端按回车后，脚本会自动把三张榜都点一遍并抓取")
            else:
                print(f"2) 进入“{args.section}”，把三个榜单(tab)都点一遍（保证三榜数据都加载过）")
            print("然后回到终端按回车继续解析。")
            print("=" * 60 + "\n")
            try:
                input("按回车开始抓取HTML并解析... ")
            except KeyboardInterrupt:
                print("\n[!] 已取消")
                browser.close()
                return 1

        # 登录完成后：需要的话自动点击“周榜/月榜”等 + 三榜触发加载
        if args.auto_click:
            try:
                page = _ensure_period_and_boards_loaded(context, page, args.section)
            except Exception:
                pass

        # 给最后的异步请求一点时间
        time.sleep(2)

        html = page.content()

        if args.save_html or True:
            html_out.write_text(html, encoding="utf-8")
            print(f"[*] 已保存HTML: {html_out.resolve()}")

        if args.save_screenshot:
            try:
                page.screenshot(path=str(screenshot_out.resolve()), full_page=True)
                print(f"[*] 已保存截图: {screenshot_out.resolve()}")
            except Exception as e:
                print(f"[!] 保存截图失败: {e}")

        browser.close()

    # 解析
    lines = extract_text_lines(html)
    boards = parse_three_boards_from_lines(
        lines,
        section_keyword=args.section,
        boards=args.boards,
        per_board=args.per_board,
    )

    keywords = [s.strip() for s in (args.keywords or "").split(",") if s.strip()]
    monitor_date = args.monitor_date.strip() or datetime.now().strftime("%Y-%m-%d")
    board_names = [s.strip() for s in (args.board_names or "").split(",") if s.strip()]
    to_folders = not args.no_to_folders
    also_flat_output = bool(args.also_flat_output)

    # 固定输出顺序（用户要求）：1 人气榜，2 畅销榜，3 畅玩榜
    folder_map = [
        ("人气榜", "微信小游戏人气榜"),
        ("畅销榜", "微信小游戏畅销榜"),
        ("畅玩榜", "微信小游戏畅玩榜"),
    ]
    # 文件命名：日榜/月榜等用 monitor_date；周榜用“上一周（周一~周日）”范围
    if "周榜" in (args.section or ""):
        date_filename = _prev_week_range_filename(monitor_date)
    else:
        date_filename = _date_for_filename(monitor_date)

    for idx, items in enumerate(boards, start=1):
        if not args.no_filter:
            items = filter_top_n_by_keywords(items, keywords, args.top_n)

        # 榜单名称：优先用用户传入的 --board-names；否则按固定顺序；最后兜底 section+idx
        if idx - 1 < len(board_names):
            board_name = board_names[idx - 1]
        elif idx <= len(folder_map):
            board_name = folder_map[idx - 1][1]
        else:
            board_name = f"{args.section}{idx}"

        # 1) 输出到三个排行榜文件夹（用户期望）
        if to_folders and idx <= len(folder_map):
            folder_name, _default_board_label = folder_map[idx - 1]
            folder_dir = out_dir / folder_name
            folder_dir.mkdir(parents=True, exist_ok=True)
            folder_csv = folder_dir / f"{date_filename}.csv"
            write_csv(
                items,
                folder_csv,
                monitor_date=monitor_date,
                platform=args.platform,
                source=args.source,
                board_name=board_name,
            )
            print(f"✅ {folder_name}: {len(items)} 条 -> {folder_csv.resolve()}")

        # 2) 兼容旧输出（平铺）
        if also_flat_output:
            csv_path = out_dir / f"{args.prefix}_{idx}.csv"
            json_path = out_dir / f"{args.prefix}_{idx}.json"
            write_csv(
                items,
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
                        for x in items
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"✅ 榜单{idx}: {len(items)} 条 -> {csv_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

