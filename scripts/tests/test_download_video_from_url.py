"""
测试从 URL 直接下载视频
从 TikHub API 响应中提取 URL 并测试下载
"""
import sys
from pathlib import Path
import json
import os
import requests

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def load_env_file():
    """从 .env 文件读取环境变量"""
    env_vars = {}
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip('"\'')
                    env_vars[key] = value
    return env_vars


def test_download_from_url():
    """测试从 URL 下载视频"""
    
    print("=" * 60)
    print("测试从 URL 下载视频")
    print("=" * 60)
    
    # 1. 从 JSON 响应文件中读取视频 URL
    response_file = Path(__file__).parent.parent.parent / "data" / "tikhub_response_x_1TdOK8ftM.json"
    
    if not response_file.exists():
        print(f"❌ 错误：找不到响应文件：{response_file}")
        print("   请先运行 test_tikhub_youtube_download.py 生成响应文件")
        return
    
    print(f"【步骤1】读取 API 响应文件...")
    print(f"  文件路径：{response_file}")
    
    with open(response_file, 'r', encoding='utf-8') as f:
        response_data = json.load(f)
    
    # 提取视频 URL
    video_data = response_data.get("data", {})
    videos_obj = video_data.get("videos", {})
    videos_items = videos_obj.get("items", [])
    
    if not videos_items:
        print("  ❌ 未找到视频格式")
        return
    
    print(f"  ✓ 找到 {len(videos_items)} 个视频格式")
    
    # 选择包含音频的 mp4 格式（优先选择 360p）
    video_url = None
    selected_format = None
    
    for item in videos_items:
        mime_type = item.get("mimeType", "")
        quality = item.get("quality", "")
        has_audio = item.get("hasAudio", False)
        
        if mime_type.startswith("video/mp4") and has_audio:
            height = item.get("height", 0)
            if height <= 720:
                video_url = item.get("url")
                selected_format = item
                print(f"  ✓ 选择格式：{quality} ({mime_type})")
                print(f"    大小：{item.get('sizeText', 'N/A')}")
                print(f"    宽度x高度：{item.get('width', 0)}x{item.get('height', 0)}")
                break
    
    if not video_url:
        print("  ⚠ 未找到包含音频的 mp4 格式，使用第一个格式")
        selected_format = videos_items[0]
        video_url = selected_format.get("url")
        print(f"  选择格式：{selected_format.get('quality', 'unknown')}")
    
    print()
    print(f"【步骤2】准备下载视频...")
    print(f"  视频 URL：{video_url[:100]}...")
    print(f"  预计大小：{selected_format.get('sizeText', 'N/A')}")
    print()
    
    # 2. 创建输出目录
    output_dir = Path(__file__).parent.parent.parent / "data" / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 3. 下载视频
    video_id = "x_1TdOK8ftM"
    output_path = output_dir / f"test_download_{video_id}.mp4"
    
    print(f"【步骤3】开始下载...")
    print(f"  保存路径：{output_path}")
    print()
    
    try:
        # 使用 requests 下载
        response = requests.get(video_url, stream=True, timeout=120)
        
        if response.status_code != 200:
            print(f"  ❌ 下载失败，HTTP 状态码：{response.status_code}")
            print(f"  响应内容：{response.text[:200]}")
            return
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        
        print(f"  文件大小：{total_size / 1024 / 1024:.2f} MB")
        print()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    if total_size > 0:
                        percent = (downloaded_size / total_size) * 100
                        # 每下载 1MB 打印一次进度
                        if downloaded_size % (1024 * 1024) == 0 or downloaded_size == total_size:
                            print(f"  下载进度：{percent:.1f}% ({downloaded_size / 1024 / 1024:.2f} MB / {total_size / 1024 / 1024:.2f} MB)", end='\r')
        
        print()  # 换行
        
        # 4. 验证下载
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print()
            print(f"【步骤4】验证下载结果...")
            print(f"  ✓ 文件已保存")
            print(f"  文件路径：{output_path}")
            print(f"  文件大小：{file_size / 1024 / 1024:.2f} MB")
            
            if file_size < 1024:
                print(f"  ⚠ 警告：文件大小异常小（{file_size} 字节），可能下载不完整")
            elif total_size > 0 and abs(file_size - total_size) > 1024:
                print(f"  ⚠ 警告：文件大小不匹配（期望：{total_size} 字节，实际：{file_size} 字节）")
            else:
                print(f"  ✓ 文件大小正常")
            
            print()
            print("=" * 60)
            print("✓ 下载测试成功！")
            print("=" * 60)
            print(f"视频文件：{output_path}")
        else:
            print(f"  ❌ 文件不存在")
            
    except requests.exceptions.Timeout:
        print(f"  ❌ 下载超时（超过 120 秒）")
    except requests.exceptions.RequestException as e:
        print(f"  ❌ 下载失败：{str(e)}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"  ❌ 发生错误：{str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_download_from_url()
