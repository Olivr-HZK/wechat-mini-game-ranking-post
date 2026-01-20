import csv
import os
import random
import re
import time
from pathlib import Path
from typing import List, Dict, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


TARGET_URL = "https://web.gravity-engine.com/#/manage/rank"
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
    """根据表头识别列索引"""
    indices = {
        "rank": None, 
        "name": None, 
        "type": None,
        "platform": None,
        "company": None,
        "change": None,
        "heat": None,
        "days": None
    }
    
    for idx, header in enumerate(headers):
        cleaned = normalize_header(header)
        if cleaned in ["排名", "rank", "序号"]:
            indices["rank"] = idx
        elif "游戏名" in cleaned or "名称" in cleaned or "name" in cleaned.lower():
            indices["name"] = idx
        elif "类型" in cleaned or "分类" in cleaned or "category" in cleaned.lower() or "type" in cleaned.lower():
            indices["type"] = idx
        elif "平台" in cleaned or "platform" in cleaned.lower():
            indices["platform"] = idx
        elif "公司" in cleaned or "开发" in cleaned or "company" in cleaned.lower() or "developer" in cleaned.lower():
            indices["company"] = idx
        elif "变化" in cleaned or "change" in cleaned.lower() or "排名变化" in cleaned:
            indices["change"] = idx
        elif "热度" in cleaned or "heat" in cleaned.lower() or "指数" in cleaned:
            indices["heat"] = idx
        elif "天数" in cleaned or "days" in cleaned.lower() or "投放" in cleaned or "发布" in cleaned:
            indices["days"] = idx
    
    # 设置默认值
    fallback = {"rank": 0, "name": 1, "type": 2, "platform": 3, "company": None, "change": None, "heat": None, "days": None}
    for key, value in fallback.items():
        if indices[key] is None:
            indices[key] = value
    
    return indices


def cell_text(cells, idx):
    """获取单元格文本"""
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx].inner_text().strip()


def parse_rank(text, fallback_rank):
    """解析排名"""
    if not text:
        return str(fallback_rank)
    match = re.search(r"\d+", text)
    return match.group(0) if match else str(fallback_rank)


def parse_game_name(text):
    """解析游戏名称"""
    if not text:
        return ""
    return text.splitlines()[0].strip()


def parse_company(text):
    """解析开发公司"""
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines[1]
    return ""


