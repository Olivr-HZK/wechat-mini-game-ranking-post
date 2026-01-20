"""
一键清理：删除数据库中所有游戏的“玩法视频相关字段”（不删除游戏记录）。

用途：
- 让下一次工作流重新搜索/下载/上传视频（相当于把视频缓存清空）

注意：
- 只清理数据库字段；不会删除 data/videos/ 下的本地视频文件
- 不会清理 gameplay_analysis（玩法分析缓存）
"""

from modules.database import VideoDatabase


def main() -> None:
    print("=" * 60)
    print("清空数据库：所有游戏玩法视频字段")
    print("=" * 60)
    db = VideoDatabase()
    affected = db.clear_all_gameplay_videos()
    print("-" * 60)
    stats = db.get_statistics()
    print("当前数据库统计：")
    print(f"  总游戏数: {stats.get('total_games', 0)}")
    print(f"  已下载数: {stats.get('downloaded_games', 0)}")
    print(f"  已分析数: {stats.get('analyzed_games', 0)}")
    print("-" * 60)
    print(f"完成：本次清理影响记录数 = {affected}")


if __name__ == "__main__":
    main()

