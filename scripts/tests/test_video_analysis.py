"""
测试视频分析功能
使用GPT-4o分析合成大西瓜的视频
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
from modules.video_analyzer import VideoAnalyzer
import config


def test_video_analysis():
    """测试视频分析功能"""
    print("=" * 60)
    print("测试视频分析功能")
    print("=" * 60)
    print()
    
    # 初始化分析器
    analyzer = VideoAnalyzer()
    
    # 检查API配置
    if not analyzer.api_key:
        print("警告：未配置OpenRouter API密钥")
        print("请在.env文件中设置 OPENROUTER_API_KEY")
        print("将使用Mock分析结果进行测试\n")
    else:
        print(f"使用模型：{analyzer.model}")
        print(f"API密钥：{'已配置' if analyzer.api_key else '未配置'}\n")
    
    # 查找合成大西瓜的视频
    video_dir = config.VIDEOS_DIR
    game_name = "合成大西瓜"
    
    print(f"查找游戏视频：{game_name}")
    print(f"视频目录：{video_dir}\n")
    
    # 查找视频文件
    video_files = []
    if os.path.exists(video_dir):
        for file in os.listdir(video_dir):
            if file.startswith(game_name) and file.endswith('.mp4'):
                video_path = os.path.join(video_dir, file)
                video_files.append(video_path)
    
    if not video_files:
        print(f"错误：未找到 {game_name} 的视频文件")
        print(f"请确保视频文件在 {video_dir} 目录下")
        print(f"文件名格式应为：{game_name}_*.mp4")
        return
    
    # 使用第一个找到的视频
    video_path = video_files[0]
    file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
    
    print(f"找到视频文件：{os.path.basename(video_path)}")
    print(f"文件大小：{file_size:.2f} MB")
    print()
    
    # 游戏信息
    game_info = {
        "游戏名称": game_name,
        "游戏类型": "合成类"
    }
    
    # 分析视频
    print("=" * 60)
    print("开始分析视频...")
    print("=" * 60)
    print()
    
    analysis = analyzer.analyze_video(
        video_path=video_path,
        game_name=game_name,
        game_info=game_info
    )
    
    if not analysis:
        print("分析失败")
        return
    
    # 显示分析结果
    print("\n" + "=" * 60)
    print("分析结果")
    print("=" * 60)
    print()
    print(f"游戏名称：{analysis.get('game_name', 'N/A')}")
    print(f"使用模型：{analysis.get('model_used', 'N/A')}")
    print(f"分析状态：{analysis.get('status', 'N/A')}")
    print()
    print("玩法解析：")
    print("-" * 60)
    print(analysis.get('analysis', '无分析内容'))
    print("-" * 60)
    
    # 保存分析结果
    output_file = f"data/analysis_{game_name}_{os.path.basename(video_path).replace('.mp4', '')}.txt"
    try:
        os.makedirs("data", exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"游戏名称：{analysis.get('game_name', 'N/A')}\n")
            f.write(f"使用模型：{analysis.get('model_used', 'N/A')}\n")
            f.write(f"分析状态：{analysis.get('status', 'N/A')}\n")
            f.write(f"\n玩法解析：\n")
            f.write("=" * 60 + "\n")
            f.write(analysis.get('analysis', '无分析内容'))
            f.write("\n" + "=" * 60 + "\n")
        
        print(f"\n分析结果已保存到：{output_file}")
    except Exception as e:
        print(f"\n保存分析结果时出错：{str(e)}")


if __name__ == "__main__":
    test_video_analysis()