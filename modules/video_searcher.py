"""
搜索下载视频模块
通过抖音搜索API搜索并下载游戏相关视频
"""
import requests
import os
import json
import time
from typing import Dict, Optional, List
import config
from modules.database import VideoDatabase


class VideoSearcher:
    """视频搜索和下载器"""
    
    def __init__(self, videos_dir: str = None, video_info_dir: str = None, use_database: bool = True):
        """
        初始化视频搜索器
        
        Args:
            videos_dir: 视频保存目录，默认使用配置文件中的路径
            video_info_dir: 视频信息保存目录，默认使用配置文件中的路径（已废弃，使用数据库）
            use_database: 是否使用数据库保存，默认True
        """
        self.videos_dir = videos_dir or config.VIDEOS_DIR
        self.video_info_dir = video_info_dir or config.VIDEO_INFO_DIR
        self.api_base_url = config.DOUYIN_API_BASE_URL
        self.api_token = config.DOUYIN_API_TOKEN
        self.search_endpoint = config.DOUYIN_SEARCH_ENDPOINT
        self.use_database = use_database
        
        # 确保目录存在
        os.makedirs(self.videos_dir, exist_ok=True)
        if not use_database:
            os.makedirs(self.video_info_dir, exist_ok=True)
        
        # 初始化数据库
        if use_database:
            self.db = VideoDatabase()
        else:
            self.db = None
    
    def search_videos(self, game_name: str, game_type: str = None, max_results: int = 5) -> List[Dict]:
        """
        搜索游戏相关视频（先检查数据库缓存）
        
        Args:
            game_name: 游戏名称
            game_type: 游戏类型（可选）
            max_results: 最大返回结果数
        
        Returns:
            视频信息列表，每个视频包含URL、ID等信息
        """
        # 先检查数据库中是否已有该游戏的视频
        if self.use_database and self.db:
            existing_videos = self.db.get_videos_by_game(game_name)
            if existing_videos:
                # 返回数据库中已有的视频（按点赞数排序，取第一个）
                existing_videos.sort(key=lambda x: x.get("like_count", 0), reverse=True)
                top_video = existing_videos[0]
                print(f"  ✓ 从数据库找到视频：{top_video.get('title', 'N/A')[:50]}")
                print(f"    点赞数：{top_video.get('like_count', 0):,}")
                return [top_video]
        
        if not self.api_token:
            print(f"警告：未配置抖音API Token，使用Mock数据")
            return [self._mock_search_result(game_name)]
        
        # 构建搜索关键词，只搜索玩法关键字
        keywords = [
            f"{game_name}玩法"
        ]
        
        all_videos = []
        
        # 第一步：用所有关键词搜索，收集所有视频
        print(f"开始搜索游戏 '{game_name}' 的相关视频...")
        
        for keyword in keywords:
            print(f"  搜索关键词：'{keyword}'...")
            
            # 添加请求间隔，避免频率过高
            if config.API_REQUEST_DELAY > 0:
                time.sleep(config.API_REQUEST_DELAY)
            
            # 重试机制
            success = False
            for retry in range(config.API_MAX_RETRIES):
                try:
                    # 构建请求
                    url = f"{self.api_base_url}{self.search_endpoint}"
                    headers = {
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json"
                    }
                    
                    # 首次请求参数
                    # 筛选条件：1分钟以内的视频，只要玩法演示
                    payload = {
                        "keyword": keyword,
                        "cursor": 0,
                        "sort_type": "1",  # 最多点赞，更可能找到热门玩法视频
                        "publish_time": "0",  # 不限时间
                        "filter_duration": "0-1",  # 1分钟以内
                        "content_type": "1",  # 只要视频
                        "search_id": "",
                        "backtrace": ""
                    }
                    
                    response = requests.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    
                    # 处理不同的HTTP状态码
                    if response.status_code == 200:
                        result = response.json()
                        
                        # 检查响应状态
                        if result.get("code") == 200:
                            # 解析返回数据
                            data_str = result.get("data")
                            if data_str:
                                # data可能是JSON字符串，需要解析
                                if isinstance(data_str, str):
                                    try:
                                        data = json.loads(data_str)
                                    except json.JSONDecodeError:
                                        print(f"    无法解析JSON数据：{data_str[:100]}...")
                                        data = None
                                else:
                                    data = data_str
                                
                                if data:
                                    # 提取视频信息
                                    videos = self._parse_search_results(data, game_name, keyword)
                                    
                                    # 对视频进行筛选和评分
                                    filtered_videos = self._filter_and_score_videos(videos, game_name)
                                    all_videos.extend(filtered_videos)
                                    print(f"    ✓ 找到 {len(filtered_videos)} 个视频")
                                    success = True
                                    break
                        else:
                            error_msg = result.get('message_zh') or result.get('message', '未知错误')
                            print(f"    API返回错误：{error_msg} (code: {result.get('code')})")
                            # API业务错误，不重试
                            break
                    
                    elif response.status_code == 400:
                        # 400 Bad Request - 需要重试
                        print(f"    ✗ HTTP 400: 请求参数错误")
                        try:
                            error_detail = response.json()
                            print(f"      错误详情: {error_detail.get('message', '未知')}")
                        except:
                            print(f"      响应内容: {response.text[:100]}")
                        if retry < config.API_MAX_RETRIES - 1:
                            wait_time = config.API_RETRY_DELAY * (retry + 1)
                            print(f"      等待 {wait_time} 秒后重试 ({retry + 1}/{config.API_MAX_RETRIES})...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"      达到最大重试次数，跳过该关键词")
                            break
                    
                    elif response.status_code == 401:
                        # 401 Unauthorized - 认证失败
                        print(f"    ✗ HTTP 401: 认证失败，请检查API Token是否正确")
                        break  # 不重试
                    
                    elif response.status_code == 429:
                        # 429 Too Many Requests - 请求频率过高
                        print(f"    ✗ HTTP 429: 请求频率过高，等待后重试...")
                        if retry < config.API_MAX_RETRIES - 1:
                            wait_time = config.API_RETRY_DELAY * (retry + 1)
                            print(f"      等待 {wait_time} 秒后重试...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"      达到最大重试次数，跳过该关键词")
                            break
                    
                    elif response.status_code in [500, 502, 503, 504]:
                        # 5xx 服务器错误 - 可以重试
                        print(f"    ✗ HTTP {response.status_code}: 服务器错误")
                        if retry < config.API_MAX_RETRIES - 1:
                            wait_time = config.API_RETRY_DELAY * (retry + 1)
                            print(f"      等待 {wait_time} 秒后重试 ({retry + 1}/{config.API_MAX_RETRIES})...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"      达到最大重试次数，跳过该关键词")
                            break
                    
                    else:
                        # 其他HTTP错误
                        print(f"    ✗ HTTP {response.status_code}: 请求失败")
                        try:
                            error_detail = response.text[:200]
                            print(f"      响应内容: {error_detail}")
                        except:
                            pass
                        # 对于未知错误，不重试
                        break
                    
                except requests.exceptions.Timeout:
                    print(f"    ✗ 请求超时")
                    if retry < config.API_MAX_RETRIES - 1:
                        wait_time = config.API_RETRY_DELAY * (retry + 1)
                        print(f"      等待 {wait_time} 秒后重试 ({retry + 1}/{config.API_MAX_RETRIES})...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"      达到最大重试次数，跳过该关键词")
                        break
                
                except requests.exceptions.RequestException as e:
                    print(f"    ✗ 网络请求异常：{str(e)}")
                    if retry < config.API_MAX_RETRIES - 1:
                        wait_time = config.API_RETRY_DELAY * (retry + 1)
                        print(f"      等待 {wait_time} 秒后重试 ({retry + 1}/{config.API_MAX_RETRIES})...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"      达到最大重试次数，跳过该关键词")
                        break
                
                except Exception as e:
                    print(f"    ✗ 搜索视频时出错：{str(e)}")
                    import traceback
                    traceback.print_exc()
                    break  # 其他异常不重试
            
            if not success:
                print(f"    ⚠ 关键词 '{keyword}' 搜索失败，继续搜索其他关键词...")
        
        # 第二步：统一去重（基于aweme_id）
        print(f"\n  收集到 {len(all_videos)} 个视频，开始去重...")
        seen_ids = set()
        unique_videos = []
        for video in all_videos:
            video_id = video.get("aweme_id")
            if video_id and video_id not in seen_ids:
                seen_ids.add(video_id)
                unique_videos.append(video)
        
        print(f"  去重后剩余 {len(unique_videos)} 个视频")
        
        # 如果API搜索失败，返回Mock结果
        if not unique_videos:
            print("API搜索未找到结果，使用Mock数据")
            return [self._mock_search_result(game_name)]
        
        # 第三步：统一按点赞数和播放量排序，选择最高的
        print(f"  按点赞量和播放量排序...")
        # 计算综合分数：点赞数 * 0.6 + 播放量 * 0.4（归一化后）
        for video in unique_videos:
            like_count = video.get("like_count", 0)
            play_count = video.get("play_count", 0)
            # 简单排序：优先点赞数，其次播放量
            video["_sort_score"] = like_count * 1000 + play_count  # 点赞数权重更高
        
        unique_videos.sort(key=lambda x: x.get("_sort_score", 0), reverse=True)
        
        # 显示前3个视频的点赞数和播放量（用于调试）
        if len(unique_videos) > 0:
            top_video = unique_videos[0]
            print(f"  点赞播放量最高的视频：{top_video.get('title', 'N/A')[:50]}")
            print(f"    点赞数：{top_video.get('like_count', 0):,}")
            print(f"    播放量：{top_video.get('play_count', 0):,}")
            print(f"    视频ID：{top_video.get('aweme_id')}")
        
        # 只返回点赞播放量最高的那一条
        return [unique_videos[0]] if unique_videos else []
    
    def _parse_search_results(self, data: Dict, game_name: str, search_keyword: str = "") -> List[Dict]:
        """
        解析搜索结果，提取视频信息
        
        Args:
            data: API返回的数据（已解析的JSON）
            game_name: 游戏名称
            search_keyword: 搜索关键词
        
        Returns:
            视频信息列表
        """
        videos = []
        
        try:
            # 根据API文档，数据结构可能是：
            # 1. {"status_code": 0, "data": [...]} - 标准格式
            # 2. 直接是列表 [...]
            # 3. 其他格式
            
            items = None
            
            if isinstance(data, dict):
                # 情况1: 标准格式，包含status_code和data字段
                if "status_code" in data and data.get("status_code") == 0:
                    items = data.get("data", [])
                # 情况2: 直接包含data列表
                elif "data" in data and isinstance(data["data"], list):
                    items = data["data"]
                # 情况3: 其他可能的字段名
                elif "aweme_list" in data:
                    items = data["aweme_list"]
                # 情况4: 如果data本身就是列表结构
                elif isinstance(data.get("data"), list):
                    items = data["data"]
            elif isinstance(data, list):
                # 情况5: 直接是列表
                items = data
            
            if items:
                for item in items:
                    # 提取aweme_info
                    aweme_info = None
                    
                    # 根据API文档，每个item可能有type和aweme_info字段
                    if isinstance(item, dict):
                        if "aweme_info" in item:
                            aweme_info = item["aweme_info"]
                        elif item.get("type") == 1:  # 视频类型，type=1表示视频
                            # 如果type=1，item本身可能就是aweme_info
                            aweme_info = item
                        elif "aweme_id" in item:
                            # 如果直接包含aweme_id，说明item就是aweme_info
                            aweme_info = item
                    
                    if aweme_info:
                        video_info = self._extract_video_info(aweme_info, game_name, search_keyword)
                        if video_info:
                            videos.append(video_info)
            else:
                # 调试：打印数据结构以便排查
                print(f"警告：无法从响应中提取视频列表，数据结构：{type(data)}")
                if isinstance(data, dict):
                    print(f"  可用字段：{list(data.keys())[:10]}")
        except Exception as e:
            print(f"解析搜索结果时出错：{str(e)}")
            import traceback
            traceback.print_exc()
        
        return videos
    
    def _filter_and_score_videos(self, videos: List[Dict], game_name: str) -> List[Dict]:
        """
        筛选和评分视频，确保内容相关性
        
        Args:
            videos: 视频列表
            game_name: 游戏名称
        
        Returns:
            筛选后的视频列表（按相关性评分排序）
        """
        # 相关关键词（加分项）
        relevant_keywords = [
            "玩法", "演示", "教程", "怎么玩", "如何玩", "操作", 
            "技巧", "攻略", "教学", "展示", "试玩", "体验"
        ]
        
        # 不相关关键词（排除项）
        irrelevant_keywords = [
            "宣传", "广告", "推广", "下载", "安装", "注册",
            "充值", "氪金", "抽奖", "活动", "福利", "奖励"
        ]
        
        filtered = []
        
        for video in videos:
            title = video.get("title", "").lower()
            description = video.get("description", "").lower()
            text = f"{title} {description}"
            
            # 检查是否包含不相关关键词（如果只有不相关关键词，则排除）
            has_irrelevant = any(kw in text for kw in irrelevant_keywords)
            has_relevant = any(kw in text for kw in relevant_keywords)
            
            # 如果只有不相关关键词，且没有相关关键词，则排除
            if has_irrelevant and not has_relevant:
                continue
            
            # 计算相关性评分
            score = 0
            
            # 基础分：包含游戏名称
            if game_name in text:
                score += 10
            
            # 相关关键词加分
            for kw in relevant_keywords:
                if kw in text:
                    score += 5
                    # 高优先级关键词额外加分
                    if kw in ["玩法", "演示", "怎么玩", "教程"]:
                        score += 3
            
            # 时长加分：15-60秒的视频更适合玩法演示
            duration = video.get("duration", 0)
            if 15 <= duration <= 60:
                score += 5
            elif 10 <= duration < 15:
                score += 2
            elif duration > 60:
                score -= 2  # 超过1分钟的视频可能不是纯玩法演示
            
            # 点赞数加分（热门视频可能更相关）
            like_count = video.get("like_count", 0)
            if like_count > 1000:
                score += 2
            elif like_count > 100:
                score += 1
            
            video["relevance_score"] = score
            filtered.append(video)
        
        # 按评分排序
        filtered.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return filtered
    
    def _extract_video_info(self, aweme_info: Dict, game_name: str, search_keyword: str = "") -> Optional[Dict]:
        """
        从aweme_info中提取视频信息
        
        Args:
            aweme_info: 视频详细信息
            game_name: 游戏名称
            search_keyword: 搜索关键词
        
        Returns:
            提取的视频信息字典
        """
        try:
            # 提取基本信息
            aweme_id = aweme_info.get("aweme_id", "")
            desc = aweme_info.get("desc", "")
            create_time = aweme_info.get("create_time", 0)
            
            # 提取视频播放地址
            video = aweme_info.get("video", {})
            play_addr = video.get("play_addr", {})
            video_urls = play_addr.get("url_list", [])
            
            # 尝试提取原视频URL（最高画质）
            original_video_url = None
            
            # 检查是否有bit_rate字段（包含不同清晰度的视频）
            bit_rate = video.get("bit_rate", [])
            if bit_rate and len(bit_rate) > 0:
                # 选择最高清晰度的视频（通常是第一个）
                best_quality = bit_rate[0]
                best_play_addr = best_quality.get("play_addr", {})
                best_urls = best_play_addr.get("url_list", [])
                
                # 如果bit_rate中有URL，使用它作为original_video_url
                if best_urls:
                    original_video_url = best_urls[0]
                    # 如果普通play_addr没有URL，使用bit_rate中的URL
                    if not video_urls:
                        video_urls = best_urls
            
            # 检查其他可能的原视频URL字段
            if not original_video_url:
                # 检查video字段中是否有original_video_url
                original_video_url = video.get("original_video_url") or video.get("origin_cover", {}).get("url_list", [None])[0]
            
            # 检查aweme_info中是否有原视频URL
            if not original_video_url:
                original_video_url = aweme_info.get("original_video_url") or aweme_info.get("video_url")
            
            if not video_urls:
                return None
            
            # 提取封面
            cover = video.get("cover", {})
            cover_urls = cover.get("url_list", [])
            
            # 提取作者信息
            author = aweme_info.get("author", {})
            author_name = author.get("nickname", "未知作者")
            
            # 提取统计信息
            statistics = aweme_info.get("statistics", {})
            like_count = statistics.get("digg_count", 0)
            comment_count = statistics.get("comment_count", 0)
            play_count = statistics.get("play_count", 0)
            
            # 提取视频时长（毫秒转秒）
            duration_ms = video.get("duration", 0)
            duration = duration_ms / 1000 if duration_ms else 0
            
            video_info = {
                "aweme_id": aweme_id,
                "game_name": game_name,
                "title": desc[:100] if desc else f"{game_name} 相关视频",  # 限制标题长度
                "description": desc,
                "video_url": video_urls[0] if video_urls else "",  # 使用第一个URL
                "video_urls": video_urls,  # 保存所有URL
                "original_video_url": original_video_url,  # 原视频URL（最高画质，如果API返回）
                "cover_url": cover_urls[0] if cover_urls else "",
                "author_name": author_name,
                "author_uid": author.get("uid", ""),
                "duration": duration,
                "like_count": like_count,
                "comment_count": comment_count,
                "play_count": play_count,
                "create_time": create_time,
                "share_url": aweme_info.get("share_url", ""),
                "search_keyword": search_keyword  # 记录搜索关键词
            }
            
            # 如果有原视频URL，打印提示
            if original_video_url:
                print(f"  ✓ 找到原视频URL（最高画质）: {original_video_url[:60]}...")
            
            # 保存到数据库
            if self.use_database and self.db:
                self.db.save_video(video_info)
                print(f"  ✓ 视频信息已保存到数据库: {aweme_id}")
            
            return video_info
            
        except Exception as e:
            print(f"提取视频信息时出错：{str(e)}")
            return None
    
    def save_video_info(self, video_info: Dict) -> str:
        """
        保存视频信息（URL和ID）到数据库或文件
        
        Args:
            video_info: 视频信息字典
        
        Returns:
            保存的文件路径或数据库记录ID
        """
        # 优先使用数据库
        if self.use_database and self.db:
            success = self.db.save_video(video_info)
            if success:
                return f"db:{video_info.get('aweme_id')}"
            else:
                print("数据库保存失败，尝试保存到文件")
        
        # 降级到文件保存
        aweme_id = video_info.get("aweme_id", "unknown")
        game_name = video_info.get("game_name", "unknown")
        
        # 创建文件名
        filename = f"{game_name}_{aweme_id}.json"
        filepath = os.path.join(self.video_info_dir, filename)
        
        # 保存为JSON格式
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(video_info, f, ensure_ascii=False, indent=2)
            print(f"视频信息已保存到：{filepath}")
            return filepath
        except Exception as e:
            print(f"保存视频信息时出错：{str(e)}")
            return ""
    
    def download_video(self, video_info: Dict, use_download_api: bool = None) -> Optional[str]:
        """
        下载视频到本地
        
        下载逻辑（简化版）：
        1. 优先使用免费的video_url直接下载
        2. 如果普通URL下载失败，使用付费的最高画质API（如果启用）
        
        Args:
            video_info: 视频信息字典，必须包含aweme_id和video_url
            use_download_api: 已废弃，保留以兼容旧代码
        
        Returns:
            本地视频文件路径，如果下载失败返回None
        """
        aweme_id = video_info.get("aweme_id", "")
        game_name = video_info.get("game_name", "unknown")
        video_url = video_info.get("video_url", "")
        share_url = video_info.get("share_url", "")
        
        if not aweme_id:
            print("错误：视频aweme_id为空，无法下载")
            return None
        
        # 先检查数据库中是否已有下载的视频
        if self.use_database and self.db:
            existing = self.db.get_video(aweme_id)
            if existing and existing.get("downloaded") == 1 and existing.get("local_path"):
                local_path = existing.get("local_path")
                if os.path.exists(local_path):
                    print(f"  ✓ 视频已存在于数据库且已下载：{local_path}")
                    return local_path
        
        print(f"正在下载视频：{video_info.get('title', '未知标题')}")
        print(f"  视频ID: {aweme_id}")
        print(f"  点赞数: {video_info.get('like_count', 0):,}")
        
        # 方式1：优先使用免费的video_url直接下载
        if video_url:
            print(f"  尝试方式1: 直接下载URL（免费）")
            result = self._download_direct_url(video_url, game_name, aweme_id)
            if result:
                print(f"  ✓ 下载成功（使用免费URL）")
                return result
            print(f"  ✗ URL下载失败，尝试使用API")
        
        # 方式2：如果普通URL失败，使用付费的最高画质API
        if config.USE_HIGH_QUALITY_API_FALLBACK:
            print(f"  尝试方式2: 使用最高画质API（付费，0.005$）")
            result = self._download_via_high_quality_api(aweme_id, share_url, game_name)
            if result:
                print(f"  ✓ 下载成功（使用最高画质API）")
                return result
            print(f"  ✗ 最高画质API下载失败")
        else:
            print(f"  提示：未启用最高画质API备用方案（USE_HIGH_QUALITY_API_FALLBACK=false）")
        
        print("错误：所有下载方式都失败")
        return None
    
    def _download_via_api(self, aweme_id: str, game_name: str, video_info: Dict) -> Optional[str]:
        """
        通过下载API下载视频（使用aweme_id）
        
        Args:
            aweme_id: 视频ID
            game_name: 游戏名称
            video_info: 视频信息字典
        
        Returns:
            本地视频文件路径，如果下载失败返回None
        """
        try:
            # 构建本地文件路径
            local_path = os.path.join(self.videos_dir, f"{game_name}_{aweme_id}.mp4")
            
            # 调用下载API
            url = f"{self.api_base_url}{config.DOUYIN_DOWNLOAD_ENDPOINT}"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            # 根据实际API文档调整payload格式
            payload = {
                "aweme_id": aweme_id
            }
            
            print(f"  调用下载API: {url}")
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # 根据实际API响应格式调整
                # 可能返回的是视频URL，或者直接是视频数据
                if result.get("code") == 200:
                    # 情况1: API返回视频URL
                    download_url = result.get("data", {}).get("video_url") or result.get("video_url")
                    if download_url:
                        return self._download_direct_url(download_url, game_name, aweme_id)
                    
                    # 情况2: API直接返回视频数据
                    video_data = result.get("data", {}).get("video_data") or result.get("video_data")
                    if video_data:
                        with open(local_path, 'wb') as f:
                            if isinstance(video_data, str):
                                # 如果是base64编码
                                import base64
                                f.write(base64.b64decode(video_data))
                            else:
                                f.write(video_data)
                        print(f"视频已保存到：{local_path}")
                        return local_path
                    
                    print("错误：API响应格式不符合预期")
                    return None
                else:
                    error_msg = result.get('message_zh') or result.get('message', '未知错误')
                    print(f"下载API返回错误：{error_msg}")
                    return None
            else:
                print(f"下载API请求失败：HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"通过API下载视频时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _download_via_high_quality_api(self, aweme_id: str, share_url: str, game_name: str) -> Optional[str]:
        """
        通过最高画质API获取并下载视频（付费API，0.005$一次）
        
        Args:
            aweme_id: 视频ID
            share_url: 分享链接（可选）
            game_name: 游戏名称
        
        Returns:
            本地视频文件路径，如果下载失败返回None
        """
        try:
            if not self.api_token:
                print("  警告：未配置API Token，无法使用最高画质API")
                return None
            
            # 构建本地文件路径
            local_path = os.path.join(self.videos_dir, f"{game_name}_{aweme_id}.mp4")
            
            # 调用最高画质API
            url = f"{self.api_base_url}{config.DOUYIN_HIGH_QUALITY_ENDPOINT}"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            # 构建请求参数
            params = {}
            if aweme_id:
                params["aweme_id"] = aweme_id
            elif share_url:
                params["share_url"] = share_url
            else:
                print("  错误：aweme_id和share_url都为空")
                return None
            
            print(f"  调用最高画质API: {url}")
            print(f"  参数: aweme_id={aweme_id}")
            if share_url:
                print(f"  参数: share_url={share_url[:50]}...")
            
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("code") == 200:
                    # 解析返回数据
                    data_str = result.get("data")
                    if data_str:
                        # data可能是JSON字符串，需要解析
                        if isinstance(data_str, str):
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                print(f"  无法解析JSON数据：{data_str[:100]}...")
                                return None
                        else:
                            data = data_str
                        
                        # 获取最高画质视频URL
                        original_video_url = data.get("original_video_url")
                        if not original_video_url:
                            print("  错误：API响应中未找到original_video_url")
                            return None
                        
                        print(f"  ✓ 获取到最高画质链接")
                        print(f"  注意：本次API调用费用 0.005$")
                        
                        # 使用最高画质URL下载
                        return self._download_direct_url(original_video_url, game_name, aweme_id)
                    else:
                        print("  错误：API响应中data字段为空")
                        return None
                else:
                    error_msg = result.get('message_zh') or result.get('message', '未知错误')
                    print(f"  最高画质API返回错误：{error_msg}")
                    return None
            else:
                print(f"  最高画质API请求失败：HTTP {response.status_code}")
                if response.status_code == 401:
                    print("  认证失败，请检查API Token是否正确")
                return None
                
        except Exception as e:
            print(f"  通过最高画质API下载视频时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _download_direct_url(self, video_url: str, game_name: str, aweme_id: str) -> Optional[str]:
        """
        直接从URL下载视频
        
        Args:
            video_url: 视频URL
            game_name: 游戏名称
            aweme_id: 视频ID
        
        Returns:
            本地视频文件路径，如果下载失败返回None
        """
        try:
            # 构建本地文件路径
            local_path = os.path.join(self.videos_dir, f"{game_name}_{aweme_id}.mp4")
            
            print(f"  从URL下载: {video_url[:80]}...")
            
            # 下载视频
            response = requests.get(video_url, stream=True, timeout=60)
            
            if response.status_code == 200:
                # 获取文件大小
                total_size = int(response.headers.get('content-length', 0))
                
                with open(local_path, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            # 显示下载进度（可选）
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                if downloaded % (1024 * 1024) == 0:  # 每MB显示一次
                                    print(f"  下载进度: {percent:.1f}%")
                
                print(f"视频已保存到：{local_path}")
                
                # 更新数据库下载状态
                if self.use_database and self.db and aweme_id:
                    # 自动上传到Google Drive并获取URL（先检查数据库）
                    gdrive_url, gdrive_file_id = self._upload_to_gdrive(local_path, game_name, aweme_id)
                    # 更新数据库（如果gdrive_url已存在，不会覆盖）
                    if gdrive_url:
                        self.db.update_download_status(aweme_id, local_path, gdrive_url, gdrive_file_id)
                    else:
                        # 只更新下载状态
                        self.db.update_download_status(aweme_id, local_path)
                
                return local_path
            else:
                print(f"下载失败：HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"下载视频时出错：{str(e)}")
            return None
    
    def _upload_to_gdrive(self, video_path: str, game_name: str, aweme_id: str = None) -> tuple:
        """
        上传视频到Google Drive并获取公开访问链接（先检查数据库缓存）
        
        Args:
            video_path: 本地视频文件路径
            game_name: 游戏名称
            aweme_id: 视频ID（可选，用于检查数据库）
        
        Returns:
            (gdrive_url, gdrive_file_id) 元组，如果失败返回 (None, None)
        """
        # 先检查数据库中是否已有Google Drive链接
        if self.use_database and self.db and aweme_id:
            existing = self.db.get_video(aweme_id)
            if existing and existing.get("gdrive_url"):
                gdrive_url = existing.get("gdrive_url")
                gdrive_file_id = existing.get("gdrive_file_id")
                print(f"  ✓ 从数据库找到Google Drive链接：{gdrive_url[:60]}...")
                return (gdrive_url, gdrive_file_id)
        
        try:
            from modules.gdrive_uploader import GoogleDriveUploader
            
            print(f"  数据库中未找到Google Drive链接，正在上传到Google Drive...")
            uploader = GoogleDriveUploader()
            result = uploader.upload_video(video_path, folder_name="Game Videos")
            
            if result and result.get('public_url'):
                gdrive_url = result['public_url']
                gdrive_file_id = result.get('file_id')
                print(f"  ✓ 已上传到Google Drive")
                print(f"  Google Drive链接：{gdrive_url[:60]}...")
                
                # 保存到数据库
                if self.use_database and self.db and aweme_id:
                    self.db.update_download_status(aweme_id, video_path, gdrive_url, gdrive_file_id)
                    print(f"  ✓ 已保存Google Drive链接到数据库")
                
                return (gdrive_url, gdrive_file_id)
            else:
                print(f"  ⚠ 上传到Google Drive失败（将使用本地文件）")
                return (None, None)
                
        except ImportError:
            print(f"  ⚠ Google Drive上传功能不可用（未安装相关库）")
            return (None, None)
        except Exception as e:
            print(f"  ⚠ 上传到Google Drive时出错：{str(e)}")
            return (None, None)
    
    def get_video_ids_and_urls(self, game_name: str, game_type: str = None, max_results: int = 5) -> List[Dict]:
        """
        只获取视频的aweme_id和url，不下载视频
        
        Args:
            game_name: 游戏名称
            game_type: 游戏类型（可选）
            max_results: 最大结果数
        
        Returns:
            视频信息列表，每个包含aweme_id和video_url
        """
        videos = self.search_videos(game_name, game_type, max_results=max_results)
        
        # 只返回关键信息
        result = []
        for video in videos:
            result.append({
                "aweme_id": video.get("aweme_id"),
                "video_url": video.get("video_url"),
                "video_urls": video.get("video_urls", []),  # 所有URL
                "title": video.get("title"),
                "game_name": video.get("game_name")
            })
            # 保存完整信息
            self.save_video_info(video)
        
        return result
    
    def search_and_download(self, game_name: str, game_type: str = None, max_results: int = 1) -> Optional[str]:
        """
        搜索并下载视频的便捷方法（先检查数据库缓存）
        
        Args:
            game_name: 游戏名称
            game_type: 游戏类型（可选）
            max_results: 搜索的最大结果数，默认只取第一个
        
        Returns:
            本地视频文件路径，如果失败返回None
        """
        # 步骤1：先检查数据库中是否已有已下载的视频
        if self.use_database and self.db:
            existing_videos = self.db.get_videos_by_game(game_name)
            # 查找已下载且有本地文件的视频
            for video in existing_videos:
                if video.get("downloaded") == 1 and video.get("local_path"):
                    local_path = video.get("local_path")
                    if os.path.exists(local_path):
                        print(f"  ✓ 从数据库找到已下载的视频：{local_path}")
                        return local_path
        
        # 步骤2：如果数据库中没有，进行搜索
        print(f"  数据库中未找到已下载的视频，开始搜索...")
        videos = self.search_videos(game_name, game_type, max_results=max_results)
        
        if not videos:
            return None
        
        # 选择第一个视频（最相关的）
        video_info = videos[0]
        
        # 检查数据库中是否已有该视频信息（避免重复搜索）
        if self.use_database and self.db:
            existing = self.db.get_video(video_info.get("aweme_id"))
            if existing:
                print(f"  ✓ 视频信息已存在于数据库，使用现有数据")
                video_info = existing
        
        # 保存视频信息（URL和ID）
        self.save_video_info(video_info)
        
        # 步骤3：检查是否已下载
        if self.use_database and self.db:
            existing = self.db.get_video(video_info.get("aweme_id"))
            if existing and existing.get("downloaded") == 1 and existing.get("local_path"):
                local_path = existing.get("local_path")
                if os.path.exists(local_path):
                    print(f"  ✓ 视频已下载，使用现有文件：{local_path}")
                    return local_path
        
        # 步骤4：如果未下载，进行下载
        print(f"  视频未下载，开始下载...")
        return self.download_video(video_info)
    
    def search_video(self, game_name: str, game_type: str = None) -> Optional[Dict]:
        """
        搜索单个视频（兼容旧接口）
        
        Args:
            game_name: 游戏名称
            game_type: 游戏类型（可选）
        
        Returns:
            视频信息字典
        """
        videos = self.search_videos(game_name, game_type, max_results=1)
        return videos[0] if videos else None
    
    def _mock_search_result(self, game_name: str) -> Dict:
        """
        Mock搜索结果（当API不可用时使用）
        
        Args:
            game_name: 游戏名称
        
        Returns:
            Mock视频信息
        """
        return {
            "aweme_id": f"mock_{game_name.replace(' ', '_')}",
            "game_name": game_name,
            "title": f"{game_name} 玩法演示视频",
            "description": f"这是{game_name}的玩法演示视频，展示了游戏的核心玩法和特色功能。",
            "video_url": f"https://example.com/videos/{game_name.replace(' ', '_')}.mp4",
            "video_urls": [f"https://example.com/videos/{game_name.replace(' ', '_')}.mp4"],
            "cover_url": f"https://example.com/thumbnails/{game_name.replace(' ', '_')}.jpg",
            "author_name": "Mock作者",
            "author_uid": "mock_uid",
            "duration": 120,
            "like_count": 1000,
            "comment_count": 100,
            "play_count": 10000,
            "create_time": 0,
            "share_url": ""
        }