"""
单独测试 TikHub YouTube API 下载功能
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import http.client
import json
import os
import re

# 直接从 .env 文件读取
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
                    # 移除引号
                    value = value.strip('"\'')
                    env_vars[key] = value
    return env_vars

# 加载环境变量
env_vars = load_env_file()
for key, value in env_vars.items():
    os.environ[key] = value


def test_tikhub_youtube_api():
    """测试 TikHub YouTube API 获取视频信息"""
    
    video_id = "x_1TdOK8ftM"  # 从测试中获取的视频ID
    
    print("=" * 60)
    print("测试 TikHub YouTube API")
    print("=" * 60)
    print(f"视频ID: {video_id}")
    print()
    
    # 获取 Token（直接从环境变量读取）
    token = os.getenv("DOUYIN_API_TOKEN", "")
    
    if not token:
        print("❌ 错误：未配置 DOUYIN_API_TOKEN")
        print("请在 .env 文件中设置 DOUYIN_API_TOKEN")
        return
    
    print(f"✓ Token 已配置（长度：{len(token)} 字符）")
    print(f"  Token 前缀：{token[:30]}...")
    print()
    
    # 调用 API
    print("【步骤1】调用 TikHub API 获取视频信息...")
    print(f"  端点：/api/v1/youtube/web/get_video_info")
    print(f"  参数：video_id={video_id}, lang=zh-CN")
    print()
    
    try:
        conn = http.client.HTTPSConnection("api.tikhub.io")
        
        # 尝试不同的参数组合
        endpoints = [
            f"/api/v1/youtube/web/get_video_info?video_id={video_id}&lang=zh-CN",
            f"/api/v1/youtube/web/get_video_info?video_id={video_id}",
            f"/api/v1/youtube/web/get_video_info?video_id={video_id}&url_access=null&lang=zh-CN&videos=null&audios=null&subtitles=null&related=null",
        ]
        
        headers = {
            'Authorization': f'Bearer {token}'
        }
        
        for idx, endpoint in enumerate(endpoints, 1):
            print(f"  尝试 {idx}/{len(endpoints)}: {endpoint[:80]}...")
            
            try:
                conn.request("GET", endpoint, "", headers)
                res = conn.getresponse()
                data = res.read()
                
                print(f"    状态码：{res.status}")
                
                if res.status == 200:
                    result = json.loads(data.decode("utf-8"))
                    print(f"    ✓ 请求成功")
                    print(f"    API 响应 code: {result.get('code', 'N/A')}")
                    print(f"    API 响应 message: {result.get('message', 'N/A')}")
                    print(f"    API 响应 message_zh: {result.get('message_zh', 'N/A')}")
                    
                    # 打印完整的响应数据（用于调试）
                    print(f"\n  完整响应数据：")
                    full_response = json.dumps(result, indent=2, ensure_ascii=False)
                    print(full_response)
                    
                    # 保存到文件以便查看
                    output_file = Path(__file__).parent.parent.parent / "data" / f"tikhub_response_{video_id}.json"
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    print(f"\n  响应已保存到：{output_file}")
                    
                    # 检查是否有数据
                    video_data = result.get("data")
                    if video_data:
                        print(f"\n  ✓ 获取到视频数据")
                        
                        # 尝试提取视频下载链接
                        print(f"\n  【步骤2】提取视频下载链接...")
                        
                        video_url = None
                        
                        # 从 data.videos.items 中提取（根据实际 API 响应结构）
                        if isinstance(video_data, dict):
                            print(f"  视频数据字段：{list(video_data.keys())}")
                            
                            # 从 data.videos.items 中提取
                            videos_obj = video_data.get("videos", {})
                            if videos_obj and isinstance(videos_obj, dict):
                                videos_items = videos_obj.get("items", [])
                                if videos_items and len(videos_items) > 0:
                                    print(f"  找到 {len(videos_items)} 个视频格式")
                                    
                                    # 优先选择包含音频的 mp4 格式（itag=18 通常是 360p 带音频）
                                    for item in videos_items:
                                        mime_type = item.get("mimeType", "")
                                        quality = item.get("quality", "")
                                        has_audio = item.get("hasAudio", False)
                                        
                                        # 优先选择：mp4 格式，有音频，720p 以下
                                        if mime_type.startswith("video/mp4") and has_audio:
                                            height = item.get("height", 0)
                                            if height <= 720:
                                                video_url = item.get("url")
                                                print(f"  选择格式：{quality} ({mime_type}), 大小：{item.get('sizeText', 'N/A')}, 有音频")
                                                break
                                    
                                    # 如果还没找到，选择第一个 mp4 格式
                                    if not video_url:
                                        for item in videos_items:
                                            if item.get("mimeType", "").startswith("video/mp4"):
                                                video_url = item.get("url")
                                                quality = item.get("quality", "unknown")
                                                print(f"  选择格式：{quality} ({item.get('mimeType', '')}), 大小：{item.get('sizeText', 'N/A')}")
                                                break
                                    
                                    # 如果还没找到，使用第一个视频
                                    if not video_url and videos_items:
                                        video_url = videos_items[0].get("url")
                                        quality = videos_items[0].get("quality", "unknown")
                                        print(f"  使用第一个格式：{quality}, 大小：{videos_items[0].get('sizeText', 'N/A')}")
                            
                            if video_url:
                                print(f"  ✓ 找到视频下载链接：{video_url[:100]}...")
                                return video_url
                            else:
                                print(f"  ⚠ 未找到视频下载链接")
                                print(f"  可用的字段：{list(video_data.keys())}")
                    else:
                        print(f"  ⚠ API 返回的 data 字段为空")
                    
                    conn.close()
                    break
                    
                elif res.status == 403:
                    error_body = data.decode("utf-8") if data else ""
                    print(f"    ❌ 403 错误（认证失败）")
                    print(f"    错误响应：{error_body[:300]}")
                    print(f"\n    💡 可能的原因：")
                    print(f"      1. Token 无效或已过期")
                    print(f"      2. Token 没有访问 YouTube API 的权限")
                    print(f"      3. 需要在 TikHub 控制台启用 YouTube API")
                    if idx < len(endpoints):
                        print(f"    继续尝试下一个端点...")
                        conn.close()
                        conn = http.client.HTTPSConnection("api.tikhub.io")
                        continue
                    else:
                        conn.close()
                        return
                else:
                    error_body = data.decode("utf-8") if data else ""
                    print(f"    ❌ 请求失败，状态码：{res.status}")
                    print(f"    错误响应：{error_body[:300]}")
                    if idx < len(endpoints):
                        print(f"    继续尝试下一个端点...")
                        conn.close()
                        conn = http.client.HTTPSConnection("api.tikhub.io")
                        continue
                    else:
                        conn.close()
                        return
                        
            except Exception as e:
                print(f"    ❌ 请求异常：{str(e)}")
                if idx < len(endpoints):
                    print(f"    继续尝试下一个端点...")
                    conn.close()
                    conn = http.client.HTTPSConnection("api.tikhub.io")
                    continue
                else:
                    conn.close()
                    return
        
        conn.close()
        
    except Exception as e:
        print(f"❌ 测试失败：{str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_tikhub_youtube_api()
