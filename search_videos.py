"""
独立的视频搜索脚本
用于单独执行视频搜索功能，不运行完整工作流
"""
import sys
import argparse
import json
from datetime import datetime
from modules.rank_extractor import RankExtractor
from modules.video_searcher import VideoSearcher
import config


def search_videos_for_games(games, max_results_per_game=1, download=False, save_summary=True):
    """
    为多个游戏搜索视频
    
    Args:
        games: 游戏列表
        max_results_per_game: 每个游戏搜索的最大结果数
        download: 是否下载视频
        save_summary: 是否保存搜索摘要
    """
    searcher = VideoSearcher()
    all_results = []
    
    print("=" * 60)
    print("视频搜索任务")
    print("=" * 60)
    print(f"游戏数量: {len(games)}")
    print(f"每个游戏最大结果数: {max_results_per_game}")
    print(f"是否下载视频: {'是' if download else '否'}")
    print("=" * 60)
    print()
    
    for idx, game in enumerate(games, 1):
        game_name = game.get('游戏名称', '未知游戏')
        game_type = game.get('游戏类型', '')
        rank = game.get('排名', idx)
        
        print(f"\n[{idx}/{len(games)}] 处理游戏: {game_name} (排名: {rank})")
        print("-" * 60)
        
        # 搜索视频
        videos = searcher.search_videos(
            game_name=game_name,
            game_type=game_type,
            max_results=max_results_per_game
        )
        
        if not videos:
            print(f"  ✗ 未找到视频")
            continue
        
        print(f"  ✓ 找到 {len(videos)} 个视频")
        
        # 处理每个视频
        for video_idx, video_info in enumerate(videos, 1):
            print(f"\n  视频 {video_idx}:")
            print(f"    标题: {video_info.get('title', 'N/A')}")
            print(f"    视频ID: {video_info.get('aweme_id', 'N/A')}")
            print(f"    作者: {video_info.get('author_name', 'N/A')}")
            print(f"    时长: {video_info.get('duration', 0):.1f}秒")
            print(f"    点赞数: {video_info.get('like_count', 0):,}")
            print(f"    播放数: {video_info.get('play_count', 0):,}")
            
            # 保存视频信息
            info_path = searcher.save_video_info(video_info)
            if info_path:
                print(f"    信息已保存: {info_path}")
            
            # 下载视频（如果需要）
            if download:
                print(f"    正在下载视频...")
                video_path = searcher.download_video(video_info)
                if video_path:
                    print(f"    ✓ 视频已下载: {video_path}")
                else:
                    print(f"    ✗ 视频下载失败")
        
        # 记录结果
        all_results.append({
            "game": game,
            "videos": videos,
            "count": len(videos)
        })
    
    # 保存搜索摘要
    if save_summary:
        summary = {
            "search_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_games": len(games),
            "total_videos": sum(r["count"] for r in all_results),
            "results": []
        }
        
        for result in all_results:
            game = result["game"]
            summary["results"].append({
                "game_name": game.get("游戏名称"),
                "rank": game.get("排名"),
                "game_type": game.get("游戏类型"),
                "video_count": result["count"],
                "videos": [
                    {
                        "aweme_id": v.get("aweme_id"),
                        "title": v.get("title"),
                        "video_url": v.get("video_url"),
                        "author": v.get("author_name"),
                        "like_count": v.get("like_count"),
                        "play_count": v.get("play_count")
                    }
                    for v in result["videos"]
                ]
            })
        
        summary_file = f"data/search_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            import os
            os.makedirs("data", exist_ok=True)
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            print(f"\n✓ 搜索摘要已保存: {summary_file}")
        except Exception as e:
            print(f"\n✗ 保存搜索摘要失败: {str(e)}")
    
    # 打印统计信息
    print("\n" + "=" * 60)
    print("搜索完成统计")
    print("=" * 60)
    print(f"处理游戏数: {len(games)}")
    print(f"找到视频的游戏数: {sum(1 for r in all_results if r['count'] > 0)}")
    print(f"总视频数: {sum(r['count'] for r in all_results)}")
    print("=" * 60)


