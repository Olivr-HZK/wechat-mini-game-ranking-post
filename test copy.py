from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
import time

# 设置 Chrome 的无头模式（可选）
chrome_options = Options()
chrome_options.add_argument("--headless")  # 启动无头浏览器

# 启动 Chrome 浏览器
print("启动浏览器中...")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    # 打开目标网址
    url = "https://web.gravity-engine.com/#/manage/rank"
    print(f"打开网址: {url}")
    driver.get(url)

    # 等待页面加载完成
    time.sleep(5)
    print("当前页面标题:", driver.title)
    print("当前 URL:", driver.current_url)

    # 1. 尝试点击“周榜”按钮
    try:
        print("尝试查找“周榜”按钮...")
        week_button = driver.find_element(
            By.XPATH,
            "//div[contains(@class,'button-item') and contains(normalize-space(.), '周榜')]"
        )
        print("找到“周榜”按钮，点击它...")
        week_button.click()
    except NoSuchElementException:
        print("没有找到“周榜”按钮！请检查 XPath 是否正确，或者页面是否已经完全加载。")
        # 打印一小段页面源码帮助排查
        page_source_snippet = driver.page_source[:2000]
        print("页面源码前 2000 字符：")
        print(page_source_snippet)
        raise

    # 2. 等待周榜数据加载
    print("等待周榜数据加载...")
    time.sleep(5)

    # 3. 获取榜单信息（根据你提供的 DOM 结构）
    # 每一条是一个包含多种 class 的 div，例如：class="flex items-center w-full rank-item"
    print("尝试获取榜单元素...")
    ranks = driver.find_elements(By.XPATH, "//div[contains(@class,'rank-item')]")
    print(f"找到榜单元素数量: {len(ranks)}")

    if not ranks:
        print("没有找到任何榜单元素，请检查榜单的 XPath 是否正确。")

    for i, rank in enumerate(ranks, start=1):
        try:
            # 排名序号：左侧的数字或图标里的数字
            index_text = rank.find_element(
                By.XPATH, ".//div[contains(@class,'rank-index')]//span[contains(@class,'index')]"
            ).text
        except NoSuchElementException:
            index_text = ""

        try:
            # 游戏名称：加粗文本，例如 “羊了个羊：星球”
            name_text = rank.find_element(
                By.XPATH, ".//span[contains(@class,'font-bold')]"
            ).text
        except NoSuchElementException:
            name_text = ""

        try:
            # 描述区域：包含 “休闲: 1名 厂商名称” 等
            desc_div = rank.find_element(
                By.XPATH, ".//div[contains(@class,'desc')]"
            )
            desc_text = desc_div.text
        except NoSuchElementException:
            desc_text = ""

        try:
            # 涨跌 / 新进榜 等标签，如 “3”、“新进榜” 等
            tag_text = rank.find_element(
                By.XPATH, ".//span[contains(@class,'el-tag__content')]"
            ).text
        except NoSuchElementException:
            tag_text = ""

        try:
            # 周平均排名：包含 “周平均排名:” 的那一行
            avg_div = rank.find_element(
                By.XPATH, ".//div[contains(@class,'desc') and contains(normalize-space(.), '周平均排名')]"
            )
            avg_text = avg_div.text
        except NoSuchElementException:
            avg_text = ""

        print(f"第 {i} 条：")
        print(f"  排名: {index_text}")
        print(f"  名称: {name_text}")
        print(f"  描述: {desc_text}")
        print(f"  标签: {tag_text}")
        print(f"  周平均排名: {avg_text}")

finally:
    print("关闭浏览器。")
    driver.quit()
