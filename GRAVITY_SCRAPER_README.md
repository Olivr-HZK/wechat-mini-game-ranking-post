# 引力引擎排行榜爬虫使用说明

## 功能说明

这个爬虫用于爬取 https://web.gravity-engine.com/#/manage/rank 网站上的三个排行榜数据。

## 使用方法

### 基本使用

```bash
# 显示浏览器窗口（推荐，便于查看和调试）
python scrape_gravity.py

# 无头模式（后台运行）
python scrape_gravity.py --headless

# 调试模式（会保存页面截图、HTML和API响应数据到data目录）
python scrape_gravity.py --debug
```

### 调试页面结构

如果需要查看页面的实际结构，可以运行：

```bash
python debug_gravity_page.py
```

这会：
- 打开浏览器并访问网站
- 你先在浏览器里完成登录/进入榜单，并把三个榜单都点一遍
- 回到终端按回车后，脚本才会开始保存：
  - `data/debug_screenshot.png`（截图）
  - `data/debug_page_source.html`（HTML）
  - `data/debug_network.json`（网络请求/响应日志，用来定位排行榜API）
- 分析并打印页面结构信息
- 浏览器保持打开30秒供手动检查

## 输出文件

爬取的数据会保存到 `data/game_rankings.csv`，包含以下字段：
- 排名
- 游戏名称
- 游戏类型
- 热度指数
- 平台
- 发布时间
- 开发公司
- 排名变化

## 工作原理

1. **访问网站**：使用 Playwright 打开目标网页
2. **等待加载**：等待SPA应用完全加载（包括JavaScript执行和API请求）
3. **查找标签页**：自动识别并切换三个排行榜标签页
4. **解析表格**：从每个标签页中提取表格数据
5. **数据清洗**：去重、排序并格式化数据
6. **保存CSV**：将结果保存为CSV文件

## 调试功能

使用 `--debug` 参数时，会额外保存：
- `data/page_screenshot.png` - 页面完整截图
- `data/page_source.html` - 页面HTML源码
- `data/api_responses.json` - 拦截到的API响应数据（如果有）

## 注意事项

1. **首次运行**：Playwright 需要下载浏览器驱动，可能需要一些时间
2. **网络要求**：需要能够访问目标网站
3. **等待时间**：SPA应用需要时间加载，脚本已设置合理的等待时间
4. **反爬虫**：如果网站有反爬虫机制，可能需要调整等待时间或添加更多延迟

## 故障排除

如果爬取失败，可以：

1. **使用调试模式**查看页面实际结构：
   ```bash
   python scrape_gravity.py --debug
   ```

2. **检查保存的截图和HTML**文件，了解页面结构

3. **查看控制台输出**，了解脚本执行到哪一步

4. **手动访问网站**，确认网站可正常访问

5. **检查网络连接**，确保能够访问目标域名

## 代码结构

- `modules/GravityScraper.py` - 主爬虫模块
- `scrape_gravity.py` - 独立运行脚本
- `debug_gravity_page.py` - 页面结构调试脚本
