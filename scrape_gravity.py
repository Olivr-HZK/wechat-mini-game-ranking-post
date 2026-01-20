"""
爬取引力引擎排行榜的独立脚本

使用方法:
    python scrape_gravity.py           # 显示浏览器窗口（推荐，便于调试）
    python scrape_gravity.py --headless # 无头模式（后台运行）
    python scrape_gravity.py --debug    # 调试模式（保存页面截图和HTML）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.GravityScraper import scrape

if __name__ == "__main__":
    headless = "--headless" in sys.argv
    debug = "--debug" in sys.argv
    scrape(headless=headless, debug=debug)
