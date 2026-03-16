# 工作流使用指南

## 当前状态检查

在运行完整工作流之前，建议先检查当前状态：

### 1. 检查数据库中的视频状态

```bash
python -c "from modules.database import VideoDatabase; db = VideoDatabase(); videos = db.get_all_videos(); print(f'总视频数: {len(videos)}'); print(f'已下载: {sum(1 for v in videos if v.get(\"downloaded\") == 1)}'); print(f'有Google Drive链接: {sum(1 for v in videos if v.get(\"gdrive_url\"))}'); print(f'有分析结果: {sum(1 for v in videos if v.get(\"gameplay_analysis\"))}')"
```

## 推荐的工作流程

### 方案1：已有视频但缺少Google Drive链接

如果你的数据库中已有视频，但还没有上传到Google Drive：

```bash
# 1. 为已有视频上传到Google Drive
python upload_existing_videos_to_gdrive.py

# 或者只上传特定游戏
python upload_existing_videos_to_gdrive.py 合成大西瓜

# 2. 运行视频分析（会自动使用gdrive_url）
python test_video_analysis.py
```

### 方案2：全新开始（推荐）

如果你想重新运行完整工作流，系统会自动：
1. 搜索视频
2. 下载视频
3. **自动上传到Google Drive**（新功能）
4. 使用Google Drive链接进行分析
5. 保存分析结果

```bash
# 运行完整工作流
python main.py
```

### 方案3：只分析已有视频

如果数据库中已有视频和Google Drive链接，只想进行分析：

```bash
# 运行分析（会自动检查数据库中的分析结果）
python test_video_analysis.py
```

## 工作流步骤说明

### 步骤1：搜索和下载视频
- 系统会搜索游戏相关视频
- 下载点赞量最高的视频
- **自动上传到Google Drive并保存URL**

### 步骤2：AI分析
- 检查数据库是否已有分析结果
  - **如果有，直接返回（不调用API）**
  - 如果没有，继续分析
- 从数据库获取Google Drive URL
- 使用Google Drive URL进行分析
- 保存分析结果到数据库

### 步骤3：生成报告
- 从数据库读取分析结果
- 生成JSON格式的日报
- 发送到飞书

## 重要提示

1. **避免重复分析**：系统会自动检查数据库，如果已有分析结果，不会重复调用API
2. **Google Drive上传**：视频下载后会自动上传，无需手动操作
3. **数据持久化**：所有数据保存在数据库中，包括：
   - 视频信息
   - Google Drive链接
   - 分析结果

## 常见场景

### 场景1：第一次运行
```bash
python main.py
```
系统会完整执行所有步骤。

### 场景2：已有视频，需要上传到Google Drive
```bash
python upload_existing_videos_to_gdrive.py
python test_video_analysis.py
```

### 场景3：已有所有数据，只想生成报告
```bash
python test_report.py
```

## 检查数据状态

查看数据库中"合成大西瓜"的状态：

```python
from modules.database import VideoDatabase

db = VideoDatabase()
videos = db.get_videos_by_game("合成大西瓜")

if videos:
    v = videos[0]
    print(f"视频ID: {v.get('aweme_id')}")
    print(f"已下载: {v.get('downloaded') == 1}")
    print(f"本地路径: {v.get('local_path')}")
    print(f"Google Drive链接: {v.get('gdrive_url', '无')}")
    print(f"有分析结果: {bool(v.get('gameplay_analysis'))}")
```
