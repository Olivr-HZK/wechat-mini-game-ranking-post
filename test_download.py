"""
测试视频下载功能
测试通过URL直接下载视频
"""
from modules.rank_extractor import RankExtractor
from modules.video_searcher import VideoSearcher
from modules.database import VideoDatabase


def test_search_and_download():
    """测试搜索和下载功能"""
    print("=" * 60)
    print("测试视频搜索和下载功能")
    print("=" * 60)
    print()
    
    # 初始化
    extractor = RankExtractor()
    searcher = VideoSearcher(use_database=True)
    db = VideoDatabase()
    
    # 获取前3个游戏
    print("【步骤1】获取游戏列表...")
    games = extractor.get_top_games(top_n=3)
    print(f"找到 {len(games)} 个游戏\n")
    
    # 搜索并下载视频
    print("【步骤2】搜索视频（筛选：1分钟以内，玩法演示）...")
    print("-" * 60)
    
    for idx, game in enumerate(games, 1):
        game_name = game.get('游戏名称', '未知游戏')
        print(f"\n[{idx}] 游戏: {game_name}")
        
        # 搜索视频（会自动保存到数据库）
        videos = searcher.search_videos(
            game_name=game_name,
            game_type=game.get('游戏类型'),
            max_results=2  # 每个游戏找2个视频
        )
        
        if not videos:
            print(f"  ✗ 未找到视频")
            continue
        
        if not videos:
            print(f"  ✗ 未找到视频")
            continue
        
        # 只返回点赞量最高的那一条
        video = videos[0]  # 已经是点赞量最高的了
        
        print(f"  ✓ 找到视频（点赞量最高）:")
        print(f"    标题: {video.get('title', 'N/A')}")
        print(f"    视频ID: {video.get('aweme_id')}")
        print(f"    点赞数: {video.get('like_count', 0):,}")
        print(f"    评分: {video.get('relevance_score', 0)}")
        print(f"    时长: {video.get('duration', 0):.1f}秒")
        
        # 下载视频（会自动尝试免费URL，失败后使用API）
        print(f"\n  开始下载...")
        video_path = searcher.download_video(video)
        
        if video_path:
            print(f"  ✓ 下载成功: {video_path}")
        else:
            print(f"  ✗ 下载失败")
    
    # 显示数据库统计
    print("\n" + "=" * 60)
    print("【步骤3】数据库统计")
    print("=" * 60)
    stats = db.get_statistics()
    print(f"总视频数: {stats.get('total_videos', 0)}")
    print(f"已下载数: {stats.get('downloaded_videos', 0)}")
    print(f"游戏数: {stats.get('unique_games', 0)}")
    
    # 显示所有视频（按相关性评分排序）
    print("\n" + "=" * 60)
    print("【步骤4】数据库中的视频列表（按相关性评分排序）")
    print("=" * 60)
    all_videos = db.get_all_videos(limit=20)
    # 按相关性评分排序
    all_videos.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
    
    for idx, video in enumerate(all_videos, 1):
        score = video.get('relevance_score', 0)
        print(f"\n[{idx}] 评分:{score:2d} | {video.get('title', 'N/A')[:60]}")
        print(f"    游戏: {video.get('game_name')} | 视频ID: {video.get('aweme_id')}")
        print(f"    时长: {video.get('duration', 0):.1f}秒 | 点赞: {video.get('like_count', 0):,}")
        print(f"    已下载: {'是' if video.get('downloaded') else '否'}")
        if video.get('local_path'):
            print(f"    本地路径: {video.get('local_path')}")


if __name__ == "__main__":
    test_search_and_download()