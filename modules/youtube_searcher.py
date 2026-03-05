"""
YouTube 视频搜索和下载模块
通过 RapidAPI 搜索 YouTube 视频，下载并上传到 Google Drive
"""
import http.client
import json
import os
import time
import requests
from typing import Dict, Optional, List
import config
from modules.database import VideoDatabase
from modules.gdrive_uploader import GoogleDriveUploader


class YouTubeSearcher:
    """YouTube 视频搜索和下载器"""
    
    def __init__(self, videos_dir: str = None, use_database: bool = True):
        """
        初始化 YouTube 搜索器
        
        Args:
            videos_dir: 视频保存目录，默认使用配置文件中的路径
            use_database: 是否使用数据库保存，默认True
        """
        self.videos_dir = videos_dir or config.VIDEOS_DIR
        # 优先使用 TikHub API（更稳定），如果没有则使用 RapidAPI
        self.tikhub_token = getattr(config, 'YOUTUBE_API_TOKEN', '') or getattr(config, 'DOUYIN_API_TOKEN', '') or os.getenv("DOUYIN_API_TOKEN", "")
        self.tikhub_base_url = getattr(config, 'YOUTUBE_API_BASE_URL', 'https://api.tikhub.io')
        self.rapidapi_key = getattr(config, 'RAPIDAPI_KEY', '') or os.getenv("RAPIDAPI_KEY", "")
        self.rapidapi_host = "youtube138.p.rapidapi.com"
        self.use_database = use_database
        
        # 确保目录存在
        os.makedirs(self.videos_dir, exist_ok=True)
        
        # 初始化数据库
        if use_database:
            self.db = VideoDatabase()
        else:
            self.db = None
    
    def search_videos(self, game_name: str, max_results: int = 5) -> List[Dict]:
        """
        搜索游戏相关视频（先检查数据库缓存）
        
        Args:
            game_name: 游戏名称
            max_results: 最大返回结果数
        
        Returns:
            视频信息列表，每个视频包含URL、ID等信息
        """
        # 先检查数据库中是否已有该游戏的视频
        if self.use_database and self.db:
            existing_game = self.db.get_game(game_name)
            if existing_game:
                has_video_info = any([
                    existing_game.get("video_id"),
                    existing_game.get("gdrive_url"),
                    existing_game.get("video_url"),
                    existing_game.get("downloaded") == 1,
                ])
                if has_video_info:
                    title_preview = str(existing_game.get("title") or "N/A")[:50]
                    print(f"  ✓ 从数据库找到游戏视频：{title_preview}")
                    print(f"    观看数：{existing_game.get('views', 0):,}")
                    return [existing_game]
        
        # 构建搜索关键词：游戏名称 + gameplay
        keywords = f"{game_name} gameplay"
        
        print(f"开始搜索游戏 '{game_name}' 的 YouTube 视频...")
        print(f"  搜索关键词：'{keywords}'...")
        
        # 添加请求间隔
        if config.API_REQUEST_DELAY > 0:
            time.sleep(config.API_REQUEST_DELAY)
        
        # 检查 API 配置
        use_rapidapi = bool(self.rapidapi_key)
        
        if not use_rapidapi:
            print(f"警告：未配置 RapidAPI Key，无法搜索视频")
            return []
        
        # 使用 RapidAPI 搜索（TikHub 可能没有搜索 API，先用 RapidAPI 搜索获取 video_id）
        videos = self._search_with_rapidapi(keywords, game_name, max_results)
        
        if not videos:
            print(f"  ✗ 未找到相关视频")
            return []
        
        print(f"  ✓ 找到 {len(videos)} 个视频")
        return videos
    
    
    def _search_with_rapidapi(self, keywords: str, game_name: str, max_results: int) -> List[Dict]:
        """
        使用 RapidAPI 搜索 YouTube 视频
        
        Args:
            keywords: 搜索关键词
            game_name: 游戏名称
            max_results: 最大结果数
        
        Returns:
            视频信息列表
        """
        videos = []
        for retry in range(config.API_MAX_RETRIES):
            try:
                conn = http.client.HTTPSConnection(self.rapidapi_host)
                
                # 构建搜索URL，必须对关键词做 URL 编码，避免出现非 ASCII 字符（如 ®）导致编码错误
                import urllib.parse
                search_query = urllib.parse.quote(keywords, safe="")
                endpoint = f"/search/?q={search_query}&hl=en&gl=US"
                
                headers = {
                    'x-rapidapi-key': self.rapidapi_key,
                    'x-rapidapi-host': self.rapidapi_host
                }
                
                conn.request("GET", endpoint, headers=headers)
                res = conn.getresponse()
                data = res.read()
                
                if res.status == 200:
                    result = json.loads(data.decode("utf-8"))
                    videos = self._parse_search_results(result, game_name, max_results)
                    conn.close()
                    break
                else:
                    print(f"  ⚠ API请求失败，状态码：{res.status}")
                    if retry < config.API_MAX_RETRIES - 1:
                        time.sleep(config.API_RETRY_DELAY)
                    conn.close()
                    
            except Exception as e:
                print(f"  ⚠ 搜索失败（尝试 {retry + 1}/{config.API_MAX_RETRIES}）：{str(e)}")
                if retry < config.API_MAX_RETRIES - 1:
                    time.sleep(config.API_RETRY_DELAY)
        
        return videos
    
    def _parse_search_results(self, result: Dict, game_name: str, max_results: int) -> List[Dict]:
        """
        解析 YouTube 搜索结果
        
        Args:
            result: API 返回的 JSON 数据
            game_name: 游戏名称
        
        Returns:
            视频信息列表
        """
        videos: List[Dict] = []
        contents = result.get("contents", [])
        
        # 先收集所有候选视频，再按“短视频优先（<=60 秒）、观看数”排序
        for item in contents:
            if item.get("type") != "video":
                continue
            
            video_data = item.get("video", {})
            if not video_data:
                continue
            
            video_id = video_data.get("videoId", "")
            title = video_data.get("title", "")
            author = video_data.get("author", {})
            author_name = author.get("title", "") if author else ""
            stats = video_data.get("stats", {})
            views = stats.get("views", 0) if stats else 0
            length_seconds = video_data.get("lengthSeconds", 0)
            thumbnails = video_data.get("thumbnails", [])
            thumbnail_url = thumbnails[-1].get("url", "") if thumbnails else ""
            
            # 构建 YouTube URL
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            
            video_info = {
                "game_name": game_name,
                "video_id": video_id,
                "title": title,
                "author_name": author_name,
                "youtube_url": youtube_url,
                "views": views,
                "duration": length_seconds,
                "thumbnail_url": thumbnail_url,
                "source": "youtube",
            }
            
            videos.append(video_info)
        
        if not videos:
            return []
        
        def _score(v: Dict) -> tuple:
            """短视频（<=60秒）优先，然后按观看数排序。"""
            dur = v.get("duration") or 0
            is_short = 1 if (dur and dur <= 60) else 0
            views_val = v.get("views") or 0
            return (is_short, views_val)
        
        # 按（是否短视频, 观看数）降序排序
        videos.sort(key=_score, reverse=True)
        
        # 只返回前 max_results 个
        return videos[:max_results]
    
    def _mock_search_result(self, game_name: str) -> Dict:
        """生成Mock搜索结果（用于测试）"""
        return {
            "game_name": game_name,
            "video_id": "mock_video_id",
            "title": f"{game_name} - Gameplay Video",
            "author_name": "Mock Channel",
            "youtube_url": "https://www.youtube.com/watch?v=mock_video_id",
            "views": 1000,
            "duration": 60,
            "thumbnail_url": "",
            "source": "youtube",
        }
    
    def download_video(self, video_info: Dict) -> Optional[str]:
        """
        下载 YouTube 视频到本地
        
        Args:
            video_info: 视频信息字典，必须包含 video_id 和 youtube_url
        
        Returns:
            本地视频文件路径，如果下载失败返回None
        """
        video_id = video_info.get("video_id", "")
        game_name = video_info.get("game_name", "unknown")
        youtube_url = video_info.get("youtube_url", "")
        
        if not video_id:
            print("错误：视频ID为空，无法下载")
            return None
        
        # 先检查数据库中是否已有下载的视频
        if self.use_database and self.db:
            existing = self.db.get_game(game_name)
            if existing and existing.get("downloaded") == 1 and existing.get("local_path"):
                local_path = existing.get("local_path")
                if os.path.exists(local_path):
                    print(f"  ✓ 视频已存在于数据库且已下载：{local_path}")
                    return local_path
        
        print(f"正在下载视频：{video_info.get('title', '未知标题')}")
        print(f"  视频ID: {video_id}")
        print(f"  观看数: {video_info.get('views', 0):,}")
        
        # 构建输出文件名
        safe_game_name = "".join(c for c in game_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        # NOTE:
        #  目前在本机环境下，使用 TikHub 返回的 googlevideo 直链下载会频繁出现
        #  ConnectionResetError / RemoteDisconnected，因此这里临时禁用
        #  TikHub 的直链下载分支，直接使用 yt-dlp 进行下载。
        #
        #  如需重新启用 TikHub 直链，只需把下面条件改回 `if self.tikhub_token:`
        #  并根据需要再增加网络稳定性/重试策略。
        #
        # 原逻辑（暂时禁用）：
        # if self.tikhub_token:
        #     video_path = self._download_with_tikhub(video_id, game_name, safe_game_name)
        #     if video_path:
        #         return video_path
        #     print(f"  ⚠ TikHub 下载失败，尝试使用 yt-dlp...")
        
        # 使用 yt-dlp 下载视频
        try:
            import yt_dlp
            
            output_template = os.path.join(self.videos_dir, f"{safe_game_name}_{video_id}.%(ext)s")
            
            ydl_opts = {
                # 优先选择非 HLS 格式（避免 fragment 超时问题）
                # 格式优先级：1) 非 HLS 的 mp4 格式 2) 720p 以下 3) 其他格式
                'format': 'bestvideo[ext=mp4][protocol!=m3u8][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][protocol!=m3u8][height<=720]/best[protocol!=m3u8][height<=720]/best[height<=720]/best',
                'outtmpl': output_template,
                'quiet': False,
                'no_warnings': False,
                # 增加超时和重试配置
                'socket_timeout': 120,  # 增加 socket 超时时间到 120 秒
                'fragment_retries': 20,  # fragment 重试次数（增加到 20）
                'retries': 20,  # 整体重试次数（增加到 20）
                'file_access_retries': 5,  # 文件访问重试
                'fragment_read_timeout': 120,  # fragment 读取超时（增加到 120 秒）
                'http_chunk_size': 10485760,  # 10MB chunks，减少请求次数
                # 网络配置
                'nocheckcertificate': False,
                'prefer_insecure': False,
                # 下载配置
                'noprogress': False,
                'keepvideo': False,  # 下载后不保留临时文件
                # 使用更好的下载器（如果有 ffmpeg）
                'merge_output_format': 'mp4',
                # 限制下载速度，避免触发限流（可选）
                # 'limit_rate': '10M',  # 限制下载速度为 10MB/s
            }
            
            # 尝试下载，带错误处理和格式降级
            max_attempts = 3
            format_options = [
                # 第一次尝试：优先非 HLS 格式
                'bestvideo[ext=mp4][protocol!=m3u8][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][protocol!=m3u8][height<=720]/best[protocol!=m3u8][height<=720]/best[height<=720]/best',
                # 第二次尝试：允许 HLS，但限制高度
                'best[height<=480]/best[ext=mp4]/best',
                # 第三次尝试：任何可用格式
                'best',
            ]
            
            for attempt in range(max_attempts):
                try:
                    # 每次尝试使用不同的格式选择
                    ydl_opts['format'] = format_options[min(attempt, len(format_options) - 1)]
                    if attempt > 0:
                        print(f"  尝试格式选项 {attempt + 1}...")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([youtube_url])
                    break  # 成功则退出循环
                except Exception as e:
                    error_msg = str(e)
                    if attempt < max_attempts - 1:
                        print(f"  ⚠ 下载失败（尝试 {attempt + 1}/{max_attempts}）：{error_msg[:100]}")
                        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                            print(f"  检测到超时错误，将尝试更低画质格式...")
                        else:
                            print(f"  等待 5 秒后重试...")
                        time.sleep(5)
                    else:
                        print(f"  ✗ 下载失败（已重试 {max_attempts} 次）：{error_msg[:200]}")
                        # 清理可能的不完整文件
                        for ext in ['mp4', 'webm', 'mkv', 'part', 'ytdl']:
                            incomplete_path = os.path.join(self.videos_dir, f"{safe_game_name}_{video_id}.{ext}")
                            if os.path.exists(incomplete_path):
                                try:
                                    os.remove(incomplete_path)
                                    print(f"  已清理不完整文件：{incomplete_path}")
                                except:
                                    pass
                        return None
            
            # 查找下载的文件
            expected_path = os.path.join(self.videos_dir, f"{safe_game_name}_{video_id}.mp4")
            if os.path.exists(expected_path):
                # 检查文件大小，如果太小可能是下载不完整
                file_size = os.path.getsize(expected_path)
                if file_size < 1024:  # 小于 1KB 可能是空文件
                    print(f"  ⚠ 下载的文件可能不完整（大小：{file_size} 字节）")
                    os.remove(expected_path)
                    return None
                
                print(f"  ✓ 下载成功：{expected_path} ({file_size / 1024 / 1024:.2f} MB)")
                
                # 保存到数据库
                if self.use_database and self.db:
                    self.db.update_download_status(game_name, expected_path, None, None)
                
                return expected_path
            else:
                # 尝试查找其他格式
                for ext in ['mp4', 'webm', 'mkv']:
                    alt_path = os.path.join(self.videos_dir, f"{safe_game_name}_{video_id}.{ext}")
                    if os.path.exists(alt_path):
                        file_size = os.path.getsize(alt_path)
                        if file_size < 1024:
                            print(f"  ⚠ 下载的文件可能不完整（大小：{file_size} 字节）")
                            os.remove(alt_path)
                            continue
                        
                        print(f"  ✓ 下载成功：{alt_path} ({file_size / 1024 / 1024:.2f} MB)")
                        if self.use_database and self.db:
                            self.db.update_download_status(game_name, alt_path, None, None)
                        return alt_path
                
                print(f"  ✗ 下载失败：文件不存在")
                return None
                
        except ImportError:
            print(f"  ✗ 未安装 yt-dlp，请运行: pip install yt-dlp")
            return None
        except Exception as e:
            print(f"  ✗ 下载失败：{str(e)}")
            return None
    
    def _download_with_tikhub(self, video_id: str, game_name: str, safe_game_name: str) -> Optional[str]:
        """
        使用 TikHub API 获取视频信息并下载
        
        Args:
            video_id: YouTube 视频ID
            game_name: 游戏名称
            safe_game_name: 安全的游戏名称（用于文件名）
        
        Returns:
            本地视频文件路径，如果失败返回None
        """
        try:
            print(f"  使用 TikHub API 获取视频信息...")
            
            if not self.tikhub_token:
                print(f"  ⚠ TikHub API Token 未配置")
                return None
            
            # 调用 TikHub API 获取视频信息
            conn = http.client.HTTPSConnection("api.tikhub.io")
            # 简化参数，只传递必要的 video_id 和 lang
            # 注意：根据示例，参数中的 null 可能不需要传递，或者需要作为字符串 "null" 传递
            endpoint = f"/api/v1/youtube/web/get_video_info?video_id={video_id}&lang=zh-CN"
            
            headers = {
                'Authorization': f'Bearer {self.tikhub_token}'
            }
            
            print(f"  请求端点：{endpoint}")
            print(f"  Token 前缀：{self.tikhub_token[:10]}...")
            
            conn.request("GET", endpoint, "", headers)
            res = conn.getresponse()
            data = res.read()
            conn.close()
            
            if res.status != 200:
                error_body = data.decode("utf-8") if data else ""
                print(f"  ⚠ TikHub API 请求失败，状态码：{res.status}")
                print(f"  错误响应：{error_body[:500]}")
                
                # 如果是 403，可能是 Token 问题
                if res.status == 403:
                    print(f"  💡 提示：403 错误通常表示：")
                    print(f"    1. Token 无效或已过期")
                    print(f"    2. Token 没有访问 YouTube API 的权限")
                    print(f"    3. API 端点或参数格式不正确")
                    print(f"  请检查：")
                    print(f"    - DOUYIN_API_TOKEN 是否正确配置在 .env 文件中")
                    print(f"    - Token 是否有 YouTube API 访问权限")
                    print(f"    - 是否需要在 TikHub 控制台启用 YouTube API")
                
                return None
            
            result = json.loads(data.decode("utf-8"))
            
            if result.get("code") != 200:
                print(f"  ⚠ TikHub API 返回错误：{result.get('message', '未知错误')}")
                return None
            
            video_data = result.get("data")
            if not video_data:
                print(f"  ⚠ TikHub API 未返回视频数据")
                print(f"  API 响应：{json.dumps(result, indent=2, ensure_ascii=False)[:500]}")
                return None
            
            # 提取视频下载链接
            # 根据 TikHub API 文档，可能需要从不同的字段提取
            video_url = None
            
            # 尝试多种可能的字段路径
            if isinstance(video_data, dict):
                # 可能的路径：
                # - data.video_url
                # - data.download_url
                # - data.videos[0].url (如果有 videos 数组)
                # - data.streaming_data.formats[0].url (YouTube 格式)
                # - data.playability_status.streaming_data.formats[0].url
                
                # 首先尝试直接字段
                video_url = (
                    video_data.get("video_url") or
                    video_data.get("download_url") or
                    None
                )
                
                # 从 data.videos.items 中提取（根据实际 API 响应结构）
                # videos 是一个对象，包含 errorId, expiration, items 字段
                if not video_url:
                    videos_obj = video_data.get("videos", {})
                    if videos_obj and isinstance(videos_obj, dict):
                        videos_items = videos_obj.get("items", [])
                        if videos_items and len(videos_items) > 0:
                            print(f"  找到 {len(videos_items)} 个视频格式")
                            
                            # 优先选择包含音频的 mp4 格式（itag=18 通常是 360p 带音频）
                            # 或者选择 720p 以下的 mp4 格式
                            for item in videos_items:
                                mime_type = item.get("mimeType", "")
                                quality = item.get("quality", "")
                                has_audio = item.get("hasAudio", False)
                                
                                # 优先选择：mp4 格式，有音频，720p 以下
                                if mime_type.startswith("video/mp4") and has_audio:
                                    height = item.get("height", 0)
                                    if height <= 720:
                                        video_url = item.get("url")
                                        print(f"  选择格式：{quality} ({mime_type}), 大小：{item.get('sizeText', 'N/A')}, 有音频")
                                        break
                            
                            # 如果还没找到，选择第一个 mp4 格式
                            if not video_url:
                                for item in videos_items:
                                    if item.get("mimeType", "").startswith("video/mp4"):
                                        video_url = item.get("url")
                                        quality = item.get("quality", "unknown")
                                        print(f"  选择格式：{quality} ({item.get('mimeType', '')}), 大小：{item.get('sizeText', 'N/A')}")
                                        break
                            
                            # 如果还没找到，使用第一个视频
                            if not video_url and videos_items:
                                video_url = videos_items[0].get("url")
                                quality = videos_items[0].get("quality", "unknown")
                                print(f"  使用第一个格式：{quality}, 大小：{videos_items[0].get('sizeText', 'N/A')}")
            
            if not video_url:
                print(f"  ⚠ 未找到视频下载链接")
                print(f"  API 响应数据：{json.dumps(video_data, indent=2, ensure_ascii=False)[:500]}")
                return None
            
            print(f"  ✓ 获取到视频下载链接")
            
            # 下载视频
            output_path = os.path.join(self.videos_dir, f"{safe_game_name}_{video_id}.mp4")
            
            # 使用重试机制下载
            max_retries = 3
            for retry in range(max_retries):
                try:
                    if retry > 0:
                        print(f"  重试下载（第 {retry + 1}/{max_retries} 次）...")
                        time.sleep(5)  # 等待 5 秒后重试
                    
                    print(f"  正在下载视频...")
                    # 使用更长的超时时间：(连接超时, 读取超时)
                    # 连接超时 30 秒，读取超时 300 秒（5分钟）
                    # 对于大文件，读取超时需要足够长
                    response = requests.get(
                        video_url, 
                        stream=True, 
                        timeout=(30, 300)  # (connect_timeout, read_timeout)
                    )
                    
                    if response.status_code != 200:
                        print(f"  ⚠ 下载失败，HTTP 状态码：{response.status_code}")
                        if retry < max_retries - 1:
                            continue
                        return None
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    last_progress_time = time.time()
                    
                    # 使用临时文件，下载完成后再重命名
                    temp_path = output_path + '.tmp'
                    
                    with open(temp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192 * 4):  # 增大 chunk 大小到 32KB
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                
                                # 每 1MB 或每 5 秒打印一次进度
                                current_time = time.time()
                                if total_size > 0:
                                    percent = (downloaded_size / total_size) * 100
                                    if (downloaded_size % (1024 * 1024) == 0) or (current_time - last_progress_time >= 5):
                                        print(f"  下载进度：{percent:.1f}% ({downloaded_size / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB)")
                                        last_progress_time = current_time
                                else:
                                    # 如果没有 content-length，每 5 秒打印一次
                                    if current_time - last_progress_time >= 5:
                                        print(f"  已下载：{downloaded_size / 1024 / 1024:.1f} MB")
                                        last_progress_time = current_time
                    
                    # 下载完成，重命名临时文件
                    if os.path.exists(temp_path):
                        if os.path.exists(output_path):
                            os.remove(output_path)  # 删除旧文件
                        os.rename(temp_path, output_path)
                    
                    # 验证文件
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                        if file_size < 1024:
                            print(f"  ⚠ 下载的文件可能不完整（大小：{file_size} 字节）")
                            os.remove(output_path)
                            if retry < max_retries - 1:
                                continue
                            return None
                        
                        # 如果知道总大小，验证是否完整
                        if total_size > 0 and abs(file_size - total_size) > 1024:
                            print(f"  ⚠ 文件大小不匹配（期望：{total_size} 字节，实际：{file_size} 字节）")
                            if retry < max_retries - 1:
                                continue
                        
                        print(f"  ✓ 下载成功：{output_path} ({file_size / 1024 / 1024:.2f} MB)")
                        
                        # 保存到数据库
                        if self.use_database and self.db:
                            self.db.update_download_status(game_name, output_path, None, None)
                        
                        return output_path
                    else:
                        print(f"  ✗ 下载失败：文件不存在")
                        if retry < max_retries - 1:
                            continue
                        return None
                        
                except requests.exceptions.Timeout as e:
                    print(f"  ⚠ 下载超时：{str(e)}")
                    # 清理可能的不完整文件
                    temp_path = output_path + '.tmp'
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    if retry < max_retries - 1:
                        print(f"  将重试下载...")
                        continue
                    return None
                    
                except requests.exceptions.RequestException as e:
                    print(f"  ⚠ 下载请求失败：{str(e)}")
                    # 清理可能的不完整文件
                    temp_path = output_path + '.tmp'
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    if retry < max_retries - 1:
                        print(f"  将重试下载...")
                        continue
                    return None
                    
                except Exception as e:
                    print(f"  ⚠ 下载过程出错：{str(e)}")
                    # 清理可能的不完整文件
                    temp_path = output_path + '.tmp'
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    if retry < max_retries - 1:
                        print(f"  将重试下载...")
                        continue
                    return None
            
            print(f"  ✗ 下载失败：已重试 {max_retries} 次")
            return None
                
        except Exception as e:
            print(f"  ⚠ TikHub 下载失败：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def upload_to_gdrive(self, video_path: str, game_name: str) -> Optional[str]:
        """
        上传视频到 Google Drive 并获取公开访问链接
        
        Args:
            video_path: 本地视频文件路径
            game_name: 游戏名称
        
        Returns:
            Google Drive 公开访问URL，如果失败返回None
        """
        if not os.path.exists(video_path):
            print(f"错误：视频文件不存在：{video_path}")
            return None
        
        # 检查数据库中是否已有 Google Drive 链接
        if self.use_database and self.db:
            existing = self.db.get_game(game_name)
            if existing and existing.get("gdrive_url"):
                print(f"  ✓ 数据库中已有Google Drive链接")
                return existing.get("gdrive_url")
        
        try:
            print(f"  正在上传到Google Drive...")
            uploader = GoogleDriveUploader()
            result = uploader.upload_video(video_path, folder_name="Game Videos")
            
            if result and result.get('public_url'):
                gdrive_url = result['public_url']
                gdrive_file_id = result.get('file_id')
                print(f"  ✓ 已上传到Google Drive")
                print(f"  Google Drive链接：{gdrive_url[:60]}...")
                
                # 保存到数据库
                if self.use_database and self.db:
                    self.db.update_download_status(game_name, video_path, gdrive_url, gdrive_file_id)
                    print(f"  ✓ 已保存Google Drive链接到数据库")
                
                return gdrive_url
            else:
                print(f"  ⚠ 上传到Google Drive失败")
                return None
                
        except ImportError:
            print(f"  ⚠ Google Drive上传功能不可用（未安装相关库）")
            return None
        except Exception as e:
            print(f"  ⚠ 上传到Google Drive时出错：{str(e)}")
            return None
    
    def search_and_download(self, game_name: str, max_results: int = 1, upload_to_gdrive: bool = True) -> Optional[Dict]:
        """
        搜索、下载并上传视频（完整流程）
        
        Args:
            game_name: 游戏名称
            max_results: 最大搜索结果数
            upload_to_gdrive: 是否上传到Google Drive
        
        Returns:
            视频信息字典（包含gdrive_url），如果失败返回None
        """
        # 搜索视频
        videos = self.search_videos(game_name, max_results=max_results)
        if not videos:
            return None
        
        # 使用第一个视频
        video_info = videos[0]
        
        # 下载视频
        video_path = self.download_video(video_info)
        if not video_path:
            return None
        
        # 上传到Google Drive
        if upload_to_gdrive:
            gdrive_url = self.upload_to_gdrive(video_path, game_name)
            if gdrive_url:
                video_info['gdrive_url'] = gdrive_url
                video_info['local_path'] = video_path
                return video_info
        
        video_info['local_path'] = video_path
        return video_info
