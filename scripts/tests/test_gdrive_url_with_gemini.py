"""
测试Google Drive链接是否能被Gemini访问
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
import json
import config
from modules.video_analyzer import VideoAnalyzer


def test_gdrive_url_with_gemini(gdrive_url: str, game_name: str = "测试游戏"):
    """
    测试Google Drive链接是否能被Gemini访问
    
    Args:
        gdrive_url: Google Drive直接下载链接
        game_name: 游戏名称
    """
    print("=" * 60)
    print("测试Google Drive链接与Gemini")
    print("=" * 60)
    print()
    
    print(f"Google Drive链接：{gdrive_url}")
    print()
    
    if not config.OPENROUTER_API_KEY:
        print("❌ 错误：未配置OpenRouter API密钥")
        print("请在.env文件中设置 OPENROUTER_API_KEY")
        return False
    
    print(f"使用模型：{config.VIDEO_ANALYSIS_MODEL}")
    print()
    print("-" * 60)
    print("发送测试请求...")
    print("-" * 60)
    print()
    
    # 构建测试提示词
    prompt = f"""请分析这个游戏视频，重点关注以下两个方面：

1. **核心玩法解析**：简要说明游戏的核心玩法机制和操作方式

2. **吸引力分析**：分析游戏的吸引点和特色，为什么玩家会喜欢这个游戏

游戏名称：{game_name}

请用中文简洁清晰地描述，每个部分控制在200字以内。"""
    
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo",
        "X-Title": "Game Video Analyzer"
    }
    
    # 构建请求内容
    content_items = [
        {
            "type": "text",
            "text": prompt
        },
        {
            "type": "video_url",
            "video_url": {
                "url": gdrive_url
            }
        }
    ]
    
    payload = {
        "model": config.VIDEO_ANALYSIS_MODEL,
        "messages": [
            {
                "role": "user",
                "content": content_items
            }
        ],
        "max_tokens": 8000
    }
    
    try:
        print(f"  发送API请求到 {config.OPENROUTER_BASE_URL}/chat/completions...")
        print(f"  注意：视频分析可能需要较长时间，请耐心等待...")
        print()
        
        response = requests.post(
            f"{config.OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=180
        )
        
        if response.status_code == 200:
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                choice = result['choices'][0]
                analysis_text = choice['message']['content']
                finish_reason = choice.get('finish_reason', 'unknown')
                
                print("=" * 60)
                print("✅ 测试成功！Gemini可以访问Google Drive链接")
                print("=" * 60)
                print()
                print("分析结果：")
                print("-" * 60)
                print(analysis_text)
                print("-" * 60)
                print()
                print(f"完成原因：{finish_reason}")
                print(f"文本长度：{len(analysis_text)} 字符")
                return True
            else:
                print("❌ API响应格式异常")
                print(f"响应内容：{json.dumps(result, indent=2, ensure_ascii=False)}")
                return False
        else:
            error_text = response.text[:500] if response.text else "无错误信息"
            print(f"❌ API请求失败：HTTP {response.status_code}")
            print(f"错误信息：{error_text}")
            
            if response.status_code == 400:
                print()
                print("可能的原因：")
                print("1. Google Drive链接无法被Gemini访问")
                print("2. 视频文件格式不支持")
                print("3. 链接格式不正确")
            
            return False
            
    except Exception as e:
        print(f"❌ 测试时出错：{str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法：python test_gdrive_url_with_gemini.py <Google_Drive_链接> [游戏名称]")
        print()
        print("示例：")
        print("  python test_gdrive_url_with_gemini.py \"https://drive.google.com/uc?export=download&id=158-st1pjUzGyo6vT-fyD3aRWDZhEEYkf\" \"合成大西瓜\"")
        sys.exit(1)
    
    gdrive_url = sys.argv[1]
    game_name = sys.argv[2] if len(sys.argv) > 2 else "测试游戏"
    
    success = test_gdrive_url_with_gemini(gdrive_url, game_name)
    sys.exit(0 if success else 1)
