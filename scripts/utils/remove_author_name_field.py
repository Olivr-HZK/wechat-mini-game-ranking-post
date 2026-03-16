"""
删除数据库中的author_name字段
由于SQLite不支持直接删除列，需要重建表
"""
import sqlite3
import os
import config

def main():
    """删除author_name字段"""
    print("=" * 60)
    print("删除数据库中的author_name字段")
    print("=" * 60)
    print()
    
    # 连接数据库
    db_dir = os.path.dirname(config.RANKINGS_CSV_PATH)
    db_path = os.path.join(db_dir, "videos.db")
    
    if not os.path.exists(db_path):
        print(f"错误：找不到数据库文件：{db_path}")
        return
    
    print(f"[*] 连接数据库：{db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查games表是否存在
    cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='games'
    ''')
    if not cursor.fetchone():
        print("  ✗ 数据库中没有games表")
        conn.close()
        return
    
    # 检查author_name字段是否存在
    cursor.execute('PRAGMA table_info(games)')
    columns = [col[1] for col in cursor.fetchall()]
    has_author_name = 'author_name' in columns
    
    if not has_author_name:
        print("  ✓ author_name字段不存在，无需删除")
        conn.close()
        return
    
    print("  [!] 检测到author_name字段，需要重建表来删除它")
    response = input("  是否继续？(y/N): ").strip().lower()
    
    if response != 'y':
        print("  已取消")
        conn.close()
        return
    
    print()
    print("[*] 开始重建表...")
    
    try:
        # 创建新表（不包含author_name）
        cursor.execute('''
            CREATE TABLE games_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT UNIQUE NOT NULL,
                game_rank TEXT,
                game_company TEXT,
                rank_change TEXT,
                aweme_id TEXT,
                title TEXT,
                description TEXT,
                video_url TEXT,
                video_urls TEXT,
                cover_url TEXT,
                author_uid TEXT,
                duration REAL,
                like_count INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                play_count INTEGER DEFAULT 0,
                create_time INTEGER,
                share_url TEXT,
                original_video_url TEXT,
                gdrive_url TEXT,
                gdrive_file_id TEXT,
                local_path TEXT,
                downloaded INTEGER DEFAULT 0,
                search_keyword TEXT,
                relevance_score INTEGER DEFAULT 0,
                gameplay_analysis TEXT,
                analysis_model TEXT,
                analyzed_at TIMESTAMP,
                screenshot_image_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 复制数据（排除author_name）
        keep_columns = [col for col in columns if col != 'author_name']
        columns_str = ', '.join(keep_columns)
        cursor.execute(f'''
            INSERT INTO games_new ({columns_str})
            SELECT {columns_str} FROM games
        ''')
        
        # 删除旧表，重命名新表
        cursor.execute('DROP TABLE games')
        cursor.execute('ALTER TABLE games_new RENAME TO games')
        
        # 重建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_game_name ON games(game_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_game_rank ON games(game_rank)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON games(created_at)')
        
        conn.commit()
        print("  ✓ 已成功删除author_name字段")
        
    except Exception as e:
        print(f"  ✗ 删除字段失败：{str(e)}")
        conn.rollback()
        raise
    
    finally:
        conn.close()
    
    print()
    print("=" * 60)
    print("完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
