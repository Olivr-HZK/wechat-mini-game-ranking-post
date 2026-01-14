"""
数据库模块
用于保存和管理视频搜索结果
"""
import sqlite3
import os
import json
from typing import Dict, List, Optional
from datetime import datetime
import config


class VideoDatabase:
    """视频数据库管理器"""
    
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
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建视频表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aweme_id TEXT UNIQUE NOT NULL,
                game_name TEXT NOT NULL,
                title TEXT,
                description TEXT,
                video_url TEXT NOT NULL,
                video_urls TEXT,  -- JSON格式存储所有URL
                cover_url TEXT,
                author_name TEXT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_aweme_id ON videos(aweme_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_game_name ON videos(game_name)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at ON videos(created_at)
        ''')
        
        # 数据库迁移：添加新字段（如果不存在）
        migrations = [
            ("relevance_score", "INTEGER DEFAULT 0"),
            ("gameplay_analysis", "TEXT"),
            ("analysis_model", "TEXT"),
            ("analyzed_at", "TIMESTAMP"),
            ("original_video_url", "TEXT"),
            ("gdrive_url", "TEXT"),
            ("gdrive_file_id", "TEXT"),
            ("screenshot_image_key", "TEXT")  # 飞书截图image_key
        ]
        
        for field_name, field_type in migrations:
            try:
                cursor.execute(f'SELECT {field_name} FROM videos LIMIT 1')
            except sqlite3.OperationalError:
                # 字段不存在，需要添加
                print(f"检测到旧版数据库，正在添加{field_name}字段...")
                cursor.execute(f'ALTER TABLE videos ADD COLUMN {field_name} {field_type}')
        
        conn.commit()
        conn.close()
    
    def save_video(self, video_info: Dict) -> bool:
        """
        保存视频信息到数据库
        
        Args:
            video_info: 视频信息字典
        
        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 将video_urls列表转为JSON字符串
            video_urls = video_info.get("video_urls", [])
            video_urls_json = json.dumps(video_urls, ensure_ascii=False) if video_urls else None
            
            # 检查是否已存在
            cursor.execute('SELECT id FROM videos WHERE aweme_id = ?', (video_info.get("aweme_id"),))
            existing = cursor.fetchone()
            
            if existing:
                # 更新现有记录
                cursor.execute('''
                    UPDATE videos SET
                        game_name = ?,
                        title = ?,
                        description = ?,
                        video_url = ?,
                        video_urls = ?,
                        cover_url = ?,
                        author_name = ?,
                        author_uid = ?,
                        duration = ?,
                        like_count = ?,
                        comment_count = ?,
                        play_count = ?,
                        create_time = ?,
                        share_url = ?,
                        original_video_url = COALESCE(?, original_video_url),
                        gdrive_url = COALESCE(?, gdrive_url),
                        gdrive_file_id = COALESCE(?, gdrive_file_id),
                        relevance_score = ?,
                        gameplay_analysis = COALESCE(?, gameplay_analysis),
                        analysis_model = COALESCE(?, analysis_model),
                        analyzed_at = COALESCE(?, analyzed_at),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE aweme_id = ?
                ''', (
                    video_info.get("game_name"),
                    video_info.get("title"),
                    video_info.get("description"),
                    video_info.get("video_url"),
                    video_urls_json,
                    video_info.get("cover_url"),
                    video_info.get("author_name"),
                    video_info.get("author_uid"),
                    video_info.get("duration"),
                    video_info.get("like_count", 0),
                    video_info.get("comment_count", 0),
                    video_info.get("play_count", 0),
                    video_info.get("create_time"),
                    video_info.get("share_url"),
                    video_info.get("original_video_url"),
                    video_info.get("gdrive_url"),
                    video_info.get("gdrive_file_id"),
                    video_info.get("relevance_score", 0),
                    video_info.get("gameplay_analysis"),
                    video_info.get("analysis_model"),
                    video_info.get("analyzed_at"),
                    video_info.get("aweme_id")
                ))
            else:
                # 插入新记录
                cursor.execute('''
                    INSERT INTO videos (
                        aweme_id, game_name, title, description,
                        video_url, video_urls, cover_url,
                        author_name, author_uid, duration,
                        like_count, comment_count, play_count,
                        create_time, share_url, original_video_url, gdrive_url, gdrive_file_id, search_keyword, relevance_score,
                        gameplay_analysis, analysis_model, analyzed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    video_info.get("aweme_id"),
                    video_info.get("game_name"),
                    video_info.get("title"),
                    video_info.get("description"),
                    video_info.get("video_url"),
                    video_urls_json,
                    video_info.get("cover_url"),
                    video_info.get("author_name"),
                    video_info.get("author_uid"),
                    video_info.get("duration"),
                    video_info.get("like_count", 0),
                    video_info.get("comment_count", 0),
                    video_info.get("play_count", 0),
                    video_info.get("create_time"),
                    video_info.get("share_url"),
                    video_info.get("original_video_url"),
                    video_info.get("gdrive_url"),
                    video_info.get("gdrive_file_id"),
                    video_info.get("search_keyword"),
                    video_info.get("relevance_score", 0),
                    video_info.get("gameplay_analysis"),
                    video_info.get("analysis_model"),
                    video_info.get("analyzed_at")
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"保存视频到数据库时出错：{str(e)}")
            return False
    
    def update_download_status(self, aweme_id: str, local_path: str, gdrive_url: str = None, gdrive_file_id: str = None):
        """
        更新视频下载状态，并可选择更新Google Drive链接
        
        Args:
            aweme_id: 视频ID
            local_path: 本地文件路径
            gdrive_url: Google Drive公开访问链接（可选）
            gdrive_file_id: Google Drive文件ID（可选）
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if gdrive_url and gdrive_file_id:
                cursor.execute('''
                    UPDATE videos SET
                        local_path = ?,
                        downloaded = 1,
                        gdrive_url = COALESCE(?, gdrive_url),
                        gdrive_file_id = COALESCE(?, gdrive_file_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE aweme_id = ?
                ''', (local_path, gdrive_url, gdrive_file_id, aweme_id))
            else:
                cursor.execute('''
                    UPDATE videos SET
                        local_path = ?,
                        downloaded = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE aweme_id = ?
                ''', (local_path, aweme_id))
            
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
            
            # 更新该游戏所有视频的截图key
            cursor.execute('''
                UPDATE videos SET
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
                FROM videos 
                WHERE game_name = ? AND screenshot_image_key IS NOT NULL AND screenshot_image_key != ''
                LIMIT 1
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
    
    def get_video(self, aweme_id: str) -> Optional[Dict]:
        """
        根据aweme_id获取视频信息
        
        Args:
            aweme_id: 视频ID
        
        Returns:
            视频信息字典，如果不存在返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM videos WHERE aweme_id = ?', (aweme_id,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                return self._row_to_dict(row)
            return None
            
        except Exception as e:
            print(f"获取视频信息时出错：{str(e)}")
            return None
    
    def get_videos_by_game(self, game_name: str) -> List[Dict]:
        """
        根据游戏名称获取所有视频
        
        Args:
            game_name: 游戏名称
        
        Returns:
            视频信息列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM videos WHERE game_name = ? ORDER BY created_at DESC', (game_name,))
            rows = cursor.fetchall()
            
            conn.close()
            
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            print(f"获取游戏视频时出错：{str(e)}")
            return []
    
    def get_all_videos(self, limit: int = None) -> List[Dict]:
        """
        获取所有视频
        
        Args:
            limit: 限制返回数量
        
        Returns:
            视频信息列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if limit:
                cursor.execute('SELECT * FROM videos ORDER BY created_at DESC LIMIT ?', (limit,))
            else:
                cursor.execute('SELECT * FROM videos ORDER BY created_at DESC')
            
            rows = cursor.fetchall()
            conn.close()
            
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            print(f"获取所有视频时出错：{str(e)}")
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
            
            # 查找该游戏已分析的视频（优先找已分析的）
            cursor.execute('''
                SELECT gameplay_analysis, analysis_model, analyzed_at 
                FROM videos 
                WHERE game_name = ? AND gameplay_analysis IS NOT NULL AND gameplay_analysis != ''
                ORDER BY analyzed_at DESC
                LIMIT 1
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
            
            # 更新该游戏所有视频的分析结果（因为同一个游戏可能有多个视频）
            cursor.execute('''
                UPDATE videos SET
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
            
            # 统计将被清除的记录数
            cursor.execute(
                "SELECT COUNT(*) FROM videos WHERE game_name = ? AND gameplay_analysis IS NOT NULL AND gameplay_analysis != ''",
                (game_name,)
            )
            count = cursor.fetchone()[0]
            
            if count == 0:
                print(f"未找到需要清除分析结果的记录：'{game_name}'")
                conn.close()
                return 0
            
            # 只清空分析相关字段，保留视频和元数据
            cursor.execute(
                """
                UPDATE videos SET
                    gameplay_analysis = NULL,
                    analysis_model = NULL,
                    analyzed_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE game_name = ?
                """,
                (game_name,)
            )
            
            conn.commit()
            conn.close()
            
            print(f"已清除 {count} 条关于 '{game_name}' 的AI分析结果")
            return count
        
        except Exception as e:
            print(f"清除玩法分析时出错：{str(e)}")
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
            
            # 先查询要删除的记录数
            cursor.execute('SELECT COUNT(*) FROM videos WHERE game_name = ?', (game_name,))
            count = cursor.fetchone()[0]
            
            if count == 0:
                print(f"未找到游戏 '{game_name}' 的数据")
                conn.close()
                return 0
            
            # 删除数据
            cursor.execute('DELETE FROM videos WHERE game_name = ?', (game_name,))
            conn.commit()
            conn.close()
            
            print(f"已删除 {count} 条关于 '{game_name}' 的记录")
            return count
            
        except Exception as e:
            print(f"删除游戏数据时出错：{str(e)}")
            return 0
    
    def delete_video_by_id(self, aweme_id: str) -> bool:
        """
        根据视频ID删除单条记录
        
        Args:
            aweme_id: 视频ID
        
        Returns:
            是否删除成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM videos WHERE aweme_id = ?', (aweme_id,))
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                print(f"已删除视频ID为 '{aweme_id}' 的记录")
                return True
            else:
                print(f"未找到视频ID为 '{aweme_id}' 的记录")
                return False
                
        except Exception as e:
            print(f"删除视频数据时出错：{str(e)}")
            return False
    
    def get_statistics(self) -> Dict:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 总视频数
            cursor.execute('SELECT COUNT(*) FROM videos')
            total = cursor.fetchone()[0]
            
            # 已下载数
            cursor.execute('SELECT COUNT(*) FROM videos WHERE downloaded = 1')
            downloaded = cursor.fetchone()[0]
            
            # 游戏数
            cursor.execute('SELECT COUNT(DISTINCT game_name) FROM videos')
            games = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "total_videos": total,
                "downloaded_videos": downloaded,
                "unique_games": games
            }
            
        except Exception as e:
            print(f"获取统计信息时出错：{str(e)}")
            return {}