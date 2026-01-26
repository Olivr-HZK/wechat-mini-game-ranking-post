# 小游戏热榜玩法解析日报工作流

这是一个自动化工作流系统，用于分析小游戏热榜上的游戏玩法，并生成日报通过飞书机器人发送。

## 功能模块

1. **排行提取模块** (`modules/rank_extractor.py`)
   - 从CSV文件中提取游戏排行榜信息
   - 支持限制提取数量

2. **搜索下载视频模块** (`modules/video_searcher.py`)
   - 通过抖音搜索API搜索游戏相关视频
   - **自动筛选**：只搜索"玩法"和"演示"关键词，时长限制在1分钟以内
   - 下载视频到本地并保存视频信息（URL和ID）
   - **数据库存储**：搜索结果自动保存到SQLite数据库
   - 当API不可用时自动降级到Mock模式

3. **数据库模块** (`modules/database.py`)
   - 使用SQLite数据库存储视频信息
   - 支持视频信息查询和统计
   - 自动记录搜索关键词和下载状态

4. **视频分析模块** (`modules/video_analyzer.py`)
   - 使用OpenRouter API调用多模态模型分析视频
   - 支持GPT-4o、Claude等支持视频的模型
   - 当API不可用时自动使用Mock数据

5. **生成日报模块** (`modules/report_generator.py`)
   - 根据分析结果生成格式化的日报
   - 支持Markdown格式和飞书卡片格式

6. **飞书发送模块** (`modules/feishu_sender.py`)
   - 通过飞书Webhook发送日报
   - 支持文本、Markdown和卡片格式

## 安装

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量：
创建 `.env` 文件（参考 `env_example.txt`）：
```
OPENROUTER_API_KEY=your_openrouter_api_key_here
VIDEO_ANALYSIS_MODEL=openai/gpt-4o
FEISHU_WEBHOOK_URL=your_feishu_webhook_url_here
DOUYIN_API_TOKEN=your_douyin_api_token_here
MAX_GAMES_TO_PROCESS=5
```

### 获取抖音API Token

