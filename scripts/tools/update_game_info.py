"""
更新游戏信息脚本
从game_rankings.csv读取游戏排名、公司、排名变化信息，更新到数据库
并删除author_name字段
"""
import csv
import sqlite3
import os
import config

def main():
    """更新游戏信息"""
    print("=" * 60)
    print("更新游戏信息：从CSV读取排名、公司、排名变化")
    print("=" * 60)
    print()
    
    # 读取CSV文件
    csv_path = config.RANKINGS_CSV_PATH
    if not os.path.exists(csv_path):
        print(f"错误：找不到CSV文件：{csv_path}")
        return
    
    print(f"[*] 读取CSV文件：{csv_path}")
    
    # 读取CSV，支持多种编码
    game_data = {}
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
    
    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    game_name = row.get('游戏名称', '').strip()
                    if game_name:
                        game_data[game_name] = {
                            'game_rank': row.get('排名', '').strip(),
                            'game_company': row.get('开发公司', '').strip(),
                            'rank_change': row.get('排名变化', '').strip() or '--'
                        }
            print(f"  ✓ 成功读取 {len(game_data)} 个游戏的信息")
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"  ✗ 读取CSV失败：{str(e)}")
            return
    
    if not game_data:
        print("  ✗ 未读取到任何游戏数据")
        return
    
    # 连接数据库
    db_dir = os.path.dirname(config.RANKINGS_CSV_PATH)
    db_path = os.path.join(db_dir, "videos.db")
    
    if not os.path.exists(db_path):
        print(f"错误：找不到数据库文件：{db_path}")
        return
    
    print()
    print(f"[*] 连接数据库：{db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查games表是否存在
    cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='games'
    ''')
    if not cursor.fetchone():
        print("  ✗ 数据库中没有games表，请先运行迁移脚本")
        conn.close()
        return
    
    # 检查author_name字段是否存在
    cursor.execute('PRAGMA table_info(games)')
    columns = [col[1] for col in cursor.fetchall()]
    has_author_name = 'author_name' in columns
    
    # 更新游戏信息
    print()
    print("[*] 更新游戏信息...")
    updated_count = 0
    not_found_games = []
    
    for game_name, info in game_data.items():
        # 检查游戏是否存在
        cursor.execute('SELECT game_name FROM games WHERE game_name = ?', (game_name,))
        if not cursor.fetchone():
            not_found_games.append(game_name)
            continue
        
        # 更新排名信息
        cursor.execute('''
            UPDATE games SET
                game_rank = ?,
                game_company = ?,
                rank_change = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE game_name = ?
        ''', (
            info['game_rank'],
            info['game_company'],
            info['rank_change'],
            game_name
        ))
        
        if cursor.rowcount > 0:
            updated_count += 1
            print(f"  ✓ 更新 {game_name}: 排名={info['game_rank']}, 公司={info['game_company']}, 变化={info['rank_change']}")
    
    conn.commit()
    
    if not_found_games:
        print()
        print(f"[!] 以下游戏在数据库中未找到：{', '.join(not_found_games)}")
    
    # 删除author_name字段（SQLite不支持直接删除列，需要重建表）
    if has_author_name:
        print()
        print("[*] 删除author_name字段...")
        response = input("  注意：删除字段需要重建表，是否继续？(y/N): ").strip().lower()
        
        if response == 'y':
            try:
                # 获取所有列名（除了author_name）
                cursor.execute('PRAGMA table_info(games)')
                columns_info = cursor.fetchall()
                keep_columns = [col[1] for col in columns_info if col[1] != 'author_name']
                
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
                columns_str = ', '.join([col for col in keep_columns if col != 'author_name'])
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
                print("  ✓ 已删除author_name字段")
                
            except Exception as e:
                print(f"  ✗ 删除字段失败：{str(e)}")
                conn.rollback()
        else:
            print("  跳过删除author_name字段")
    else:
        print()
        print("  - author_name字段不存在，无需删除")
    
    conn.close()
    
    print()
    print("=" * 60)
    print("更新完成！")
    print("=" * 60)
    print(f"  更新了 {updated_count} 个游戏的信息")
    if not_found_games:
        print(f"  {len(not_found_games)} 个游戏在数据库中未找到")

if __name__ == "__main__":
    main()