def search_single_game(game_name, game_type=None, max_results=5, download=False):
    """
    搜索单个游戏的视频
    
    Args:
        game_name: 游戏名称
        game_type: 游戏类型（可选）
        max_results: 最大结果数
        download: 是否下载视频
    """
    searcher = VideoSearcher()
    
    print("=" * 60)
    print(f"搜索游戏视频: {game_name}")
    print("=" * 60)
    print()
    
    # 搜索视频
    videos = searcher.search_videos(
        game_name=game_name,
        game_type=game_type,
        max_results=max_results
    )
    
    if not videos:
        print("未找到相关视频")
        return
    
    print(f"找到 {len(videos)} 个视频:\n")
    
    # 显示并处理每个视频
    for idx, video_info in enumerate(videos, 1):
        print(f"[{idx}] {video_info.get('title', 'N/A')}")
        print(f"    视频ID: {video_info.get('aweme_id', 'N/A')}")
        print(f"    作者: {video_info.get('author_name', 'N/A')}")
        print(f"    时长: {video_info.get('duration', 0):.1f}秒")
        print(f"    点赞: {video_info.get('like_count', 0):,} | "
              f"评论: {video_info.get('comment_count', 0):,} | "
              f"播放: {video_info.get('play_count', 0):,}")
        print(f"    URL: {video_info.get('video_url', 'N/A')[:80]}...")
        
        # 保存视频信息
        info_path = searcher.save_video_info(video_info)
        if info_path:
            print(f"    ✓ 信息已保存")
        
        # 下载视频（如果需要）
        if download:
            print(f"    正在下载...")
            video_path = searcher.download_video(video_info)
            if video_path:
                print(f"    ✓ 已下载: {video_path}")
            else:
                print(f"    ✗ 下载失败")
        
        print()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="视频搜索工具 - 从抖音搜索游戏相关视频",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从排行榜搜索前5个游戏的视频
  python search_videos.py --top 5
  
  # 搜索单个游戏
  python search_videos.py --game "羊了个羊"
  
  # 搜索并下载视频
  python search_videos.py --top 3 --download
  
  # 每个游戏搜索多个结果
  python search_videos.py --top 5 --max-results 3
        """
    )
    
    # 添加参数
    parser.add_argument(
        '--top', '-t',
        type=int,
        metavar='N',
        help='从排行榜搜索前N个游戏的视频'
    )
    
    parser.add_argument(
        '--game', '-g',
        type=str,
        metavar='NAME',
        help='搜索单个游戏的视频'
    )
    
    parser.add_argument(
        '--max-results', '-m',
        type=int,
        default=1,
        metavar='N',
        help='每个游戏搜索的最大结果数（默认: 1）'
    )
    
    parser.add_argument(
        '--download', '-d',
        action='store_true',
        help='下载找到的视频（默认: 仅保存信息）'
    )
    
    parser.add_argument(
        '--no-summary',
        action='store_true',
        help='不保存搜索摘要（仅在使用--top时有效）'
    )
    
    args = parser.parse_args()
    
    # 检查参数
    if not args.top and not args.game:
        parser.print_help()
        print("\n错误: 必须指定 --top 或 --game 参数")
        sys.exit(1)
    
    # 执行搜索
    if args.game:
        # 搜索单个游戏
        search_single_game(
            game_name=args.game,
            max_results=args.max_results,
            download=args.download
        )
    else:
        # 从排行榜搜索
        extractor = RankExtractor()
        games = extractor.get_top_games(top_n=args.top)
        
        if not games:
            print("错误: 未能从排行榜提取游戏信息")
            sys.exit(1)
        
        search_videos_for_games(
            games=games,
            max_results_per_game=args.max_results,
            download=args.download,
            save_summary=not args.no_summary
        )


if __name__ == "__main__":
    main()