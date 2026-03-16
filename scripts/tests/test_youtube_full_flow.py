"""
完整测试：从 YouTube 搜索到本地下载（仅 SensorTower/YouTube 流程）

步骤：
1. 从 .env 读取 RAPIDAPI_KEY / DOUYIN_API_TOKEN（TikHub Token）
2. 使用 YouTubeSearcher.search_videos 搜索玩法视频
3. 选择第一个搜索结果
4. 使用 YouTubeSearcher.download_video（内部优先 TikHub，再回退 yt-dlp）下载到本地

用法示例：
    python3 scripts/tests/test_youtube_full_flow.py
    python3 scripts/tests/test_youtube_full_flow.py "Crossword Go!"
"""

import os
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


def _load_env_file() -> None:
    """从项目根目录的 .env 文件加载环境变量（如果存在）"""
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return

    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                if key and value and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f"⚠ 读取 .env 文件失败：{e}")


def test_youtube_full_flow(game_name: str = "Crossword Go!") -> Optional[str]:
    """从搜索到下载的完整 YouTube 流程测试"""
    from modules.youtube_searcher import YouTubeSearcher
    import config

    print("=" * 60)
    print("测试 YouTube 全流程：搜索 → 获取下载链接 → 本地下载")
    print("=" * 60)
    print(f"测试游戏：{game_name}")
    print()

    # 1. 加载环境变量 & 检查配置
    _load_env_file()

    rapidapi_key = getattr(config, "RAPIDAPI_KEY", "") or os.getenv("RAPIDAPI_KEY", "")
    tikhub_token = (
        getattr(config, "YOUTUBE_API_TOKEN", "")
        or getattr(config, "DOUYIN_API_TOKEN", "")
        or os.getenv("DOUYIN_API_TOKEN", "")
    )

    if not rapidapi_key:
        print("❌ 错误：未配置 RAPIDAPI_KEY，无法搜索 YouTube 视频")
        print("   请在 .env 中设置：RAPIDAPI_KEY=你的_rapidapi_key")
        return None

    print(f"✓ RAPIDAPI_KEY 已配置（长度：{len(rapidapi_key)} 字符）")
    if tikhub_token:
        print(f"✓ TikHub Token 已配置（长度：{len(tikhub_token)} 字符）")
    else:
        print("⚠ 警告：未配置 TikHub Token（DOUYIN_API_TOKEN / YOUTUBE_API_TOKEN）")
        print("   将优先尝试 TikHub，如果失败再回退到 yt-dlp")
    print()

    # 2. 初始化搜索器（这里关闭数据库，避免干扰主流程数据）
    try:
        searcher = YouTubeSearcher(use_database=False)
    except TypeError:
        # 兼容老版本构造函数（没有 use_database 参数）
        searcher = YouTubeSearcher()

    # 3. 搜索视频
    print("【步骤1】搜索 YouTube 视频...")
    try:
        videos = searcher.search_videos(game_name, max_results=3)
    except Exception as e:
        print(f"  ✗ 搜索失败：{e}")
        import traceback

        traceback.print_exc()
        return None

    if not videos:
        print("  ✗ 未找到任何视频结果")
        return None

    print(f"  ✓ 找到 {len(videos)} 个候选视频，前 3 个：")
    for idx, v in enumerate(videos[:3], 1):
        print(f"    [{idx}] {v.get('title', 'N/A')}  ({v.get('views', 0):,} 观看)")
        print(f"         video_id: {v.get('video_id', 'N/A')}")
        print(f"         url     : {v.get('youtube_url', '')[:80]}...")
    print()

    # 取第一个结果
    video_info = videos[0]
    print("【步骤2】选择第一个视频用于下载：")
    print(f"  标题   : {video_info.get('title', 'N/A')}")
    print(f"  video_id: {video_info.get('video_id', 'N/A')}")
    print(f"  作者   : {video_info.get('author_name', 'N/A')}")
    print(f"  观看数 : {video_info.get('views', 0):,}")
    print(f"  URL    : {video_info.get('youtube_url', '')}")
    print()

    # download_video 需要 video_info 里有 game_name 字段
    video_info["game_name"] = game_name

    # 4. 下载视频（内部：优先 TikHub → 回退 yt-dlp）
    print("【步骤3】下载视频到本地...")
    try:
        local_path = searcher.download_video(video_info)
    except Exception as e:
        print(f"  ✗ 下载过程中发生异常：{e}")
        import traceback

        traceback.print_exc()
        return None

    if not local_path:
        print("  ✗ 下载失败（返回 None）")
        return None

    if not os.path.exists(local_path):
        print(f"  ✗ 下载失败，文件不存在：{local_path}")
        return None

    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    print(f"  ✓ 下载成功：{local_path}")
    print(f"    文件大小：{file_size_mb:.2f} MB")
    print()

    print("=" * 60)
    print("测试完成：YouTube 搜索 + 下载完整流程成功")
    print("=" * 60)
    return local_path


if __name__ == "__main__":
    # 允许从命令行传入游戏名
    if len(sys.argv) > 1:
        game = " ".join(sys.argv[1:]).strip()
    else:
        game = "Crossword Go!"

    test_youtube_full_flow(game)

