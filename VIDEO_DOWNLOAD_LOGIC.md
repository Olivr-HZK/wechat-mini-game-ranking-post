# 视频下载逻辑说明

## 当前实现

### 1. 视频信息获取

当搜索视频时，系统会：

1. **调用搜索API** (`/api/v1/douyin/search/fetch_general_search_v3`)
   - 使用游戏名称 + "玩法"/"演示"/"教程" 等关键词搜索
   - 返回视频列表

2. **提取视频信息** (`_extract_video_info` 方法)
   - 从API响应中提取关键信息：
     - `aweme_id`: 视频唯一ID（**重要**）
     - `video_url`: 视频播放地址（第一个URL）
     - `video_urls`: 所有可用的视频URL列表
     - 其他信息（标题、作者、统计等）

3. **保存视频信息** (`save_video_info` 方法)
   - 将完整的视频信息保存为JSON文件
   - 文件路径：`data/video_info/{游戏名}_{aweme_id}.json`
   - **包含aweme_id和所有video_urls**

### 2. 视频下载方式（优先级顺序）

系统支持三种下载方式，按优先级自动选择：

#### 优先级1：直接下载URL（免费，默认）

**逻辑：**
```python
download_video(video_info)
```

1. 从 `video_info` 中获取 `video_url`
2. 使用 `requests.get(video_url, stream=True)` 直接下载
3. 保存到 `data/videos/{游戏名}_{aweme_id}.mp4`

**优点：**
- 免费，不需要额外API调用
- 简单直接

**缺点：**
- 某些URL可能有防盗链或时效性限制
- 可能无法获取最高清晰度

**如果失败，自动尝试优先级2**

#### 优先级2：使用最高画质API（付费，0.005$一次，备用方案）

**配置方式：**
在 `.env` 文件中设置：
```
USE_HIGH_QUALITY_API_FALLBACK=true
```

**逻辑：**
1. 当普通URL下载失败时，自动调用最高画质API
2. 使用 `aweme_id` 或 `share_url` 调用 `/api/v1/douyin/app/v3/fetch_video_high_quality_play_url`
3. 获取 `original_video_url`（最高画质，原始上传画质）
4. 下载最高画质视频

**优点：**
- 获取最高画质视频（原始上传画质）
- 无水印
- 适合视频编辑、存档、训练模型等场景

**缺点：**
- 需要付费（0.005$一次）
- 需要API Token

**注意：** 系统优先使用免费URL，只有在免费方式失败时才会使用此API，最大程度节省成本。

#### 优先级3：使用下载API（可选）

**配置方式：**
在 `.env` 文件中设置：
```
USE_DOWNLOAD_API=true
DOUYIN_DOWNLOAD_ENDPOINT=/api/v1/douyin/video/download
```

**逻辑：**
```python
download_video(video_info, use_download_api=True)
```

1. 使用 `aweme_id` 调用下载API
2. API返回视频URL或视频数据
3. 下载并保存视频

**优点：**
- 可能获取更稳定的下载链接
- 支持更多清晰度选项
- 符合API服务商的推荐方式

### 3. 只获取ID和URL（不下载）

如果只需要获取 `aweme_id` 和 `url`，可以使用：

```python
searcher = VideoSearcher()
video_list = searcher.get_video_ids_and_urls(
    game_name="羊了个羊",
    max_results=5
)

# 返回格式：
# [
#     {
#         "aweme_id": "7123456789",
#         "video_url": "https://...",
#         "video_urls": ["https://...", "https://..."],
#         "title": "视频标题",
#         "game_name": "羊了个羊"
#     },
#     ...
# ]
```

**注意：**
- 视频信息会自动保存到 `data/video_info/` 目录
- 不会下载视频文件本身

## 数据存储

### 视频信息JSON文件

每个视频的信息保存在：
```
data/video_info/{游戏名}_{aweme_id}.json
```

**文件内容示例：**
```json
{
  "aweme_id": "7123456789",
  "game_name": "羊了个羊",
  "title": "羊了个羊玩法演示",
  "description": "视频描述...",
  "video_url": "https://...",
  "video_urls": [
    "https://...",
    "https://..."
  ],
  "cover_url": "https://...",
  "author_name": "作者名",
  "author_uid": "123456",
  "duration": 120.5,
  "like_count": 10000,
  "comment_count": 500,
  "play_count": 100000,
  "create_time": 1234567890,
  "share_url": "https://..."
}
```

### 视频文件

如果下载了视频，保存在：
```
data/videos/{游戏名}_{aweme_id}.mp4
```

## 使用建议

### 场景1：只需要ID和URL，后续用其他API下载

```python
from modules.video_searcher import VideoSearcher

searcher = VideoSearcher()

# 只获取ID和URL，不下载
videos = searcher.get_video_ids_and_urls("羊了个羊", max_results=5)

for video in videos:
    aweme_id = video["aweme_id"]
    video_url = video["video_url"]
    
    # 使用你自己的下载API
    # your_download_api(aweme_id, video_url)
```

### 场景2：使用系统自带的下载功能

```python
from modules.video_searcher import VideoSearcher

searcher = VideoSearcher()

# 搜索并下载（使用默认方式）
video_path = searcher.search_and_download("羊了个羊")

# 或指定使用下载API
video_info = searcher.search_video("羊了个羊")
if video_info:
    video_path = searcher.download_video(video_info, use_download_api=True)
```

### 场景3：批量获取ID和URL

```python
from modules.rank_extractor import RankExtractor
from modules.video_searcher import VideoSearcher

extractor = RankExtractor()
searcher = VideoSearcher()

games = extractor.get_top_games(top_n=5)

all_videos = []
for game in games:
    game_name = game["游戏名称"]
    videos = searcher.get_video_ids_and_urls(game_name, max_results=1)
    all_videos.extend(videos)

# all_videos 包含所有视频的aweme_id和url
```

## 配置说明

### 环境变量

在 `.env` 文件中：

```bash
# 抖音搜索API Token（必需）
DOUYIN_API_TOKEN=your_token_here

# 是否使用下载API（可选，默认false）
USE_DOWNLOAD_API=false

# 下载API端点（如果使用下载API，需要配置）
DOUYIN_DOWNLOAD_ENDPOINT=/api/v1/douyin/video/download
```

## 注意事项

1. **aweme_id 是必需的**：所有下载方式都需要 `aweme_id`
2. **video_url 可能有多个**：`video_urls` 列表包含所有可用URL
3. **URL可能有时效性**：某些URL可能在一段时间后失效
4. **下载API格式**：如果使用下载API，需要根据实际API文档调整 `_download_via_api` 方法中的请求格式

## 扩展开发

如果需要使用其他下载API，可以：

1. 修改 `_download_via_api` 方法，调整请求格式
2. 或创建新的下载方法
3. 或直接使用 `get_video_ids_and_urls` 获取ID和URL，然后自己实现下载逻辑