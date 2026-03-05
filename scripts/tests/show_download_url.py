"""
显示 YouTube 视频的下载链接
说明链接的特性和是否可以手动下载
"""
import sys
from pathlib import Path
import json

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def show_download_url():
    """显示下载链接信息"""
    
    print("=" * 80)
    print("YouTube 视频下载链接说明")
    print("=" * 80)
    print()
    
    # 从 JSON 响应文件中读取视频 URL
    response_file = Path(__file__).parent.parent.parent / "data" / "tikhub_response_x_1TdOK8ftM.json"
    
    if not response_file.exists():
        print(f"❌ 错误：找不到响应文件：{response_file}")
        print("   请先运行 test_tikhub_youtube_download.py 生成响应文件")
        return
    
    print(f"【步骤1】读取 API 响应文件...")
    print(f"  文件路径：{response_file}")
    
    with open(response_file, 'r', encoding='utf-8') as f:
        response_data = json.load(f)
    
    # 提取视频信息
    video_data = response_data.get("data", {})
    video_id = video_data.get("id", "")
    video_title = video_data.get("title", "")
    
    print(f"  视频ID: {video_id}")
    print(f"  视频标题: {video_title}")
    print()
    
    # 提取视频 URL
    videos_obj = video_data.get("videos", {})
    videos_items = videos_obj.get("items", [])
    
    if not videos_items:
        print("  ❌ 未找到视频格式")
        return
    
    print(f"【步骤2】视频下载链接信息")
    print(f"  找到 {len(videos_items)} 个视频格式")
    print()
    
    # 显示所有格式的链接
    for idx, item in enumerate(videos_items[:3], 1):  # 只显示前3个
        quality = item.get("quality", "unknown")
        mime_type = item.get("mimeType", "")
        size_text = item.get("sizeText", "N/A")
        has_audio = item.get("hasAudio", False)
        video_url = item.get("url", "")
        
        print(f"  格式 {idx}: {quality}")
        print(f"    - 类型: {mime_type}")
        print(f"    - 大小: {size_text}")
        print(f"    - 包含音频: {'是' if has_audio else '否'}")
        print(f"    - 下载链接: {video_url[:100]}...")
        print()
    
    # 选择最佳格式
    selected_format = None
    video_url = None
    
    for item in videos_items:
        mime_type = item.get("mimeType", "")
        quality = item.get("quality", "")
        has_audio = item.get("hasAudio", False)
        
        if mime_type.startswith("video/mp4") and has_audio:
            height = item.get("height", 0)
            if height <= 720:
                video_url = item.get("url")
                selected_format = item
                break
    
    if not video_url:
        selected_format = videos_items[0]
        video_url = selected_format.get("url")
    
    print(f"【步骤3】推荐下载链接（已选择最佳格式）")
    print(f"  格式: {selected_format.get('quality', 'unknown')}")
    print(f"  大小: {selected_format.get('sizeText', 'N/A')}")
    print()
    print(f"  完整下载链接：")
    print(f"  {video_url}")
    print()
    
    print("=" * 80)
    print("关于下载链接的说明")
    print("=" * 80)
    print()
    print("1. 链接类型：")
    print("   - 这是 Google Video 的直链下载地址")
    print("   - 格式：https://rrX---sn-XXXXX.googlevideo.com/videoplayback?...")
    print()
    print("2. 链接特性：")
    print("   ✅ 可以直接在浏览器中打开")
    print("   ✅ 浏览器会自动开始下载视频文件")
    print("   ✅ 支持断点续传（如果浏览器支持）")
    print("   ⚠️  链接有时效性（通常几小时内有效）")
    print("   ⚠️  链接包含 IP 和签名验证，可能限制访问来源")
    print()
    print("3. 手动下载方法：")
    print("   ⚠️  注意：浏览器会直接播放视频，不会自动下载")
    print()
    print("   方法1：使用浏览器右键菜单")
    print("   - 在浏览器中打开链接")
    print("   - 右键点击视频或页面")
    print("   - 选择\"视频另存为\"或\"Save video as\"")
    print()
    print("   方法2：使用命令行工具（推荐）")
    print(f"   - 使用 wget: wget -O video.mp4 \"{video_url[:80]}...\"")
    print(f"   - 使用 curl: curl -L -o video.mp4 \"{video_url[:80]}...\"")
    print(f"   - 使用 aria2: aria2c \"{video_url[:80]}...\"")
    print()
    print("   方法3：使用 Python requests（程序方式）")
    print("   - 运行: python3 scripts/tests/test_download_video_from_url.py")
    print()
    print("4. 注意事项：")
    print("   ⚠️  如果链接过期，需要重新调用 API 获取新链接")
    print("   ⚠️  某些链接可能包含 IP 验证，需要从特定 IP 访问")
    print("   ⚠️  如果下载失败，可能是链接已过期或网络问题")
    print()
    print("5. 测试链接：")
    print(f"   可以尝试在浏览器中打开以下链接测试：")
    print(f"   {video_url[:150]}...")
    print()
    print("=" * 80)
    
    # 生成一个简单的 HTML 文件用于测试
    html_file = Path(__file__).parent.parent.parent / "data" / "test_download_link.html"
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>YouTube 视频下载链接测试</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
        }}
        .info {{
            background: #f0f0f0;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .link {{
            background: #e8f4f8;
            padding: 10px;
            border-radius: 5px;
            word-break: break-all;
            margin: 10px 0;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .warning {{
            background: #fff3cd;
            padding: 10px;
            border-left: 4px solid #ffc107;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <h1>YouTube 视频下载链接测试</h1>
    
    <div class="info">
        <h2>视频信息</h2>
        <p><strong>视频ID:</strong> {video_id}</p>
        <p><strong>视频标题:</strong> {video_title}</p>
        <p><strong>格式:</strong> {selected_format.get('quality', 'unknown')}</p>
        <p><strong>大小:</strong> {selected_format.get('sizeText', 'N/A')}</p>
    </div>
    
    <div class="warning">
        <strong>⚠️ 注意：</strong>此链接有时效性，如果无法下载，可能需要重新获取。
    </div>
    
    <h2>下载链接</h2>
    <div class="link">
        <a href="{video_url}" download="video.mp4">点击这里下载视频</a>
    </div>
    
    <p>或者复制以下链接到浏览器地址栏：</p>
    <div class="link">
        <code>{video_url}</code>
    </div>
    
    <h2>说明</h2>
    <ul>
        <li>点击上面的链接，浏览器会自动开始下载视频</li>
        <li>如果链接过期，需要重新调用 API 获取新链接</li>
        <li>某些链接可能包含 IP 验证，需要从特定 IP 访问</li>
    </ul>
</body>
</html>
"""
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ 已生成测试 HTML 文件：{html_file}")
    print(f"  可以在浏览器中打开此文件测试下载链接")
    print()


if __name__ == "__main__":
    show_download_url()
