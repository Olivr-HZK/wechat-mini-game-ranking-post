"""
删除数据库中指定游戏的数据
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.database import VideoDatabase


def delete_game_data(game_name: str):
    """
    删除指定游戏的所有数据
    
    Args:
        game_name: 游戏名称
    """
    print("=" * 60)
    print(f"删除游戏数据：{game_name}")
    print("=" * 60)
    print()
    
    # 初始化数据库
    db = VideoDatabase()
    
    # 先查看该游戏的数据
    videos = db.get_videos_by_game(game_name)
    print(f"找到 {len(videos)} 条关于 '{game_name}' 的记录：")
    print("-" * 60)
    
    for idx, video in enumerate(videos, 1):
        print(f"{idx}. 视频ID: {video.get('aweme_id')}")
        print(f"   标题: {video.get('title', 'N/A')}")
        print(f"   视频URL: {video.get('video_url', 'N/A')[:50]}...")
        print(f"   本地路径: {video.get('local_path', 'N/A')}")
        print()
    
    if len(videos) == 0:
        print("未找到相关数据，无需删除")
        return
    
    # 确认删除
    print("-" * 60)
    confirm = input(f"确认删除以上 {len(videos)} 条记录吗？(yes/no): ")
    
    if confirm.lower() in ['yes', 'y', '是', '确认']:
        deleted_count = db.delete_game_data(game_name)
        print()
        print(f"✓ 已成功删除 {deleted_count} 条记录")
        
        # 显示删除后的统计信息
        stats = db.get_statistics()
        print()
        print("当前数据库统计：")
        print(f"  总视频数: {stats.get('total_videos', 0)}")
        print(f"  已下载数: {stats.get('downloaded_videos', 0)}")
        print(f"  游戏数: {stats.get('unique_games', 0)}")
    else:
        print("已取消删除操作")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        game_name = sys.argv[1]
    else:
        game_name = "合成大西瓜"
    
    delete_game_data(game_name)