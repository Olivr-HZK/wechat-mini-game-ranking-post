# Google Drive上传功能设置指南

## 功能说明

系统可以将本地视频上传到Google Drive，并获取公开访问链接，供Gemini模型分析使用。这样可以解决抖音视频URL无法被Gemini访问的问题。

## 设置步骤

### 1. 安装依赖

```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

或者使用requirements.txt：

```bash
pip install -r requirements.txt
```

### 2. 创建Google Cloud项目

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 启用 **Google Drive API**：
   - 在左侧菜单选择"API和服务" > "库"
   - 搜索"Google Drive API"
   - 点击"启用"

### 3. 配置OAuth同意屏幕（重要！）

**这是解决"403: access_denied"错误的关键步骤！**

1. 在左侧菜单选择"API和服务" > "OAuth同意屏幕"
2. 选择用户类型：
   - **选择"外部"**（个人使用可以选择"内部"，但需要Google Workspace）
   - 点击"创建"
3. 填写应用信息：
   - **应用名称**：填写你的应用名称（如"Game Video Analyzer"或"video_test"）
   - **用户支持电子邮件**：选择你的邮箱
   - **开发者联系信息**：填写你的邮箱
   - 点击"保存并继续"
4. **添加测试用户（关键步骤！）**：
   - 在"测试用户"部分，点击"+ 添加用户"
   - **输入你的Google账号邮箱**（例如：Oliverplatinum@outlook.com）
   - 点击"添加"
   - **重要**：确保添加的邮箱与你登录时使用的邮箱一致
5. 作用域（Scopes）：
   - 点击"保存并继续"
   - 系统会自动添加必要的权限
6. 摘要：
   - 检查信息无误后，点击"返回到信息中心"

**注意**：
- 如果应用还在"测试"状态，只有添加到"测试用户"列表的邮箱才能使用
- 添加测试用户后，可能需要等待几分钟才能生效
- 如果仍然无法访问，请检查邮箱是否正确添加

### 4. 创建OAuth2凭证

1. 在左侧菜单选择"API和服务" > "凭证"
2. 点击"创建凭证" > "OAuth客户端ID"
3. 创建OAuth客户端ID：
   - 应用类型选择"桌面应用"
   - 名称可以自定义（如"Game Video Analyzer Client"）
   - 点击"创建"
4. 下载JSON凭证文件：
   - 点击下载按钮
   - 将文件重命名为 `credentials.json` 或 `credential.json`
   - 放在项目根目录

### 4. 首次使用

运行程序时，会自动打开浏览器进行OAuth认证：

1. 选择你的Google账号
2. 授权应用访问Google Drive
3. 认证完成后，会在项目根目录生成 `token.json` 文件
4. 之后使用时会自动使用保存的token，无需重复认证

## 使用方法

### 自动上传（推荐）

当视频分析时，如果：
- 没有可用的视频URL（抖音URL无法访问）
- 但有本地视频文件

系统会自动尝试上传到Google Drive并使用公开链接进行分析。

### 手动上传

你也可以创建一个脚本来手动上传视频：

```python
from modules.gdrive_uploader import GoogleDriveUploader

uploader = GoogleDriveUploader()
result = uploader.upload_video(
    video_path="data/videos/合成大西瓜_6921925411651865871.mp4",
    folder_name="Game Videos"
)

if result:
    print(f"文件ID: {result['file_id']}")
    print(f"公开链接: {result['public_url']}")
```

## 注意事项

1. **存储空间**：Google Drive免费账户有15GB存储空间，注意管理上传的视频
2. **公开访问**：上传的视频会被设置为"任何人可查看"，确保不包含敏感内容
3. **文件组织**：所有视频会上传到"Game Videos"文件夹，便于管理
4. **Token过期**：如果token过期，系统会自动刷新或重新认证

## 故障排除

### 问题1：找不到credentials.json

**错误信息**：`FileNotFoundError: 未找到凭证文件`

**解决方法**：
- 确保已下载OAuth2凭证文件
- 将文件重命名为 `credentials.json`
- 放在项目根目录（与main.py同级）

### 问题2：认证失败

**错误信息**：`认证失败` 或 `刷新token时出错`

**解决方法**：
- 删除 `token.json` 文件
- 重新运行程序，会重新进行OAuth认证
- 确保已添加你的邮箱为测试用户（在OAuth同意屏幕配置中）

### 问题3：上传失败

**错误信息**：`上传到Google Drive时出错`

**解决方法**：
- 检查网络连接
- 确认Google Drive API已启用
- 检查视频文件是否存在且可读
- 查看详细错误信息进行排查

## 链接格式说明

Google Drive上传后会生成两种链接：

1. **直接下载链接**（用于Gemini）：
   ```
   https://drive.google.com/uc?export=download&id=FILE_ID
   ```

2. **网页查看链接**（用于浏览器查看）：
   ```
   https://drive.google.com/file/d/FILE_ID/view?usp=sharing
   ```

系统会自动使用直接下载链接，确保Gemini可以访问视频内容。
