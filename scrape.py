from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time

# 设置浏览器驱动
driver = webdriver.Chrome(executable_path='chromedriver.exe')

# 打开网页
driver.get('https://web.gravity-engine.com/#/manage/rank')  # 替换为目标网站URL

# 等待网页加载
time.sleep(2)  # 可以根据情况调整时间，或者使用显性等待

# 找到按钮并点击
button = driver.find_element(By.ID, 'button_id')  # 替换为按钮的ID或者其他定位方式
button.click()

# 等待榜单信息加载
time.sleep(2)  # 根据网页的加载速度调整时间

# 获取榜单信息
# 示例：获取榜单项
rankings = driver.find_elements(By.CLASS_NAME, 'ranking_class')  # 替换为榜单项的class

# 打印榜单信息
for rank in rankings:
    print(rank.text)

# 关闭浏览器
driver.quit()