def scrape_ranking_table(page, table_selector: str, ranking_name: str = "") -> List[Dict]:
    """
    爬取单个排行榜表格
    
    Args:
        page: Playwright页面对象
        table_selector: 表格选择器
        ranking_name: 排行榜名称
    
    Returns:
        排行榜数据列表
    """
    try:
        # 等待表格加载（使用更宽松的等待）
        try:
            page.wait_for_selector(table_selector, timeout=10000)
        except:
            pass  # 如果超时也继续尝试
        
        table = page.locator(table_selector).first
        
        # 检查表格是否存在
        if table.count() == 0:
            print(f"  ⚠ 未找到表格（选择器: {table_selector}）")
            return []
        
        # 获取表头 - 尝试多种选择器
        headers = []
        header_selectors = [
            "thead tr th",
            "thead tr td",
            "tr:first-child th",
            "tr:first-child td",
            ".el-table__header th",
            ".ant-table-thead th",
            "[class*='header'] th",
            "[class*='Header'] th"
        ]
        
        for selector in header_selectors:
            try:
                headers = table.locator(selector).all_inner_texts()
                if headers:
                    break
            except:
                continue
        
        if not headers:
            print(f"  ⚠ 未能找到表头，尝试直接解析数据行...")
            # 如果没有表头，尝试从第一行推断
        
        column_indices = pick_column_indices(headers) if headers else {"rank": 0, "name": 1, "type": 2, "platform": 3, "company": None, "change": None, "heat": None, "days": None}
        
        # 获取所有行 - 尝试多种选择器
        rows_locator = None
        total_rows = 0
        
        row_selectors = [
            "tbody tr",
            "tbody > tr",
            "tr:not(:first-child)",
            ".el-table__body tr",
            ".ant-table-tbody tr",
            "[class*='body'] tr",
            "[class*='Body'] tr"
        ]
        
        for selector in row_selectors:
            try:
                rows_locator = table.locator(selector)
                total_rows = rows_locator.count()
                if total_rows > 0:
                    break
            except:
                continue
        
        if total_rows == 0:
            # 最后尝试：所有tr，排除表头
            try:
                all_trs = table.locator("tr").all()
                if len(all_trs) > 1:  # 至少有表头和数据行
                    rows_locator = table.locator("tr").nth(1)  # 从第二行开始
                    total_rows = len(all_trs) - 1
            except:
                pass
        
        if total_rows == 0:
            print(f"  ⚠ 未能找到数据行")
            return []
        
        print(f"  [*] {ranking_name}排行榜：发现 {total_rows} 条记录")
        
        results = []
        for i in range(min(total_rows, 50)):  # 最多处理50行
            try:
                if rows_locator.count() > 0:
                    row = rows_locator.nth(i)
                else:
                    # 备用方法：直接通过索引获取
                    row = table.locator("tr").nth(i + 1)  # +1 跳过表头
                
                row.scroll_into_view_if_needed()
                time.sleep(random.uniform(0.1, 0.3))
                
                # 获取单元格 - 尝试多种选择器
                cells = []
                cell_selectors = ["td", "th", "[class*='cell']", "[class*='Cell']"]
                for cell_sel in cell_selectors:
                    try:
                        cells = row.locator(cell_sel).all()
                        if cells:
                            break
                    except:
                        continue
                
                if len(cells) == 0:
                    continue
                
                rank_text = cell_text(cells, column_indices["rank"])
                name_text = cell_text(cells, column_indices["name"])
                type_text = cell_text(cells, column_indices["type"])
                platform_text = cell_text(cells, column_indices["platform"])
                company_text = cell_text(cells, column_indices["company"])
                change_text = cell_text(cells, column_indices["change"])
                heat_text = cell_text(cells, column_indices["heat"])
                days_text = cell_text(cells, column_indices["days"])
                
                game_name = parse_game_name(name_text)
                if not game_name or game_name in ["游戏名称", "名称", "name"]:
                    continue  # 跳过表头行
                
                # 解析排名变化
                rank_change = change_text or "--"
                if rank_change and rank_change != "--":
                    # 提取数字和符号
                    change_match = re.search(r"([+-]?\d+)", rank_change)
                    if change_match:
                        rank_change = change_match.group(1)
                
                # 计算热度指数（如果没有则根据排名计算）
                heat_index = heat_text
                if not heat_index:
                    try:
                        rank_num = int(parse_rank(rank_text, i + 1))
                        heat_index = str(max(0, 100 - (rank_num - 1) * 2))
                    except:
                        heat_index = "50"
                
                # 解析发布时间/投放天数
                publish_time = days_text or ""
                
                # 解析平台
                platform = platform_text or "微信小游戏"
                
                # 解析游戏类型
                game_type = type_text or "休闲游戏"
                
                # 解析开发公司
                company = company_text or parse_company(name_text)
                
                results.append({
                    "排名": parse_rank(rank_text, i + 1),
                    "游戏名称": game_name,
                    "游戏类型": game_type,
                    "热度指数": heat_index,
                    "平台": platform,
                    "发布时间": publish_time,
                    "开发公司": company,
                    "排名变化": rank_change,
                })
            except Exception as e:
                print(f"  ⚠ 处理第 {i+1} 行时出错：{str(e)}")
                continue
        
        print(f"  ✓ {ranking_name}排行榜：成功提取 {len(results)} 条记录")
        return results
        
    except Exception as e:
        print(f"  ✗ 爬取{ranking_name}排行榜时出错：{str(e)}")
        import traceback
        traceback.print_exc()
        return []


