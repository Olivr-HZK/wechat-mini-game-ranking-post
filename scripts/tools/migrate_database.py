"""
数据库迁移脚本
将旧版数据库（按视频存储）迁移到新版（按游戏存储）
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
import sys
from modules.database import VideoDatabase

def main():
    """执行数据库迁移"""
    print("=" * 60)
    print("数据库迁移工具：从按视频存储迁移到按游戏存储")
    print("=" * 60)
    print()
    
    # 初始化数据库（会自动执行迁移）
    print("[*] 正在初始化数据库...")
    db = VideoDatabase()
    
    print()
    print("[*] 检查数据库状态...")
    
    # 检查旧表是否存在
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    # 检查旧表
    cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='videos'
    ''')
    old_table_exists = cursor.fetchone() is not None
    
    # 检查新表
    cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='games'
    ''')
    new_table_exists = cursor.fetchone() is not None
    
    if old_table_exists:
        cursor.execute('SELECT COUNT(*) FROM videos')
        old_count = cursor.fetchone()[0]
        print(f"  ✓ 旧表 'videos' 存在，包含 {old_count} 条记录")
    else:
        print("  - 旧表 'videos' 不存在")
    
    if new_table_exists:
        cursor.execute('SELECT COUNT(*) FROM games')
        new_count = cursor.fetchone()[0]
        print(f"  ✓ 新表 'games' 存在，包含 {new_count} 条记录")
    else:
        print("  ✗ 新表 'games' 不存在")
    
    conn.close()
    
    print()
    print("[*] 获取统计信息...")
    stats = db.get_statistics()
    print(f"  总游戏数：{stats.get('total_games', 0)}")
    print(f"  已下载游戏数：{stats.get('downloaded_games', 0)}")
    print(f"  已分析游戏数：{stats.get('analyzed_games', 0)}")
    
    print()
    print("=" * 60)
    print("迁移完成！")
    print("=" * 60)
    print()
    print("说明：")
    print("1. 数据已从 'videos' 表迁移到 'games' 表")
    print("2. 每个游戏只保留一个视频（优先保留已下载的）")
    print("3. 旧表 'videos' 已保留，如需删除可手动执行：")
    print("   sqlite3 data/videos.db \"DROP TABLE videos;\"")
    print()
    
    # 询问是否删除旧表
    if old_table_exists and new_table_exists:
        response = input("是否删除旧表 'videos'？(y/N): ").strip().lower()
        if response == 'y':
            try:
                conn = sqlite3.connect(db.db_path)
                cursor = conn.cursor()
                cursor.execute('DROP TABLE videos')
                conn.commit()
                conn.close()
                print("  ✓ 已删除旧表 'videos'")
            except Exception as e:
                print(f"  ✗ 删除旧表失败：{str(e)}")
        else:
            print("  保留旧表 'videos'")

if __name__ == "__main__":
    main()
