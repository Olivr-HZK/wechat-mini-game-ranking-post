import csv
import os
import random
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


TARGET_URL = "https://adxray.dataeye.com/index/home#/Product"
OUTPUT_FILENAME = "game_rankings.csv"


def resolve_output_dir():
    """解析输出目录，优先使用data目录"""
    env_dir = os.environ.get("OUTPUT_DIR")
    if env_dir:
        return Path(env_dir)

    # 优先使用项目根目录下的data目录
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    if data_dir.exists():
        return data_dir
    
    # 如果data目录不存在，创建它
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def normalize_header(text):
    return re.sub(r"\s+", "", text or "")


def pick_column_indices(headers):
    indices = {"rank": None, "name": None, "days": None, "change": None}
    for idx, header in enumerate(headers):
        cleaned = normalize_header(header)
        if cleaned == "排名":
            indices["rank"] = idx
        elif "游戏名" in cleaned:
            indices["name"] = idx
        elif "投放天数" in cleaned:
            indices["days"] = idx
        elif "排名变化" in cleaned:
            indices["change"] = idx

    fallback = {"rank": 0, "name": 1, "days": 4, "change": 5}
    for key, value in fallback.items():
        if indices[key] is None:
            indices[key] = value
    return indices


def has_wechat_icon(row):
    wechat_locator = row.locator(
        'use[xlink\\:href="#icon-wechat"], use[href="#icon-wechat"]'
    )
    if wechat_locator.count() > 0:
        return True
    return "icon-wechat" in row.inner_html()


def cell_text(cells, idx):
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx].inner_text().strip()


def parse_rank(text, fallback_rank):
    if not text:
        return str(fallback_rank)
    match = re.search(r"\d+", text)
    return match.group(0) if match else text.strip()


def parse_game_name(text):
    if not text:
        return ""
    return text.splitlines()[0].strip()


def parse_company(text):
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines[1]
    return ""


def scrape():
    output_dir = resolve_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        def _route_filter(route, request):
            if request.resource_type in {"image", "media", "font"}:
                return route.abort()
            return route.continue_()

        page.route("**/*", _route_filter)

        print(f"[*] 访问: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)
        except PlaywrightTimeout:
            print("[!] 首次加载超时，尝试刷新重试...")
            page.reload(wait_until="domcontentloaded", timeout=90000)

        time.sleep(random.uniform(1.0, 2.0))

        try:
            page.wait_for_selector("table", timeout=60000)
            page.wait_for_selector("tbody tr.ant-table-row", timeout=60000)
        except PlaywrightTimeout:
            print("[-] 未能加载榜单表格，请检查页面是否可访问。")
            browser.close()
            return

        table = page.locator("table").first
        headers = table.locator("thead tr th").all_inner_texts()
        column_indices = pick_column_indices(headers)

        rows_locator = table.locator("tbody tr.ant-table-row")
        total_rows = rows_locator.count()
        print(f"[*] 发现 {total_rows} 条记录，筛选微信小游戏直到凑满 10 条。")

        results = []
        for i in range(total_rows):
            row = rows_locator.nth(i)
            row.scroll_into_view_if_needed()
            time.sleep(random.uniform(0.3, 0.9))

            if not has_wechat_icon(row):
                continue

            cells = row.locator("td").all()
            rank_text = cell_text(cells, column_indices["rank"])
            name_text = cell_text(cells, column_indices["name"])
            days_text = cell_text(cells, column_indices["days"])
            change_text = cell_text(cells, column_indices["change"])

            results.append(
                {
                    "排名": parse_rank(rank_text, i + 1),
                    "游戏名称": parse_game_name(name_text),
                    "游戏类型": "微信小游戏",  # 默认类型，因为DEScraper只爬取微信小游戏
                    "热度指数": str(100 - int(parse_rank(rank_text, i + 1)) * 2),  # 根据排名计算热度（排名越前热度越高）
                    "平台": "微信小游戏",
                    "发布时间": days_text,  # 使用投放天数作为发布时间
                    # 保留原始字段供参考
                    "开发公司": parse_company(name_text),
                    "排名变化": change_text or "--",
                }
            )
            if len(results) >= 10:
                break

        # 定义CSV字段（工作流需要的字段）
        fieldnames = ["排名", "游戏名称", "游戏类型", "热度指数", "平台", "发布时间","开发公司","排名变化"]
        
        with open(output_path, "w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            # 只写入工作流需要的字段
            for result in results:
                writer.writerow({
                    "排名": result["排名"],
                    "游戏名称": result["游戏名称"],
                    "游戏类型": result["游戏类型"],
                    "热度指数": result["热度指数"],
                    "平台": result["平台"],
                    "发布时间": result["发布时间"],
                    "开发公司": result["开发公司"],
                    "排名变化": result["排名变化"],
                })

        print(f"✅ 完成，已保存 {len(results)} 条记录至 {output_path}")
        browser.close()


if __name__ == "__main__":
    scrape()
