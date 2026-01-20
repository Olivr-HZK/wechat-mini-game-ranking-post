"""
数据库模块
用于保存和管理游戏数据（按游戏存储，每个游戏一条记录）
"""
import sqlite3
import os
import json
from typing import Dict, List, Optional
from datetime import datetime
import config


class VideoDatabase:
    """游戏数据库管理器（按游戏存储）"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库
        
        Args:
            db_path: 数据库文件路径，默认使用 data/videos.db
        """
        if db_path is None:
            db_dir = os.path.dirname(config.RANKINGS_CSV_PATH)
            db_path = os.path.join(db_dir, "videos.db")
        
        self.db_path = db_path
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        # 执行数据迁移（如果是从旧版本升级）
        self._migrate_from_video_based()
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 检查是否存在旧的videos表（按视频存储）
        cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='videos'
        ''')
        old_table_exists = cursor.fetchone() is not None
        
        # 创建新的games表（按游戏存储）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT UNIQUE NOT NULL,
                game_rank TEXT,
                game_company TEXT,
                rank_change TEXT,
                aweme_id TEXT,
                title TEXT,
                description TEXT,
                video_url TEXT,
                video_urls TEXT,  -- JSON格式存储所有URL
                cover_url TEXT,
                author_uid TEXT,
                duration REAL,
                like_count INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                play_count INTEGER DEFAULT 0,
                create_time INTEGER,
                share_url TEXT,
                original_video_url TEXT,  -- 原视频URL（最高画质，如果API返回）
                gdrive_url TEXT,  -- Google Drive公开访问链接
                gdrive_file_id TEXT,  -- Google Drive文件ID
                local_path TEXT,  -- 本地下载路径
                downloaded INTEGER DEFAULT 0,  -- 是否已下载 0=否 1=是
                search_keyword TEXT,  -- 搜索关键词
                relevance_score INTEGER DEFAULT 0,  -- 相关性评分
                gameplay_analysis TEXT,  -- 游戏玩法分析结果
                analysis_model TEXT,  -- 使用的分析模型
                analyzed_at TIMESTAMP,  -- 分析时间
                screenshot_image_key TEXT,  -- 飞书截图image_key（JSON格式）
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_game_name ON games(game_name)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_game_rank ON games(game_rank)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at ON games(created_at)
        ''')
        
        # 数据库迁移：添加新字段（如果不存在）
        migrations = [
            ("game_rank", "TEXT"),
            ("game_company", "TEXT"),
            ("rank_change", "TEXT"),
            ("relevance_score", "INTEGER DEFAULT 0"),
            ("gameplay_analysis", "TEXT"),
            ("analysis_model", "TEXT"),
            ("analyzed_at", "TIMESTAMP"),
            ("original_video_url", "TEXT"),
            ("gdrive_url", "TEXT"),
            ("gdrive_file_id", "TEXT"),
            ("screenshot_image_key", "TEXT")
        ]
        
        for field_name, field_type in migrations:
            try:
                cursor.execute(f'SELECT {field_name} FROM games LIMIT 1')
            except sqlite3.OperationalError:
                # 字段不存在，需要添加
                print(f"检测到旧版数据库，正在添加{field_name}字段...")
                cursor.execute(f'ALTER TABLE games ADD COLUMN {field_name} {field_type}')
        
        conn.commit()
        conn.close()
    
    def _migrate_from_video_based(self):
        """从按视频存储的旧表迁移到按游戏存储的新表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 检查是否存在旧的videos表
        cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='videos'
        ''')
        old_table_exists = cursor.fetchone() is not None
        
        if not old_table_exists:
            conn.close()
            return
        
        # 检查games表是否已有数据
        cursor.execute('SELECT COUNT(*) FROM games')
        games_count = cursor.fetchone()[0]
        
        if games_count > 0:
            # 已经迁移过了，不需要再次迁移
            conn.close()
            return
        
        print("[*] 检测到旧版数据库（按视频存储），开始迁移到新版（按游戏存储）...")
        
        # 从旧表读取所有数据，按游戏分组
        cursor.execute('SELECT * FROM videos ORDER BY downloaded DESC, created_at DESC')
        old_rows = cursor.fetchall()
        
        # 获取列名
        cursor.execute('PRAGMA table_info(videos)')
        old_columns = [col[1] for col in cursor.fetchall()]
        
        # 按游戏分组，每个游戏只保留已下载的那个视频（如果都没有下载，保留最新的）
        games_dict = {}
        for row in old_rows:
            row_dict = dict(zip(old_columns, row))
            game_name = row_dict.get("game_name")
            
            if not game_name:
                continue
            
            # 如果该游戏还没有记录，或者当前记录已下载而之前的未下载，则更新
            if game_name not in games_dict:
                games_dict[game_name] = row_dict
            else:
                # 优先保留已下载的视频
                if row_dict.get("downloaded") == 1 and games_dict[game_name].get("downloaded") != 1:
                    games_dict[game_name] = row_dict
        
        # 将数据插入到新表
        migrated_count = 0
        for game_name, game_data in games_dict.items():
            try:
                video_urls = game_data.get("video_urls", [])
                video_urls_json = json.dumps(video_urls, ensure_ascii=False) if video_urls else None
                
                screenshot_key = game_data.get("screenshot_image_key")
                if screenshot_key and isinstance(screenshot_key, list):
                    screenshot_key = json.dumps(screenshot_key, ensure_ascii=False)
                
                cursor.execute('''
                    INSERT INTO games (
                        game_name, aweme_id, title, description,
                        video_url, video_urls, cover_url,
                        author_uid, duration,
                        like_count, comment_count, play_count,
                        create_time, share_url, original_video_url, gdrive_url, gdrive_file_id,
                        local_path, downloaded, search_keyword, relevance_score,
                        gameplay_analysis, analysis_model, analyzed_at, screenshot_image_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    game_name,
                    game_data.get("aweme_id"),
                    game_data.get("title"),
                    game_data.get("description"),
                    game_data.get("video_url"),
                    video_urls_json,
                    game_data.get("cover_url"),
                    game_data.get("author_uid"),
                    game_data.get("duration"),
                    game_data.get("like_count", 0),
                    game_data.get("comment_count", 0),
                    game_data.get("play_count", 0),
                    game_data.get("create_time"),
                    game_data.get("share_url"),
                    game_data.get("original_video_url"),
                    game_data.get("gdrive_url"),
                    game_data.get("gdrive_file_id"),
                    game_data.get("local_path"),
                    game_data.get("downloaded", 0),
                    game_data.get("search_keyword"),
                    game_data.get("relevance_score", 0),
                    game_data.get("gameplay_analysis"),
                    game_data.get("analysis_model"),
                    game_data.get("analyzed_at"),
                    screenshot_key
                ))
                migrated_count += 1
            except sqlite3.IntegrityError:
                # 游戏已存在，跳过
                continue
            except Exception as e:
                print(f"迁移游戏 '{game_name}' 时出错：{str(e)}")
                continue
        
        conn.commit()
        conn.close()
        
        if migrated_count > 0:
            print(f"✅ 成功迁移 {migrated_count} 个游戏的数据到新表")
            print("   旧表 'videos' 已保留，如需删除请手动执行：DROP TABLE videos")
    
    def save_game(self, game_info: Dict) -> bool:
        """
        保存游戏信息到数据库（按游戏名称，每个游戏一条记录）
        
        Args:
            game_info: 游戏信息字典，必须包含game_name
        
        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            game_name = game_info.get("game_name")
            if not game_name:
                print("错误：game_name是必需的")
                conn.close()
                return False
            
            # 将video_urls列表转为JSON字符串
            video_urls = game_info.get("video_urls", [])
            video_urls_json = json.dumps(video_urls, ensure_ascii=False) if video_urls else None
            
            screenshot_key = game_info.get("screenshot_image_key")
            if screenshot_key and isinstance(screenshot_key, list):
                screenshot_key = json.dumps(screenshot_key, ensure_ascii=False)
            
            # 检查是否已存在
            cursor.execute('SELECT id FROM games WHERE game_name = ?', (game_name,))
            existing = cursor.fetchone()
            
            if existing:
                # 更新现有记录
                cursor.execute('''
                    UPDATE games SET
                        game_rank = COALESCE(?, game_rank),
                        game_company = COALESCE(?, game_company),
                        rank_change = COALESCE(?, rank_change),
                        aweme_id = COALESCE(?, aweme_id),
                        title = COALESCE(?, title),
                        description = COALESCE(?, description),
                        video_url = COALESCE(?, video_url),
                        video_urls = COALESCE(?, video_urls),
                        cover_url = COALESCE(?, cover_url),
                        author_uid = COALESCE(?, author_uid),
                        duration = COALESCE(?, duration),
                        like_count = COALESCE(?, like_count),
                        comment_count = COALESCE(?, comment_count),
                        play_count = COALESCE(?, play_count),
                        create_time = COALESCE(?, create_time),
                        share_url = COALESCE(?, share_url),
                        original_video_url = COALESCE(?, original_video_url),
                        gdrive_url = COALESCE(?, gdrive_url),
                        gdrive_file_id = COALESCE(?, gdrive_file_id),
                        search_keyword = COALESCE(?, search_keyword),
                        relevance_score = COALESCE(?, relevance_score),
                        gameplay_analysis = COALESCE(?, gameplay_analysis),
                        analysis_model = COALESCE(?, analysis_model),
                        analyzed_at = COALESCE(?, analyzed_at),
                        screenshot_image_key = COALESCE(?, screenshot_image_key),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE game_name = ?
                ''', (
                    game_info.get("game_rank"),
                    game_info.get("game_company"),
                    game_info.get("rank_change"),
                    game_info.get("aweme_id"),
                    game_info.get("title"),
                    game_info.get("description"),
                    game_info.get("video_url"),
                    video_urls_json,
                    game_info.get("cover_url"),
                    game_info.get("author_uid"),
                    game_info.get("duration"),
                    game_info.get("like_count"),
                    game_info.get("comment_count"),
                    game_info.get("play_count"),
                    game_info.get("create_time"),
                    game_info.get("share_url"),
                    game_info.get("original_video_url"),
                    game_info.get("gdrive_url"),
                    game_info.get("gdrive_file_id"),
                    game_info.get("search_keyword"),
                    game_info.get("relevance_score"),
                    game_info.get("gameplay_analysis"),
                    game_info.get("analysis_model"),
                    game_info.get("analyzed_at"),
                    screenshot_key,
                    game_name
                ))
            else:
                # 插入新记录
                cursor.execute('''
                    INSERT INTO games (
                        game_name, game_rank, game_company, rank_change,
                        aweme_id, title, description,
                        video_url, video_urls, cover_url,
                        author_uid, duration,
                        like_count, comment_count, play_count,
                        create_time, share_url, original_video_url, gdrive_url, gdrive_file_id,
                        local_path, downloaded, search_keyword, relevance_score,
                        gameplay_analysis, analysis_model, analyzed_at, screenshot_image_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    game_name,
                    game_info.get("game_rank"),
                    game_info.get("game_company"),
                    game_info.get("rank_change"),
                    game_info.get("aweme_id"),
                    game_info.get("title"),
                    game_info.get("description"),
                    game_info.get("video_url"),
                    video_urls_json,
                    game_info.get("cover_url"),
                    game_info.get("author_uid"),
                    game_info.get("duration"),
                    game_info.get("like_count", 0),
                    game_info.get("comment_count", 0),
                    game_info.get("play_count", 0),
                    game_info.get("create_time"),
                    game_info.get("share_url"),
                    game_info.get("original_video_url"),
                    game_info.get("gdrive_url"),
                    game_info.get("gdrive_file_id"),
                    game_info.get("local_path"),
                    game_info.get("downloaded", 0),
                    game_info.get("search_keyword"),
                    game_info.get("relevance_score", 0),
                    game_info.get("gameplay_analysis"),
                    game_info.get("analysis_model"),
                    game_info.get("analyzed_at"),
                    screenshot_key
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"保存游戏到数据库时出错：{str(e)}")
            return False
    
    def update_game_ranking(self, game_name: str, game_rank: str = None, game_company: str = None, rank_change: str = None) -> bool:
        """
        更新游戏的排名信息
        
        Args:
            game_name: 游戏名称
            game_rank: 排名
            game_company: 开发公司
            rank_change: 排名变化
        
        Returns:
            是否更新成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if game_rank is not None:
                updates.append("game_rank = ?")
                params.append(game_rank)
            if game_company is not None:
                updates.append("game_company = ?")
                params.append(game_company)
            if rank_change is not None:
                updates.append("rank_change = ?")
                params.append(rank_change)
            
            if not updates:
                conn.close()
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(game_name)
            
            cursor.execute(f'''
                UPDATE games SET {', '.join(updates)}
                WHERE game_name = ?
            ''', params)
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"更新游戏排名时出错：{str(e)}")
            return False
    
    def update_download_status(self, game_name: str, local_path: str, gdrive_url: str = None, gdrive_file_id: str = None):
        """
        更新游戏视频下载状态
        
        Args:
            game_name: 游戏名称
            local_path: 本地文件路径
            gdrive_url: Google Drive公开访问链接（可选）
            gdrive_file_id: Google Drive文件ID（可选）
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if gdrive_url and gdrive_file_id:
                cursor.execute('''
                    UPDATE games SET
                        local_path = ?,
                        downloaded = 1,
                        gdrive_url = COALESCE(?, gdrive_url),
                        gdrive_file_id = COALESCE(?, gdrive_file_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE game_name = ?
                ''', (local_path, gdrive_url, gdrive_file_id, game_name))
            else:
                cursor.execute('''
                    UPDATE games SET
                        local_path = ?,
                        downloaded = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE game_name = ?
                ''', (local_path, game_name))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"更新下载状态时出错：{str(e)}")
    
    def update_screenshot_key(self, game_name: str, screenshot_image_keys) -> bool:
        """
        更新游戏的截图image_key（支持多个）
        
        Args:
            game_name: 游戏名称
            screenshot_image_keys: 飞书截图image_key（字符串或列表），如果是列表会转为JSON字符串
        
        Returns:
            是否更新成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 如果是列表，转为JSON字符串
            if isinstance(screenshot_image_keys, list):
                screenshot_image_key_str = json.dumps(screenshot_image_keys, ensure_ascii=False)
            else:
                screenshot_image_key_str = screenshot_image_keys
            
            cursor.execute('''
                UPDATE games SET
                    screenshot_image_key = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE game_name = ?
            ''', (screenshot_image_key_str, game_name))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"更新截图key时出错：{str(e)}")
            return False
    
    def get_screenshot_key(self, game_name: str) -> Optional[List[str]]:
        """
        获取游戏的截图image_key列表（如果已上传）
        
        Args:
            game_name: 游戏名称
        
        Returns:
            screenshot_image_key列表，如果不存在返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT screenshot_image_key 
                FROM games 
                WHERE game_name = ? AND screenshot_image_key IS NOT NULL AND screenshot_image_key != ''
            ''', (game_name,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                screenshot_key_str = row["screenshot_image_key"]
                # 尝试解析为JSON（如果是列表）
                try:
                    screenshot_keys = json.loads(screenshot_key_str)
                    if isinstance(screenshot_keys, list):
                        return screenshot_keys
                    else:
                        # 如果是单个字符串，返回列表
                        return [screenshot_keys]
                except (json.JSONDecodeError, TypeError):
                    # 如果不是JSON，当作单个字符串处理
                    return [screenshot_key_str]
            return None
            
        except Exception as e:
            print(f"获取截图key时出错：{str(e)}")
            return None
    
    def get_game(self, game_name: str) -> Optional[Dict]:
        """
        根据游戏名称获取游戏信息
        
        Args:
            game_name: 游戏名称
        
        Returns:
            游戏信息字典，如果不存在返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM games WHERE game_name = ?', (game_name,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                return self._row_to_dict(row)
            return None
            
        except Exception as e:
            print(f"获取游戏信息时出错：{str(e)}")
            return None
    
    def get_all_games(self, limit: int = None) -> List[Dict]:
        """
        获取所有游戏
        
        Args:
            limit: 限制返回数量
        
        Returns:
            游戏信息列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if limit:
                cursor.execute('SELECT * FROM games ORDER BY created_at DESC LIMIT ?', (limit,))
            else:
                cursor.execute('SELECT * FROM games ORDER BY created_at DESC')
            
            rows = cursor.fetchall()
            conn.close()
            
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            print(f"获取所有游戏时出错：{str(e)}")
            return []
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """
        将数据库行转换为字典
        
        Args:
            row: 数据库行
        
        Returns:
            字典
        """
        result = dict(row)
        
        # 解析video_urls JSON
        if result.get("video_urls"):
            try:
                result["video_urls"] = json.loads(result["video_urls"])
            except:
                result["video_urls"] = []
        else:
            result["video_urls"] = []
        
        return result
    
    def get_gameplay_analysis(self, game_name: str) -> Optional[Dict]:
        """
        获取游戏的玩法分析结果（如果已分析过）
        
        Args:
            game_name: 游戏名称
        
        Returns:
            分析结果字典，包含gameplay_analysis和analysis_model，如果不存在返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT gameplay_analysis, analysis_model, analyzed_at 
                FROM games 
                WHERE game_name = ? AND gameplay_analysis IS NOT NULL AND gameplay_analysis != ''
            ''', (game_name,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "gameplay_analysis": row["gameplay_analysis"],
                    "analysis_model": row["analysis_model"],
                    "analyzed_at": row["analyzed_at"]
                }
            return None
            
        except Exception as e:
            print(f"获取玩法分析时出错：{str(e)}")
            return None
    
    def save_gameplay_analysis(self, game_name: str, analysis_text: str, model_used: str) -> bool:
        """
        保存游戏的玩法分析结果到数据库
        
        Args:
            game_name: 游戏名称
            analysis_text: 分析结果文本
            model_used: 使用的模型
        
        Returns:
            是否保存成功
        """
        try:
            from datetime import datetime
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE games SET
                    gameplay_analysis = ?,
                    analysis_model = ?,
                    analyzed_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE game_name = ?
            ''', (analysis_text, model_used, datetime.now(), game_name))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"保存玩法分析时出错：{str(e)}")
            return False
    
    def clear_gameplay_analysis(self, game_name: str) -> int:
        """
        清除指定游戏的AI玩法分析（保留视频等其他数据）
        
        Args:
            game_name: 游戏名称
        
        Returns:
            受影响的记录数
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE games SET
                    gameplay_analysis = NULL,
                    analysis_model = NULL,
                    analyzed_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE game_name = ? AND gameplay_analysis IS NOT NULL AND gameplay_analysis != ''
            ''', (game_name,))
            
            count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if count > 0:
                print(f"已清除游戏 '{game_name}' 的AI分析结果")
            else:
                print(f"未找到需要清除分析结果的记录：'{game_name}'")
            
            return count
            
        except Exception as e:
            print(f"清除玩法分析时出错：{str(e)}")
            return 0

    def clear_all_gameplay_videos(self) -> int:
        """
        清空数据库中所有游戏的“玩法视频相关字段”（不删除游戏记录）。
        用于让工作流下次重新搜索/下载/上传视频。

        注意：
        - 仅清理 videos 相关字段（aweme_id / video_url / gdrive_url / local_path 等）
        - 不会清理 gameplay_analysis（玩法分析缓存），如需清理请单独处理

        Returns:
            受影响的记录数
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE games SET
                    aweme_id = NULL,
                    title = NULL,
                    description = NULL,
                    video_url = NULL,
                    video_urls = NULL,
                    cover_url = NULL,
                    author_uid = NULL,
                    duration = NULL,
                    like_count = 0,
                    comment_count = 0,
                    play_count = 0,
                    create_time = NULL,
                    share_url = NULL,
                    original_video_url = NULL,
                    gdrive_url = NULL,
                    gdrive_file_id = NULL,
                    local_path = NULL,
                    downloaded = 0,
                    search_keyword = NULL,
                    relevance_score = 0,
                    screenshot_image_key = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE
                    aweme_id IS NOT NULL
                    OR video_url IS NOT NULL
                    OR (video_urls IS NOT NULL AND video_urls != '')
                    OR cover_url IS NOT NULL
                    OR share_url IS NOT NULL
                    OR original_video_url IS NOT NULL
                    OR gdrive_url IS NOT NULL
                    OR gdrive_file_id IS NOT NULL
                    OR local_path IS NOT NULL
                    OR downloaded != 0
                    OR (search_keyword IS NOT NULL AND search_keyword != '')
                    OR relevance_score != 0
                    OR (screenshot_image_key IS NOT NULL AND screenshot_image_key != '')
                """
            )

            count = cursor.rowcount
            conn.commit()
            conn.close()

            if count > 0:
                print(f"已清空 {count} 条游戏记录的玩法视频字段（保留游戏与分析结果）")
            else:
                print("数据库中未发现需要清理的玩法视频字段")

            return count
        except Exception as e:
            print(f"清空所有玩法视频字段时出错：{str(e)}")
            return 0
    
    def delete_game_data(self, game_name: str) -> int:
        """
        删除指定游戏的所有数据
        
        Args:
            game_name: 游戏名称
        
        Returns:
            删除的记录数
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM games WHERE game_name = ?', (game_name,))
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                print(f"已删除游戏 '{game_name}' 的数据")
            else:
                print(f"未找到游戏 '{game_name}' 的数据")
            
            return deleted_count
            
        except Exception as e:
            print(f"删除游戏数据时出错：{str(e)}")
            return 0
    
    def get_statistics(self) -> Dict:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 总游戏数
            cursor.execute('SELECT COUNT(*) FROM games')
            total = cursor.fetchone()[0]
            
            # 已下载数
            cursor.execute('SELECT COUNT(*) FROM games WHERE downloaded = 1')
            downloaded = cursor.fetchone()[0]
            
            # 已分析数
            cursor.execute('SELECT COUNT(*) FROM games WHERE gameplay_analysis IS NOT NULL AND gameplay_analysis != ""')
            analyzed = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "total_games": total,
                "downloaded_games": downloaded,
                "analyzed_games": analyzed
            }
            
        except Exception as e:
            print(f"获取统计信息时出错：{str(e)}")
            return {}
    
    # 兼容旧方法名（向后兼容）
    def save_video(self, video_info: Dict) -> bool:
        """兼容旧方法名，实际调用save_game"""
        return self.save_game(video_info)
    
    def get_video(self, aweme_id: str) -> Optional[Dict]:
        """兼容旧方法名，根据aweme_id查找游戏（不推荐使用）"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM games WHERE aweme_id = ?', (aweme_id,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                return self._row_to_dict(row)
            return None
            
        except Exception as e:
            print(f"获取视频信息时出错：{str(e)}")
            return None
    
    def get_videos_by_game(self, game_name: str) -> List[Dict]:
        """兼容旧方法名，实际返回单个游戏的列表（因为现在每个游戏只有一条记录）"""
        game = self.get_game(game_name)
        return [game] if game else []
    
    def get_video_by_game_name(self, game_name: str) -> Optional[Dict]:
        """兼容旧方法名，实际调用get_game"""
        return self.get_game(game_name)
