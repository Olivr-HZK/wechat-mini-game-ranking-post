"""
重新搜索并更新视频数据（提取原视频URL）
"""
from modules.video_searcher import VideoSearcher
from modules.database import VideoDatabase


def re_search_and_update(game_name: str = None):
    """
    重新搜索视频并更新数据库中的原视频URL
    
    Args:
        game_name: 游戏名称，如果为None则更新所有游戏
    """
    print("=" * 60)
    print("重新搜索视频并更新原视频URL")
    print("=" * 60)
    print()
    
    db = VideoDatabase()
    searcher = VideoSearcher()
    
    # 获取要更新的游戏列表
    if game_name:
        games = [game_name]
        print(f"目标游戏：{game_name}\n")
    else:
        # 获取数据库中所有不重复的游戏名称
        videos = db.get_all_videos()
        games = list(set([v.get("game_name") for v in videos if v.get("game_name")]))
        print(f"找到 {len(games)} 个游戏，将逐一更新\n")
    
    total_updated = 0
    
    for idx, game in enumerate(games, 1):
        print(f"[{idx}/{len(games)}] 处理游戏：{game}")
        print("-" * 60)
        
        # 搜索视频
        videos = searcher.search_videos(game_name=game, max_results=1)
        
        if not videos:
            print(f"  ✗ 未找到视频\n")
            continue
        
        # 检查是否有原视频URL
        video_info = videos[0]
        original_url = video_info.get("original_video_url")
        
        if original_url:
            print(f"  ✓ 找到原视频URL: {original_url[:60]}...")
            total_updated += 1
        else:
            print(f"  ⚠ 未找到原视频URL（API可能未返回）")
        
        # 显示当前使用的URL
        current_url = video_info.get("video_url", "")
        if current_url:
            print(f"  当前视频URL: {current_url[:60]}...")
        
        print()
    
    print("=" * 60)
    print(f"更新完成！共更新 {total_updated}/{len(games)} 个游戏的原视频URL")
    print("=" * 60)
    
    # 显示统计信息
    stats = db.get_statistics()
    print("\n数据库统计：")
    print(f"  总视频数: {stats.get('total_videos', 0)}")
    print(f"  已下载数: {stats.get('downloaded_videos', 0)}")
    print(f"  游戏数: {stats.get('unique_games', 0)}")
    
    # 显示有原视频URL的视频数量
    try:
        conn = db.db_path
        from modules.database import sqlite3
        conn_obj = sqlite3.connect(conn)
        cursor = conn_obj.cursor()
        cursor.execute('SELECT COUNT(*) FROM videos WHERE original_video_url IS NOT NULL AND original_video_url != ""')
        count = cursor.fetchone()[0]
        conn_obj.close()
        print(f"  有原视频URL的视频数: {count}")
    except:
        pass


if __name__ == "__main__":
    import sys
    
    game_name = None
    if len(sys.argv) > 1:
        game_name = sys.argv[1]
    
    re_search_and_update(game_name)