def scrape(headless: bool = False, debug: bool = False):
    """
    爬取引力引擎的三个排行榜
    
    Args:
        headless: 是否使用无头模式（False表示显示浏览器窗口，便于调试）
        debug: 是否启用调试模式（会打印更多信息）
    """
    output_dir = resolve_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
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
            viewport={"width": 1920, "height": 1080},
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

        # 收集API响应数据（用于调试和可能的直接数据提取）
        api_responses = []
        
        def handle_response(response):
            """拦截API响应"""
            url = response.url
            # 检查是否是API请求
            if any(keyword in url.lower() for keyword in ['api', 'rank', 'list', 'data', 'query']):
                try:
                    # 尝试获取JSON响应
                    if 'application/json' in response.headers.get('content-type', ''):
                        api_responses.append({
                            'url': url,
                            'status': response.status,
                            'data': response.json()
                        })
                except:
                    pass
        
        page.on("response", handle_response)

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

        # 等待SPA应用加载（更长的等待时间）
        print("[*] 等待页面JavaScript加载...")
        time.sleep(random.uniform(3.0, 5.0))
        
        # 等待页面完全加载（包括所有异步请求）
        try:
            # 等待网络空闲
            page.wait_for_load_state("networkidle", timeout=30000)
        except:
            print("[!] 网络空闲等待超时，继续...")
        
        # 额外等待，确保动态内容已渲染
        time.sleep(2)

        # 等待页面加载完成 - 尝试多种选择器
        print("[*] 等待页面内容加载...")
        selectors_to_wait = [
            "table",
            ".el-table",
            ".ant-table",
            "[class*='table']",
            "[class*='rank']",
            "[class*='list']",
            "tbody tr",
            ".el-table__body",
            ".ant-table-tbody"
        ]
        
        content_loaded = False
        for selector in selectors_to_wait:
            try:
                page.wait_for_selector(selector, timeout=5000)
                print(f"  ✓ 检测到内容元素: {selector}")
                content_loaded = True
                break
            except:
                continue
        
        if not content_loaded:
            print("[-] 未能检测到内容元素，继续尝试...")
        
        # 滚动页面以确保懒加载内容被加载
        print("[*] 滚动页面以加载所有内容...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)
        
        # 调试模式：保存页面截图和HTML
        if debug:
            screenshot_path = output_dir / "page_screenshot.png"
            html_path = output_dir / "page_source.html"
            api_data_path = output_dir / "api_responses.json"
            
            print(f"\n[*] 调试模式: 保存调试文件到 {output_dir}")
            
            try:
                screenshot_path_abs = screenshot_path.resolve()
                page.screenshot(path=str(screenshot_path_abs), full_page=True)
                if screenshot_path_abs.exists():
                    print(f"[*] 页面截图已保存到: {screenshot_path_abs}")
                    print(f"    文件大小: {screenshot_path_abs.stat().st_size} 字节")
                else:
                    print(f"[!] 警告: 截图文件未创建")
            except Exception as e:
                print(f"[!] 保存截图时出错: {str(e)}")
                import traceback
                traceback.print_exc()
            
            try:
                html_path_abs = html_path.resolve()
                html_content = page.content()
                with open(html_path_abs, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                if html_path_abs.exists():
                    print(f"[*] 页面HTML已保存到: {html_path_abs}")
                    print(f"    文件大小: {html_path_abs.stat().st_size} 字节")
                else:
                    print(f"[!] 警告: HTML文件未创建")
            except Exception as e:
                print(f"[!] 保存HTML时出错: {str(e)}")
                import traceback
                traceback.print_exc()
            
            # 保存API响应数据
            if api_responses:
                try:
                    api_data_path_abs = api_data_path.resolve()
                    import json
                    with open(api_data_path_abs, 'w', encoding='utf-8') as f:
                        json.dump(api_responses, f, ensure_ascii=False, indent=2)
                    if api_data_path_abs.exists():
                        print(f"[*] API响应数据已保存到: {api_data_path_abs} (共 {len(api_responses)} 个)")
                    else:
                        print(f"[!] 警告: API数据文件未创建")
                except Exception as e:
                    print(f"[!] 保存API数据时出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
        
        # 如果捕获到API数据，尝试直接解析
        if api_responses and debug:
            print(f"\n[*] 发现 {len(api_responses)} 个API响应，尝试解析...")
            for resp in api_responses:
                print(f"  - {resp['url']}: status={resp['status']}")

        all_results = []

        # 尝试多种方式查找排行榜
        # 方法1: 先查找标签页或切换按钮（通常排行榜网站会有多个标签）
        print("\n[*] 尝试查找标签页或切换按钮...")
        tabs_found = False
        try:
            # 查找可能的标签页选择器（支持多种UI框架）
            tab_selectors = [
                ("[role='tab']", "ARIA tab"),
                (".el-tabs__item", "Element UI tabs"),
                (".ant-tabs-tab", "Ant Design tabs"),
                (".el-tab-pane", "Element UI tab pane"),
                (".ant-tabs-content-item", "Ant Design tab content"),
                ("[class*='tab']", "包含'tab'的class"),
                ("[class*='Tab']", "包含'Tab'的class"),
                (".tab-item", "tab-item class"),
                (".tab-btn", "tab-btn class"),
                ("button[class*='tab']", "button with tab"),
                ("div[class*='tab']", "div with tab"),
                ("[class*='menu']", "menu items"),
                ("[class*='nav']", "nav items"),
            ]
            
            tabs = []
            used_selector = None
            for selector, desc in tab_selectors:
                try:
                    found_tabs = page.locator(selector).all()
                    if found_tabs and len(found_tabs) >= 2:  # 至少要有2个标签才算有效
                        tabs = found_tabs
                        used_selector = selector
                        print(f"  ✓ 使用选择器 '{desc}' ({selector}) 发现 {len(tabs)} 个标签页")
                        tabs_found = True
                        break
                except Exception as e:
                    if debug:
                        print(f"  - 选择器 '{selector}' 检查失败: {str(e)}")
                    continue
            
            if tabs_found and tabs:
                # 限制最多处理3个标签页（三个排行榜）
                max_tabs = min(len(tabs), 3)
                print(f"[*] 将处理前 {max_tabs} 个标签页")
                
                for idx in range(max_tabs):
                    try:
                        tab = tabs[idx]
                        
                        # 获取标签名称（在点击前）
                        ranking_name = tab.inner_text().strip()
                        if not ranking_name:
                            ranking_name = f"排行榜{idx + 1}"
                        
                        print(f"\n[*] 切换到标签 {idx + 1}/{max_tabs}: {ranking_name}")
                        
                        # 点击标签
                        tab.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        tab.click()
                        
                        # 等待内容加载（SPA应用需要等待）
                        time.sleep(2)
                        
                        # 等待表格出现
                        try:
                            page.wait_for_selector("table, .el-table, .ant-table, tbody tr", timeout=5000)
                        except:
                            pass
                        
                        # 额外等待确保数据加载完成
                        time.sleep(1)
                        
                        # 查找当前标签下的表格
                        results = scrape_ranking_table(page, "table", ranking_name)
                        if results:
                            all_results.extend(results)
                        else:
                            # 尝试其他表格选择器
                            for table_sel in ["table", ".el-table", ".ant-table", "[class*='table']", "tbody"]:
                                results = scrape_ranking_table(page, table_sel, ranking_name)
                                if results:
                                    all_results.extend(results)
                                    break
                    except Exception as e:
                        print(f"  ⚠ 处理标签页 {idx + 1} 时出错：{str(e)}")
                        if debug:
                            import traceback
                            traceback.print_exc()
                        continue
            else:
                print("  ⚠ 未找到标签页，将尝试其他方法...")
        except Exception as e:
            print(f"  ⚠ 查找标签页时出错：{str(e)}")
            if debug:
                import traceback
                traceback.print_exc()
        
        # 方法2: 如果没找到标签页，直接查找所有表格
        if len(all_results) == 0:
            print("\n[*] 未找到标签页，尝试查找所有表格...")
            try:
                # 尝试多种表格选择器
                table_selectors = [
                    ("table", "标准table元素"),
                    (".el-table", "Element UI Table"),
                    (".ant-table", "Ant Design Table"),
                    ("[class*='table']", "包含'table'的class"),
                ]
                
                tables = []
                for selector, desc in table_selectors:
                    try:
                        found_tables = page.locator(selector).all()
                        if found_tables:
                            tables = found_tables
                            print(f"  ✓ 使用 '{desc}' 发现 {len(tables)} 个表格")
                            break
                    except:
                        continue
                
                if tables:
                    max_tables = min(len(tables), 3)  # 最多处理3个表格
                    print(f"[*] 将处理前 {max_tables} 个表格")
                    for idx in range(max_tables):
                        ranking_name = f"排行榜{idx + 1}"
                        try:
                            # 尝试使用nth选择器
                            results = scrape_ranking_table(page, f"{selector}:nth-of-type({idx + 1})", ranking_name)
                            if not results:
                                # 如果失败，尝试直接使用索引
                                table = tables[idx]
                                # 这里需要更复杂的逻辑来获取表格选择器
                                results = scrape_ranking_table(page, selector, ranking_name)
                            if results:
                                all_results.extend(results)
                        except Exception as e:
                            print(f"  ⚠ 处理表格 {idx + 1} 时出错：{str(e)}")
                            continue
                else:
                    print("  ⚠ 未找到任何表格")
            except Exception as e:
                print(f"  ⚠ 查找表格时出错：{str(e)}")
                if debug:
                    import traceback
                    traceback.print_exc()

        # 方法3: 如果还是没找到，尝试直接查找第一个表格或任何包含数据的元素
        if len(all_results) == 0:
            print("\n[*] 尝试直接查找第一个表格或数据容器...")
            # 尝试多种选择器
            fallback_selectors = [
                "table:first-of-type",
                "table",
                ".el-table:first-of-type",
                ".ant-table:first-of-type",
                "[class*='table']:first-of-type",
                "tbody:first-of-type",
            ]
            
            for selector in fallback_selectors:
                try:
                    results = scrape_ranking_table(page, selector, "默认排行榜")
                    if results:
                        all_results.extend(results)
                        print(f"  ✓ 使用选择器 '{selector}' 成功提取数据")
                        break
                except Exception as e:
                    if debug:
                        print(f"  - 选择器 '{selector}' 失败: {str(e)}")
                    continue
            
            # 如果还是失败，尝试查找所有包含"排名"或"排行"文本的元素
            if len(all_results) == 0:
                print("[*] 尝试查找包含排名信息的元素...")
                try:
                    # 查找包含排名关键词的父容器
                    rank_containers = page.locator("text=/排名|排行|第.*名/").all()
                    if rank_containers:
                        print(f"  发现 {len(rank_containers)} 个包含排名信息的元素")
                        # 这里可以添加更复杂的解析逻辑
                except:
                    pass

        # 去重（基于游戏名称）
        seen_names = set()
        unique_results = []
        for result in all_results:
            game_name = result.get("游戏名称", "")
            if game_name and game_name not in seen_names:
                seen_names.add(game_name)
                unique_results.append(result)

        # 按排名排序
        try:
            unique_results.sort(key=lambda x: int(x.get("排名", 999)))
        except:
            pass

        # 限制最多10条（如果需要）
        if len(unique_results) > 10:
            unique_results = unique_results[:10]
            print(f"[*] 限制为前10条记录")

        # 保存到CSV
        fieldnames = ["排名", "游戏名称", "游戏类型", "热度指数", "平台", "发布时间", "开发公司", "排名变化"]
        
        with open(output_path, "w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for result in unique_results:
                writer.writerow(result)

        print(f"\n✅ 完成，已保存 {len(unique_results)} 条记录至 {output_path}")
        
        # 保持浏览器打开一段时间以便查看（调试用）
        if debug:
            print("\n[*] 调试模式：浏览器将保持打开10秒，请检查页面...")
            time.sleep(10)
        
        browser.close()


if __name__ == "__main__":
    import sys
    headless = "--headless" in sys.argv
    debug = "--debug" in sys.argv
    scrape(headless=headless, debug=debug)
