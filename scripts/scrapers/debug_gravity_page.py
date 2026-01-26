"""
调试脚本：查看引力引擎页面的实际结构 + 记录网络请求

用途：
- 让你先在弹出的浏览器里完成登录/进入榜单/切换三个榜单
- 然后脚本再保存截图、HTML、网络请求清单，帮助我们定位“真实API接口/参数”
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
from pathlib import Path
import json

TARGET_URL = "https://web.gravity-engine.com/#/manage/rank"

def debug_page_structure():
    """调试页面结构"""
    # 确保使用绝对路径
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[*] 输出目录: {output_dir}")
    print(f"[*] 输出目录是否存在: {output_dir.exists()}")
    
    try:
        with sync_playwright() as p:
            # 记录网络请求/响应（用于找排行榜API）
            network_log = []

            def _log_request(request):
                try:
                    network_log.append(
                        {
                            "type": "request",
                            "method": request.method,
                            "url": request.url,
                            "resource_type": request.resource_type,
                            "post_data": request.post_data if request.post_data else None,
                            "headers": dict(request.headers),
                        }
                    )
                except Exception:
                    pass

            def _log_response(response):
                try:
                    ct = response.headers.get("content-type", "")
                    entry = {
                        "type": "response",
                        "url": response.url,
                        "status": response.status,
                        "content_type": ct,
                    }
                    # 只对可能的榜单/数据接口尝试解析JSON，避免文件过大
                    url_lower = response.url.lower()
                    if (
                        "application/json" in ct
                        and any(k in url_lower for k in ["rank", "ranking", "list", "manage", "data", "api"])
                    ):
                        try:
                            entry["json"] = response.json()
                        except Exception:
                            entry["json"] = None
                    network_log.append(entry)
                except Exception:
                    pass

            browser = p.chromium.launch(
                headless=False,  # 显示浏览器
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
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
            )
            page = context.new_page()
            page.set_default_timeout(60000)

            print(f"[*] 访问: {TARGET_URL}")
            page.on("request", _log_request)
            page.on("response", _log_response)

            # 注意：该站点是 SPA，且可能存在持续请求/长连接，等待 networkidle 容易超时。
            # 调试脚本优先确保“能打开页面”，后续由你手动登录/切换榜单触发接口请求。
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120000)
            except PlaywrightTimeout:
                print("[!] domcontentloaded 超时，继续打开浏览器（你可以手动刷新/登录）")
                try:
                    page.goto(TARGET_URL, wait_until="load", timeout=120000)
                except Exception as e:
                    print(f"[!] 二次尝试加载仍失败：{e}（继续执行，可能需要你手动刷新）")

            print("\n" + "=" * 60)
            print("接下来你需要在弹出的浏览器里做两件事：")
            print("1) 如果需要登录：完成登录")
            print("2) 进入榜单页后：把三个排行榜都点一遍（切换tab/榜单类型），让页面把数据请求发出来")
            print("完成后回到这个终端，按回车继续，脚本才会开始保存文件。")
            print("=" * 60 + "\n")
            try:
                input("按回车开始抓取并保存调试文件... ")
            except KeyboardInterrupt:
                print("\n[!] 已取消。")
                browser.close()
                return

            # 给页面一点时间把最后的请求跑完
            time.sleep(2)
            
            # 保存截图
            screenshot_path = output_dir / "debug_screenshot.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                if screenshot_path.exists():
                    print(f"[*] 截图已保存: {screenshot_path}")
                    print(f"    文件大小: {screenshot_path.stat().st_size} 字节")
                else:
                    print(f"[!] 警告: 截图文件未创建: {screenshot_path}")
            except Exception as e:
                print(f"[!] 保存截图时出错: {str(e)}")
                import traceback
                traceback.print_exc()
            
            # 保存HTML
            html_path = output_dir / "debug_page_source.html"
            try:
                html_content = page.content()
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                if html_path.exists():
                    print(f"[*] HTML已保存: {html_path}")
                    print(f"    文件大小: {html_path.stat().st_size} 字节")
                    print(f"    HTML内容长度: {len(html_content)} 字符")
                else:
                    print(f"[!] 警告: HTML文件未创建: {html_path}")
            except Exception as e:
                print(f"[!] 保存HTML时出错: {str(e)}")
                import traceback
                traceback.print_exc()

            # 保存网络日志
            network_path = output_dir / "debug_network.json"
            try:
                with open(network_path, "w", encoding="utf-8") as f:
                    json.dump(network_log, f, ensure_ascii=False, indent=2)
                if network_path.exists():
                    print(f"[*] 网络日志已保存: {network_path}（{len(network_log)} 条）")
            except Exception as e:
                print(f"[!] 保存网络日志时出错: {str(e)}")

            # 额外：打印“排行榜接口 public_list”请求摘要，方便确认是否切到了周榜
            try:
                rank_reqs = [
                    x
                    for x in network_log
                    if x.get("type") == "request"
                    and isinstance(x.get("url"), str)
                    and "apprank/api/v1/rank/public_list" in x.get("url", "")
                ]
                if rank_reqs:
                    print("\n" + "=" * 60)
                    print("public_list 请求摘要（用于确认日榜/周榜/月榜参数）")
                    print("=" * 60)
                    for i, r in enumerate(rank_reqs[-12:], 1):
                        post_data = r.get("post_data") or ""
                        try:
                            payload = json.loads(post_data) if post_data else {}
                        except Exception:
                            payload = {}
                        filters = payload.get("filters") or []
                        filt_kv = {}
                        for f in filters:
                            field = f.get("field")
                            values = f.get("values")
                            if field:
                                filt_kv[field] = values
                        print(f"[{i}] filters={filt_kv}")
                        # 如果有其它关键字段，也打印出来
                        extra = {k: v for k, v in payload.items() if k not in {"filters"}}
                        if extra:
                            print(f"    extra_keys={list(extra.keys())}")
                else:
                    print("\n[*] 未捕获到 public_list 请求（可能还没加载出榜单数据）")
            except Exception:
                pass
            
            # 检查页面元素
            print("\n" + "="*60)
            print("页面结构分析")
            print("="*60)
            
            # 1. 查找所有表格
            tables = page.locator("table").all()
            print(f"\n1. 找到 {len(tables)} 个 <table> 元素")
            
            # 2. 查找标签页
            tab_selectors = [
                ("[role='tab']", "role='tab'"),
                (".el-tabs__item", "Element UI tabs"),
                (".ant-tabs-tab", "Ant Design tabs"),
                ("[class*='tab']", "包含'tab'的class"),
                ("button", "所有button"),
                (".el-button", "Element UI button"),
            ]
            
            print("\n2. 标签页/按钮检查:")
            for selector, desc in tab_selectors:
                try:
                    elements = page.locator(selector).all()
                    if elements:
                        print(f"   {desc}: 找到 {len(elements)} 个元素")
                        # 打印前3个的文本
                        for i, elem in enumerate(elements[:3]):
                            try:
                                text = elem.inner_text().strip()
                                if text:
                                    print(f"      [{i+1}] {text[:50]}")
                            except:
                                pass
                except Exception as e:
                    print(f"   {desc}: 检查失败 - {str(e)}")
            
            # 3. 查找可能的排行榜容器
            print("\n3. 查找可能的排行榜容器:")
            container_selectors = [
                (".el-table", "Element UI Table"),
                (".ant-table", "Ant Design Table"),
                ("[class*='table']", "包含'table'的class"),
                ("[class*='rank']", "包含'rank'的class"),
                ("[class*='list']", "包含'list'的class"),
            ]
            
            for selector, desc in container_selectors:
                try:
                    elements = page.locator(selector).all()
                    if elements:
                        print(f"   {desc}: 找到 {len(elements)} 个元素")
                except:
                    pass
            
            # 4. 检查页面标题和主要文本
            print("\n4. 页面主要文本:")
            try:
                title = page.title()
                print(f"   页面标题: {title}")
            except:
                pass
            
            # 5. 查找所有包含"排名"或"排行"的元素
            print("\n5. 查找包含'排名'或'排行'的元素:")
            try:
                rank_elements = page.locator("text=/排名|排行/").all()
                print(f"   找到 {len(rank_elements)} 个相关元素")
                for i, elem in enumerate(rank_elements[:5]):
                    try:
                        text = elem.inner_text().strip()
                        print(f"      [{i+1}] {text[:100]}")
                    except:
                        pass
            except Exception as e:
                print(f"   检查失败: {str(e)}")
            
            # 6. 检查是否有iframe
            print("\n6. 检查iframe:")
            iframes = page.locator("iframe").all()
            print(f"   找到 {len(iframes)} 个iframe")
            
            # 7. 打印页面中所有可见的文本（前500字符）
            print("\n7. 页面可见文本预览:")
            try:
                body_text = page.locator("body").inner_text()
                print(f"   {body_text[:500]}...")
            except:
                pass
            
            print("\n" + "="*60)
            print("分析完成！请查看保存的截图和HTML文件")
            print("="*60)
            print("\n浏览器将保持打开30秒，请手动检查页面...")
            time.sleep(30)
            
            browser.close()
    except Exception as e:
        print(f"\n[!] 脚本执行出错: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"\n请检查:")
        print(f"  1. Playwright 是否已安装: pip install playwright")
        print(f"  2. 浏览器驱动是否已安装: playwright install chromium")
        print(f"  3. 网络连接是否正常")

if __name__ == "__main__":
    debug_page_structure()
