"""
简化版调试脚本 - 确保文件能够被保存
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
import time
import sys

TARGET_URL = "https://web.gravity-engine.com/#/manage/rank"

def main():
    # 确保使用绝对路径
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"=" * 60)
    print(f"引力引擎页面调试脚本")
    print(f"=" * 60)
    print(f"\n输出目录: {output_dir}")
    print(f"目标URL: {TARGET_URL}\n")
    
    try:
        print("[1/5] 启动浏览器...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            
            print("[2/5] 创建浏览器上下文...")
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = context.new_page()
            page.set_default_timeout(60000)
            
            print(f"[3/5] 访问网站: {TARGET_URL}")
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)
                print("  ✓ 页面加载完成")
            except Exception as e:
                print(f"  ⚠ 页面加载超时或出错: {str(e)}")
                print("  继续尝试...")
            
            print("[4/5] 等待页面渲染...")
            time.sleep(5)
            
            # 保存截图
            screenshot_path = output_dir / "debug_screenshot.png"
            print(f"\n[5/5] 保存截图到: {screenshot_path}")
            try:
                page.screenshot(path=str(screenshot_path.resolve()), full_page=True)
                if screenshot_path.exists():
                    size = screenshot_path.stat().st_size
                    print(f"  ✓ 截图保存成功 ({size} 字节)")
                else:
                    print(f"  ✗ 截图文件未创建")
            except Exception as e:
                print(f"  ✗ 保存截图失败: {str(e)}")
                import traceback
                traceback.print_exc()
            
            # 保存HTML
            html_path = output_dir / "debug_page_source.html"
            print(f"\n保存HTML到: {html_path}")
            try:
                html_content = page.content()
                with open(html_path.resolve(), 'w', encoding='utf-8') as f:
                    f.write(html_content)
                if html_path.exists():
                    size = html_path.stat().st_size
                    print(f"  ✓ HTML保存成功 ({size} 字节)")
                else:
                    print(f"  ✗ HTML文件未创建")
            except Exception as e:
                print(f"  ✗ 保存HTML失败: {str(e)}")
                import traceback
                traceback.print_exc()
            
            # 分析页面结构
            print(f"\n分析页面结构...")
            try:
                tables = page.locator("table").all()
                print(f"  - 找到 {len(tables)} 个表格")
                
                tabs = page.locator("[role='tab'], .el-tabs__item, .ant-tabs-tab").all()
                print(f"  - 找到 {len(tabs)} 个标签页")
                
                body_text = page.locator("body").inner_text()[:200]
                print(f"  - 页面文本预览: {body_text}...")
            except Exception as e:
                print(f"  ⚠ 分析失败: {str(e)}")
            
            print(f"\n浏览器将保持打开10秒...")
            time.sleep(10)
            
            browser.close()
            print("✓ 完成！\n")
            
    except Exception as e:
        print(f"\n✗ 脚本执行出错: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