1. 访问 [TikHub](https://tikhub.io) 网站
2. 注册并登录账户
3. 进入用户中心，点击"API令牌"菜单
4. 创建API令牌并复制
5. 将令牌配置到 `.env` 文件中的 `DOUYIN_API_TOKEN`

## 安装依赖

```bash
pip install -r requirements.txt

# 安装 Playwright 浏览器（用于爬取排行榜）
playwright install chromium
```

## 使用方法

### 完整工作流

运行完整的工作流（爬取排行榜 → 搜索视频 → 分析 → 生成日报 → 发送）：

```bash
python main.py
```

指定处理游戏数量：

```bash
python main.py 10
```

跳过爬取步骤（使用现有CSV文件）：

```bash
python main.py --skip-scrape
```

只执行爬取步骤：

```bash
python main.py --scrape-only
```

### 选择平台

通过 `--platform` 参数选择抖音或微信小游戏榜单：

```bash
# 选择抖音小游戏榜单
python main.py --platform dy

# 选择微信小游戏榜单
python main.py --platform wx

# 默认不限制，选择最新的CSV文件
python main.py
```

### 单独执行视频搜索

使用独立的视频搜索脚本，只执行视频搜索功能：

```bash
# 从排行榜搜索前5个游戏的视频
python scripts/tools/search_videos.py --top 5

# 搜索单个游戏的视频
python scripts/tools/search_videos.py --game "羊了个羊"

# 搜索并下载视频
python scripts/tools/search_videos.py --top 3 --download

# 每个游戏搜索多个结果
python scripts/tools/search_videos.py --top 5 --max-results 3

# 查看帮助
python scripts/tools/search_videos.py --help
```

**视频搜索脚本参数说明：**
- `--top N` / `-t N`: 从排行榜搜索前N个游戏的视频
- `--game NAME` / `-g NAME`: 搜索单个游戏的视频
- `--max-results N` / `-m N`: 每个游戏搜索的最大结果数（默认: 1）
- `--download` / `-d`: 下载找到的视频（默认: 仅保存信息）
- `--no-summary`: 不保存搜索摘要（仅在使用--top时有效）

## 配置说明

### OpenRouter API配置

- `OPENROUTER_API_KEY`: OpenRouter API密钥
- `VIDEO_ANALYSIS_MODEL`: 使用的模型名称，推荐：
  - `openai/gpt-4o` - GPT-4o（支持视频）
  - `anthropic/claude-3.5-sonnet` - Claude 3.5 Sonnet
  - 其他支持视频的多模态模型

### 飞书机器人配置

1. 在飞书群聊中添加"自定义机器人"
2. 获取Webhook URL
3. 将URL配置到 `FEISHU_WEBHOOK_URL`

### 排行榜数据

排行榜数据存储在 `data/人气榜/` 目录下，支持两种平台：
- **抖音小游戏**：文件名以 `dy_` 开头（如 `dy_2026-1-19~2026-1-25.csv`）
- **微信小游戏**：普通文件名（如 `2026-1-19~2026-1-25.csv`）

CSV文件格式包含以下字段：
- 排名
- 游戏名称
- 游戏类型
- 标签
- 热度指数
- 平台
- 来源
- 榜单
- 监控日期
- 发布时间
- 开发公司
- 排名变化

## 工作流程

完整工作流包含以下步骤：

1. **步骤0：爬取排行榜** → 从引力引擎网站爬取游戏排行榜（可选，可使用现有CSV）
2. **步骤1：提取排行榜** → 从CSV文件读取游戏信息
3. **步骤2：搜索下载视频** → 为每个游戏搜索并下载相关视频
4. **步骤3：分析视频** → 使用AI模型分析游戏玩法
5. **步骤4：生成日报** → 将所有分析结果整合成日报
6. **步骤5：发送日报** → 通过飞书机器人发送日报

可以通过 `--steps` 参数指定执行的步骤：

```bash
# 只执行步骤1和2
python main.py --steps 1,2

# 只执行步骤3
python main.py --step 3
```

## 项目结构

```
.
├── main.py                    # 主程序入口（工作流）
├── config.py                  # 配置文件
├── requirements.txt           # Python依赖
├── README.md                  # 说明文档
├── env_example.txt            # 环境变量示例
│
├── modules/                   # 核心功能模块
│   ├── __init__.py
│   ├── rank_extractor.py      # 排行提取
│   ├── video_searcher.py      # 视频搜索下载
│   ├── video_analyzer.py      # 视频分析
│   ├── report_generator.py    # 日报生成
│   ├── feishu_sender.py       # 飞书发送
│   ├── wecom_sender.py        # 企业微信发送
│   ├── database.py            # 数据库操作
│   ├── gdrive_uploader.py     # Google Drive上传
│   ├── GravityScraper.py      # 引力引擎爬虫
│   └── DEScraper.py           # DataEye爬虫
│
├── scripts/                   # 脚本目录
│   ├── scrapers/              # 爬取脚本
│   │   ├── scrape_weekly_popularity.py    # 爬取周榜
│   │   ├── scrape_gravity.py              # 爬取引力引擎
│   │   ├── scrape_and_parse_gravity.py    # 爬取并解析
│   │   ├── parse_gravity_rank_from_html.py
│   │   ├── parse_gravity_rank_text.py
│   │   └── debug_gravity_page.py
│   │
│   ├── tools/                 # 工具脚本
│   │   ├── search_videos.py                # 视频搜索工具
│   │   ├── upload_existing_videos_to_gdrive.py
│   │   ├── update_game_info.py
│   │   ├── write_rankings_to_google_sheet.py
│   │   ├── re_search_videos.py
│   │   └── migrate_database.py
│   │
│   ├── tests/                 # 测试脚本
│   │   ├── test_download.py
│   │   ├── test_video_analysis.py
│   │   ├── test_report.py
│   │   └── ...
│   │
│   ├── utils/                 # 工具/清理脚本
│   │   ├── clear_database.py
│   │   ├── clear_all_gameplay_videos.py
│   │   ├── delete_game_data.py
│   │   └── ...
│   │
│   └── senders/               # 发送脚本
│       ├── send_single_game_to_feishu.py
│       ├── send_single_game_to_wecom.py
│       └── ...
│
├── docs/                      # 文档目录
│   ├── WORKFLOW_GUIDE.md      # 工作流指南
│   ├── GOOGLE_DRIVE_SETUP.md  # Google Drive设置
│   ├── GRAVITY_SCRAPER_README.md
│   └── ...
│
└── data/                      # 数据目录
    ├── 人气榜/                 # 排行榜CSV文件
    │   ├── dy_*.csv           # 抖音小游戏榜单
    │   └── *.csv              # 微信小游戏榜单
    ├── videos/                # 视频文件目录
    ├── videos.db              # SQLite数据库
    └── step*_*.json           # 工作流中间产物
```

## 其他脚本使用

### 爬取排行榜

```bash
# 爬取周榜（默认微信小游戏）
python scripts/scrapers/scrape_weekly_popularity.py

# 爬取抖音小游戏周榜
python scripts/scrapers/scrape_weekly_popularity.py --platform douyin

# 爬取引力引擎排行榜
python scripts/scrapers/scrape_gravity.py
```

### 测试功能

运行测试脚本测试视频搜索和下载：

```bash
python scripts/tests/test_download.py
```

这个脚本会：
1. 从排行榜获取前3个游戏
2. 搜索每个游戏的视频（筛选：1分钟以内，玩法演示）
3. 下载找到的视频
4. 显示数据库统计信息

### 工具脚本

```bash
# 上传已有视频到Google Drive
python scripts/tools/upload_existing_videos_to_gdrive.py

# 更新游戏信息
python scripts/tools/update_game_info.py

# 写入排行榜到Google Sheet
python scripts/tools/write_rankings_to_google_sheet.py
```

### 清理脚本

```bash
# 清理数据库
python scripts/utils/clear_database.py

# 删除指定游戏数据
python scripts/utils/delete_game_data.py "游戏名称"
```

## 注意事项

1. **抖音API**：需要配置TikHub的API Token才能使用视频搜索功能，未配置时会自动使用Mock数据
2. **视频筛选逻辑**：
   - 使用多个关键词搜索（玩法、怎么玩、演示、玩法演示）
   - 收集所有关键词搜索到的视频
   - 统一去重（基于视频ID）
   - 统一按点赞量排序
   - 选择点赞量最高的那一条作为该游戏的玩法视频
   - 只搜索1分钟以内的视频
3. **数据库存储**：搜索结果自动保存到SQLite数据库 `data/videos.db`，视频文件保存在 `data/videos/` 目录
4. **下载方式（简化逻辑）**：
   - **方式1**：优先使用免费的video_url直接下载（默认方式）
   - **方式2**：如果普通URL下载失败，且配置了 `USE_HIGH_QUALITY_API_FALLBACK=true`，自动使用付费的最高画质API（0.005$一次）
5. **成本控制**：系统优先使用免费URL下载，只有在免费方式失败时才会使用付费API，最大程度节省成本
6. **视频选择**：每个游戏只下载点赞量最高的那一条视频
4. **API限制**：OpenRouter和抖音API可能有调用频率限制，请注意控制处理速度
5. **视频大小**：大视频文件可能需要较长的处理时间，建议使用短视频或视频片段
6. **飞书消息长度**：飞书消息有长度限制，长日报可能会被截断

## 数据存储

### 数据库存储

搜索到的视频信息会自动保存到SQLite数据库 `data/videos.db` 中，包含以下信息：
- 视频ID (`aweme_id`)
- 视频URL (`video_url` 和 `video_urls`)
- 游戏名称、标题、描述
- 作者信息、统计信息
- 搜索关键词
- 下载状态和本地路径
- 创建和更新时间

### 视频搜索筛选条件

系统会自动应用以下筛选条件：
- **关键词**：只搜索"玩法"和"演示"相关视频
- **时长**：只搜索1分钟以内的视频（`filter_duration: "0-1"`）
- **内容类型**：只搜索视频内容（`content_type: "1"`）
- **排序方式**：按最多点赞排序（`sort_type: "1"`）

### 视频信息存储（旧方式，已废弃）

如果禁用数据库（`use_database=False`），视频信息会以JSON格式保存在 `data/video_info/` 目录下，文件名格式为：`{游戏名}_{视频ID}.json`

每个JSON文件包含以下信息：
- `aweme_id`: 抖音视频ID
- `video_url`: 视频播放地址
- `video_urls`: 所有可用的视频地址列表
- `title`: 视频标题
- `description`: 视频描述
- `author_name`: 作者名称
- `duration`: 视频时长（秒）
- `like_count`: 点赞数
- `comment_count`: 评论数
- `play_count`: 播放数
- 等其他详细信息

## 扩展开发

### 修改视频搜索策略

可以在 `modules/video_searcher.py` 的 `search_videos` 方法中修改搜索关键词列表，调整视频筛选逻辑。

### 使用其他AI模型

修改 `config.py` 中的 `VIDEO_ANALYSIS_MODEL` 配置，或直接修改 `modules/video_analyzer.py` 中的模型调用逻辑。

### 自定义日报格式

修改 `modules/report_generator.py` 中的 `generate_daily_report` 方法，自定义日报的格式和内容。

## 许可证

MIT License