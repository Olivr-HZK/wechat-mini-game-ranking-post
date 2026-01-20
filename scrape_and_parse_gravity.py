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
from datetime import datetime

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
    ap.add_argument("--platform", choices=["vx", "dy"], default="vx", help="平台标识（默认 vx；抖音可用 dy）")
    ap.add_argument("--source", default="榜单", help="来源字段（默认 榜单）")
    ap.add_argument("--monitor-date", default="", help="监控日期 YYYY-MM-DD（默认空则取今天）")
    ap.add_argument("--board-names", default="", help="三个榜单名称，逗号分隔（可选）")
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
            print("2) 进入“月榜”，把三个榜单(tab)都点一遍（保证三榜数据都加载过）")
            print("然后回到终端按回车继续解析。")
            print("=" * 60 + "\n")
            try:
                input("按回车开始抓取HTML并解析... ")
            except KeyboardInterrupt:
                print("\n[!] 已取消")
                browser.close()
                return 1

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

    for idx, items in enumerate(boards, start=1):
        if not args.no_filter:
            items = filter_top_n_by_keywords(items, keywords, args.top_n)
        csv_path = out_dir / f"{args.prefix}_{idx}.csv"
        json_path = out_dir / f"{args.prefix}_{idx}.json"
        board_name = board_names[idx - 1] if idx - 1 < len(board_names) else f"{args.section}{idx}"
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

