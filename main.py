"""
小游戏热榜玩法解析日报工作流
主程序入口
"""
import sys
import os
import time
from datetime import datetime
from typing import Optional, List, Dict
from modules.rank_extractor import RankExtractor
from modules.video_searcher import VideoSearcher
from modules.video_analyzer import VideoAnalyzer
from modules.report_generator import ReportGenerator
from modules.feishu_sender import FeishuSender
import config


class GameAnalysisWorkflow:
    """游戏分析工作流"""
    
    def __init__(
        self,
        rankings_csv_path: Optional[str] = None,
        force_refresh_analysis: bool = False,
        skip_screenshots: bool = False,
        platform: Optional[str] = None,
        send_to: Optional[str] = None,
    ):
        """
        初始化工作流
        
        Args:
            rankings_csv_path: CSV文件路径
            force_refresh_analysis: 是否强制刷新分析
            skip_screenshots: 是否跳过截图
            platform: 平台类型，'dy'表示抖音，'wx'表示微信小游戏，None表示不限制
            send_to: 发送目标，'feishu'/'wecom'/'sheets'/'all'，None表示默认（飞书）
        """
        self.rank_extractor = RankExtractor(csv_path=rankings_csv_path, platform=platform) if rankings_csv_path else RankExtractor(platform=platform)
        self.video_searcher = VideoSearcher()
        self.video_analyzer = VideoAnalyzer()
        self.report_generator = ReportGenerator()
        self.feishu_sender = FeishuSender()
        # 工作流可选行为
        self.force_refresh_analysis = bool(force_refresh_analysis)
        self.skip_screenshots = bool(skip_screenshots)
        self.send_to = send_to or 'feishu'  # 默认发送到飞书
    
    def _extract_and_upload_screenshot(self, video_path: str, game_name: str) -> Optional[List[str]]:
        """
        从视频中提取截图并上传到飞书服务器
        
        Args:
            video_path: 视频文件路径
            game_name: 游戏名称
        
        Returns:
            所有截图的image_key列表（开头、中间、结尾），如果失败返回None
        """
        try:
            # 检查是否有视频处理库
            try:
                import cv2
                from PIL import Image
                VIDEO_PROCESSING_AVAILABLE = True
            except ImportError:
                VIDEO_PROCESSING_AVAILABLE = False
            
            if not VIDEO_PROCESSING_AVAILABLE:
                return None
            
            # 提取视频开头、中间、结尾三帧作为截图
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                cap.release()
                return None
            
            # 计算三个时间点的帧数：开头、中间、结尾
            start_frame = 0
            middle_frame = total_frames // 2
            end_frame = total_frames - 1
            
            frame_indices = [
                (start_frame, "开头"),
                (middle_frame, "中间"),
                (end_frame, "结尾")
            ]
            
            screenshots = []
            
            for frame_idx, frame_name in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret:
                    continue
                
                # 转换BGR到RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                
                # 调整大小（限制最大尺寸为1920x1080）
                max_width, max_height = 1920, 1080
                if pil_image.width > max_width or pil_image.height > max_height:
                    pil_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                screenshots.append((pil_image, frame_name))
            
            cap.release()
            
            if not screenshots:
                return None
            
            # 上传所有截图到飞书服务器，返回第一张的image_key（用于日报显示）
            screenshot_keys = []
            try:
                from modules.feishu_sender import FeishuSender
                feishu_sender = FeishuSender()
                
                import tempfile
                temp_dir = tempfile.gettempdir()
                
                for pil_image, frame_name in screenshots:
                    screenshot_path = os.path.join(temp_dir, f"{game_name}_screenshot_{frame_name}.jpg")
                    pil_image.save(screenshot_path, format='JPEG', quality=90)
                    
                    # 上传到飞书并获取image_key
                    image_key = self._upload_image_to_feishu(feishu_sender, screenshot_path)
                    
                    # 删除临时文件
                    try:
                        os.remove(screenshot_path)
                    except:
                        pass
                    
                    if image_key:
                        screenshot_keys.append(image_key)
                        print(f"  ✓ 已上传{frame_name}截图到飞书")
                
                # 返回所有截图的image_key列表（用于日报显示）
                if screenshot_keys:
                    return screenshot_keys
            except Exception as e:
                print(f"  上传截图时出错：{str(e)}")
                import traceback
                traceback.print_exc()
            
            return None
            
        except Exception as e:
            print(f"  提取截图时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _upload_image_to_feishu(self, feishu_sender: FeishuSender, image_path: str) -> Optional[str]:
        """
        上传图片到飞书服务器并获取image_key
        
        Args:
            feishu_sender: 飞书发送器实例
            image_path: 图片文件路径
        
        Returns:
            image_key，如果失败返回None
        """
        try:
            # 检查是否配置了飞书应用凭证
            app_id = config.FEISHU_APP_ID if hasattr(config, 'FEISHU_APP_ID') else None
            app_secret = config.FEISHU_APP_SECRET if hasattr(config, 'FEISHU_APP_SECRET') else None
            
            if not app_id or not app_secret:
                print(f"    ⚠ 未配置飞书应用凭证，无法上传图片到飞书")
                return None
            
            # 步骤1：获取访问令牌
            import requests
            token_url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/'
            token_headers = {'Content-Type': 'application/json'}
            token_data = {'app_id': app_id, 'app_secret': app_secret}
            
            token_response = requests.post(token_url, json=token_data, headers=token_headers)
            token_result = token_response.json()
            
            if token_result.get('code') != 0:
                print(f"    获取访问令牌失败：{token_result.get('msg', '未知错误')}")
                return None
            
            tenant_access_token = token_result.get('tenant_access_token')
            
            # 步骤2：上传图片
            upload_url = 'https://open.feishu.cn/open-apis/im/v1/images'
            
            # 检测图片MIME类型
            mime_type = 'image/jpeg'
            if image_path.lower().endswith('.png'):
                mime_type = 'image/png'
            elif image_path.lower().endswith('.gif'):
                mime_type = 'image/gif'
            
            # 使用MultipartEncoder正确设置Content-Type
            try:
                from requests_toolbelt.multipart.encoder import MultipartEncoder
                
                with open(image_path, 'rb') as f:
                    form = {
                        'image_type': 'message',
                        'image': (os.path.basename(image_path), f, mime_type)
                    }
                    multi_form = MultipartEncoder(form)
                    upload_headers = {
                        'Authorization': f'Bearer {tenant_access_token}',
                        'Content-Type': multi_form.content_type
                    }
                    upload_response = requests.post(upload_url, headers=upload_headers, data=multi_form)
            except ImportError:
                # 如果没有requests_toolbelt，使用标准方式
                with open(image_path, 'rb') as f:
                    files = {
                        'image_type': (None, 'message'),
                        'image': (os.path.basename(image_path), f, mime_type)
                    }
                    upload_headers = {
                        'Authorization': f'Bearer {tenant_access_token}'
                    }
                    upload_response = requests.post(upload_url, headers=upload_headers, files=files)
            
            upload_result = upload_response.json()
            
            if upload_result.get('code') != 0:
                error_msg = upload_result.get('msg', '未知错误')
                print(f"    上传图片失败：{error_msg}")
                return None
            
            image_key = upload_result.get('data', {}).get('image_key')
            if not image_key:
                print(f"    上传图片失败：未获取到image_key")
                return None
            
            return image_key
            
        except Exception as e:
            print(f"    上传图片到飞书时出错：{str(e)}")
            return None
    
    def step0_scrape_rankings(self) -> bool:
        """
        步骤0：检查游戏排行榜CSV文件
        
        Returns:
            是否成功
        """
        print("【步骤0】检查游戏排行榜CSV文件...")
        try:
            import os
            extractor = self.rank_extractor
            csv_path = extractor.get_effective_csv_path()

            if not os.path.exists(csv_path):
                platform_hint = ""
                if self.rank_extractor.platform:
                    platform_name = "抖音" if self.rank_extractor.platform == 'dy' else "微信小游戏"
                    platform_hint = f"（当前选择平台：{platform_name}）"
                print(f"⚠ CSV文件不存在：{csv_path}{platform_hint}")
                print("  提示：请先运行 gravity 爬取脚本，生成 data/人气榜/<日期>.csv（或设置环境变量 RANKINGS_CSV_PATH 指向CSV/目录）")
                if self.rank_extractor.platform:
                    print(f"  提示：使用 --platform dy 选择抖音榜单，--platform wx 选择微信小游戏榜单")
                return False
            
            # 验证CSV文件格式并统计数量
            games = extractor.get_top_games(top_n=1)  # 只读取一条验证格式
            
            if not games:
                print(f"⚠ CSV文件格式不正确或为空：{csv_path}")
                print("  提示：当前工作流默认读取 data/人气榜 下最新CSV；请确保表头包含：排名,游戏名称,游戏类型,...")
                return False
            
            # 统计总游戏数量（读取所有数据）
            all_games = extractor.get_top_games(top_n=None)
            game_count = len(all_games) if all_games else 0
            
            platform_info = ""
            if self.rank_extractor.platform:
                platform_name = "抖音" if self.rank_extractor.platform == 'dy' else "微信小游戏"
                platform_info = f"（平台：{platform_name}）"
            print(f"✓ CSV文件检查通过：{csv_path}{platform_info}")
            print(f"  文件包含 {game_count} 个游戏\n")
            return True
        except Exception as e:
            print(f"⚠ 检查CSV文件失败：{str(e)}\n")
            return False
    
    def step1_extract_rankings(self, max_games: int = None) -> Optional[List[Dict]]:
        """
        步骤1：提取游戏排行榜
        
        Args:
            max_games: 最大处理游戏数量，如果为None则处理所有游戏
        
        Returns:
            游戏列表，如果失败返回None
        """
        print("【步骤1】提取游戏排行榜...")
        # 如果max_games为None，处理所有游戏（不限制）
        if max_games is None:
            games = self.rank_extractor.get_top_games(top_n=None)  # None表示处理所有
        else:
            games = self.rank_extractor.get_top_games(top_n=max_games)
        
        if not games:
            print("错误：未能提取到游戏信息\n")
            return None
        
        print(f"成功提取 {len(games)} 个游戏")

        # 将排行榜字段写入数据库（A方式：覆盖排行榜字段，不影响视频/截图/玩法分析字段）
        def _none_if_placeholder(v):
            if v is None:
                return None
            s = str(v).strip()
            if not s or s in {"--", "N/A", "None"}:
                return None
            return s

        if getattr(self, "video_searcher", None) and self.video_searcher.use_database and self.video_searcher.db:
            for g in games:
                try:
                    game_name = (g.get("游戏名称") or "").strip()
                    if not game_name:
                        continue
                    self.video_searcher.db.save_game(
                        {
                            "game_name": game_name,
                            "game_rank": _none_if_placeholder(g.get("排名")),
                            "game_company": _none_if_placeholder(g.get("开发公司")),
                            "rank_change": _none_if_placeholder(g.get("排名变化")),
                            "platform": _none_if_placeholder(g.get("平台")),
                            "source": _none_if_placeholder(g.get("来源")),
                            "board_name": _none_if_placeholder(g.get("榜单")),
                            "monitor_date": _none_if_placeholder(g.get("监控日期")),
                        }
                    )
                except Exception:
                    # 写库失败不应阻断工作流（后续仍可从CSV读取）
                    continue
        
        # 保存中间产物
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"data/step1_rankings_{timestamp}.json"
        try:
            os.makedirs("data", exist_ok=True)
            import json
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(games, f, ensure_ascii=False, indent=2)
            print(f"  中间产物已保存到：{output_file}\n")
        except Exception as e:
            print(f"  保存中间产物失败：{str(e)}\n")
        
        return games
    
    def step2_search_videos(self, games: List[Dict]) -> List[Dict]:
        """
        步骤2：搜索并下载视频
        
        Args:
            games: 游戏列表
        
        Returns:
            视频信息列表
        """
        print("【步骤2】搜索并下载视频...")
        video_results = []
        
        for idx, game in enumerate(games, 1):
            # 保留原始 CSV/榜单信息（不要被后续数据库查询覆盖）
            csv_game = game.copy() if isinstance(game, dict) else {}
            game_name = game.get('游戏名称', '未知游戏')
            game_type = game.get('游戏类型')  # 保存原始的游戏类型信息
            print(f"\n处理游戏 {idx}/{len(games)}: {game_name}")

            def _none_if_placeholder(v):
                if v is None:
                    return None
                s = str(v).strip()
                if not s or s in {"--", "N/A", "None"}:
                    return None
                return s

            # 先把排行榜字段落库（避免后续只跑step2时数据库缺少公司/来源/监控日期等信息）
            if self.video_searcher.use_database and self.video_searcher.db:
                try:
                    self.video_searcher.db.save_game(
                        {
                            "game_name": game_name,
                            "game_rank": _none_if_placeholder(csv_game.get("排名")),
                            "game_company": _none_if_placeholder(csv_game.get("开发公司")),
                            "rank_change": _none_if_placeholder(csv_game.get("排名变化")),
                            "platform": _none_if_placeholder(csv_game.get("平台")),
                            "source": _none_if_placeholder(csv_game.get("来源")),
                            "board_name": _none_if_placeholder(csv_game.get("榜单")),
                            "monitor_date": _none_if_placeholder(csv_game.get("监控日期")),
                        }
                    )
                except Exception:
                    pass
            
            # 检查数据库中是否已有视频
            video_info = None
            video_path = None
            video_url = None
            aweme_id = None
            
            if self.video_searcher.use_database and self.video_searcher.db:
                db_game = self.video_searcher.db.get_game(game_name)
                videos = [db_game] if db_game else []
                if videos:
                    video_info = videos[0]
                    aweme_id = video_info.get("aweme_id")
                    
                    if video_info.get("downloaded") == 1 and video_info.get("local_path"):
                        video_path = video_info.get("local_path")
                        if os.path.exists(video_path):
                            print(f"  ✓ 从数据库找到已下载的视频：{video_path}")
                        else:
                            video_path = None
                    
                    gdrive_url = video_info.get("gdrive_url")
                    if gdrive_url:
                        video_url = gdrive_url
                        print(f"  ✓ 从数据库找到Google Drive URL：{video_url[:50]}...")
            
            # 如果数据库中没有，进行搜索和下载
            if not video_path or not video_url:
                if not video_path:
                    print(f"  数据库中未找到已下载的视频，开始搜索...")
                    video_path = self.video_searcher.search_and_download(
                        game_name=game_name,
                        game_type=game_type  # 使用保存的原始游戏类型
                    )
                
                # 重新从数据库获取最新信息
                if self.video_searcher.use_database and self.video_searcher.db:
                    db_game = self.video_searcher.db.get_game(game_name)
                    videos = [db_game] if db_game else []
                    if videos:
                        video_info = videos[0]
                        aweme_id = video_info.get("aweme_id")
                        
                        if not video_url:
                            gdrive_url = video_info.get("gdrive_url")
                            if gdrive_url:
                                video_url = gdrive_url
                                print(f"  ✓ 从数据库获取Google Drive URL：{video_url[:50]}...")
                            elif video_path and os.path.exists(video_path):
                                print(f"  尝试上传本地视频到Google Drive...")
                                gdrive_url, gdrive_file_id = self.video_searcher._upload_to_gdrive(
                                    video_path, game_name, aweme_id
                                )
                                if gdrive_url:
                                    video_url = gdrive_url
                                    print(f"  ✓ 已上传并获取Google Drive URL：{video_url[:50]}...")
            
            # 获取完整的游戏信息（优先使用原始CSV数据，补充数据库中的视频信息）
            if video_info:
                # 使用原始的game信息（来自CSV），确保包含排名、公司等信息
                game_info = csv_game.copy() if isinstance(csv_game, dict) else {}
                # 如果数据库中有视频信息，合并进去
                if video_info:
                    game_info.update({
                        "aweme_id": video_info.get("aweme_id"),
                        "gdrive_url": video_info.get("gdrive_url"),
                        "local_path": video_info.get("local_path"),
                        # 透传抖音原始分享链接（用于报告“点击查看”跳回抖音）
                        "share_url": video_info.get("share_url"),
                        "original_video_url": video_info.get("original_video_url"),
                        "video_url": video_info.get("video_url"),
                    })
                
                video_results.append({
                    "game_name": game_name,
                    "game_info": game_info,  # 保存完整的游戏信息（包括开发公司、排名变化等）
                    "video_info": video_info,
                    "video_path": video_path,
                    "video_url": video_url,
                    "gdrive_url": video_url,  # 明确保存gdrive_url
                    "share_url": (video_info.get("share_url") if isinstance(video_info, dict) else None),
                    "original_video_url": (video_info.get("original_video_url") if isinstance(video_info, dict) else None),
                    "aweme_id": aweme_id
                })
        
        # 保存中间产物
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"data/step2_videos_{timestamp}.json"
        try:
            os.makedirs("data", exist_ok=True)
            import json
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(video_results, f, ensure_ascii=False, indent=2)
            print(f"\n✓ 视频搜索完成")
            print(f"  中间产物已保存到：{output_file}\n")
        except Exception as e:
            print(f"\n✓ 视频搜索完成")
            print(f"  保存中间产物失败：{str(e)}\n")
        
        return video_results
    
    def step3_analyze_videos(self, video_results: List[Dict]) -> List[Dict]:
        """
        步骤3：分析视频
        
        Args:
            video_results: 视频信息列表
        
        Returns:
            分析结果列表
        """
        print("【步骤3】分析视频...")
        analyses = []
        
        for idx, video_result in enumerate(video_results, 1):
            game_name = video_result.get("game_name", "未知游戏")
            video_url = video_result.get("video_url")
            video_path = video_result.get("video_path")
            # 重要：提示词需要“游戏类型”等榜单字段，优先使用 step2 组装好的 game_info（来自CSV）
            csv_game_info = video_result.get("game_info", {}) or {}
            video_info = video_result.get("video_info", {}) or {}
            
            print(f"\n处理游戏 {idx}/{len(video_results)}: {game_name}")
            
            if not video_url:
                print(f"  错误：无法获取Google Drive URL，跳过分析")
                continue
            
            if not video_url.startswith("https://drive.google.com"):
                print(f"  ✗ 错误：URL不是Google Drive链接，跳过分析")
                continue
            
            # 分析视频
            analysis = self.video_analyzer.analyze_video(
                video_path=None,
                game_name=game_name,
                game_info=csv_game_info if isinstance(csv_game_info, dict) and csv_game_info else video_info,
                video_url=video_url,
                force_refresh=bool(getattr(self, "force_refresh_analysis", False)),
            )
            
            if analysis:
                # 暂时不需要截图：默认可通过 --skip-screenshots 跳过截图提取/上传
                if not bool(getattr(self, "skip_screenshots", False)):
                    screenshot_keys = None
                    if self.video_searcher.use_database and self.video_searcher.db:
                        screenshot_keys = self.video_searcher.db.get_screenshot_key(game_name)
                        if screenshot_keys:
                            print(f"  ✓ 从数据库找到截图image_key（共{len(screenshot_keys)}张）")
                        elif video_path and os.path.exists(video_path):
                            screenshot_keys = self._extract_and_upload_screenshot(video_path, game_name)
                            if screenshot_keys:
                                self.video_searcher.db.update_screenshot_key(game_name, screenshot_keys)
                                print(f"  ✓ 已上传游戏截图到飞书并保存到数据库（共{len(screenshot_keys)}张）")
                    
                    if screenshot_keys:
                        analysis["screenshot_image_keys"] = screenshot_keys
                        analysis["screenshot_image_key"] = screenshot_keys[0] if screenshot_keys else None
                
                # 添加游戏信息和视频信息
                game_info = csv_game_info if isinstance(csv_game_info, dict) else {}
                analysis["game_rank"] = game_info.get("排名", "")
                analysis["game_company"] = game_info.get("开发公司", "")
                analysis["rank_change"] = game_info.get("排名变化", "--")
                # 额外补充：监控日期/平台/来源/榜单（来自排行榜CSV）
                analysis["monitor_date"] = game_info.get("监控日期", "")
                analysis["platform"] = game_info.get("平台", "")
                analysis["source"] = game_info.get("来源", "")
                analysis["board_name"] = game_info.get("榜单", "")
                analysis["gdrive_url"] = video_result.get("gdrive_url", video_url)
                # 报告里“点击查看”优先使用抖音分享链接
                if isinstance(video_info, dict):
                    analysis["share_url"] = video_info.get("share_url", "") or game_info.get("share_url", "")
                    analysis["original_video_url"] = video_info.get("original_video_url", "") or game_info.get("original_video_url", "")
                    analysis["video_url"] = video_info.get("video_url", "") or game_info.get("video_url", "")
                
                analyses.append(analysis)
                print(f"✓ 完成分析：{game_name}")
            else:
                print(f"✗ 分析失败：{game_name}")
        
        # 保存中间产物
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"data/step3_analyses_{timestamp}.json"
        try:
            os.makedirs("data", exist_ok=True)
            import json
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(analyses, f, ensure_ascii=False, indent=2)
            print(f"\n✓ 视频分析完成")
            print(f"  中间产物已保存到：{output_file}\n")
        except Exception as e:
            print(f"\n✓ 视频分析完成")
            print(f"  保存中间产物失败：{str(e)}\n")
        
        return analyses
    
    def step4_generate_report(self, analyses: List[Dict]) -> str:
        """
        步骤4：生成日报
        
        Args:
            analyses: 分析结果列表
        
        Returns:
            日报JSON字符串
        """
        print("【步骤4】生成日报...")
        report_json = self.report_generator.generate_daily_report(analyses)
        
        # 保存中间产物
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"data/step4_report_{timestamp}.json"
        try:
            os.makedirs("data", exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_json)
            print("✓ 日报生成完成")
            print(f"  中间产物已保存到：{output_file}\n")
        except Exception as e:
            print("✓ 日报生成完成")
            print(f"  保存中间产物失败：{str(e)}\n")
        
        return report_json
    
    def step5_send_report(self, analyses: List[Dict]) -> bool:
        """
        步骤5：发送日报到指定目标（飞书/企业微信/Google Sheets）
        
        Args:
            analyses: 分析结果列表
        
        Returns:
            是否发送成功（如果发送到多个目标，只要有一个成功就返回True）
        """
        send_to = getattr(self, 'send_to', 'feishu') or 'feishu'
        
        # 支持多个目标：all, feishu, wecom, sheets
        targets = []
        if send_to == 'all':
            targets = ['feishu', 'wecom', 'sheets']
        else:
            targets = [send_to]
        
        overall_success = False
        
        # 生成飞书格式报告（用于飞书和企业微信）
        feishu_report = None
        if 'feishu' in targets or 'wecom' in targets:
            feishu_report = self.report_generator.generate_feishu_format(analyses)
            
            # 保存发送前的卡片数据
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"data/step5_feishu_card_{timestamp}.json"
            try:
                os.makedirs("data", exist_ok=True)
                import json
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(feishu_report, f, ensure_ascii=False, indent=2)
                print(f"  飞书卡片数据已保存到：{output_file}")
            except Exception as e:
                print(f"  保存飞书卡片数据失败：{str(e)}")
        
        # 发送到飞书
        if 'feishu' in targets:
            print("【步骤5】发送日报到飞书...")
            success = self._send_to_feishu(feishu_report)
            if success:
                overall_success = True
                print("✓ 飞书发送成功\n")
            else:
                print("✗ 飞书发送失败（请检查飞书Webhook配置）\n")
        
        # 发送到企业微信
        if 'wecom' in targets:
            print("【步骤5】发送日报到企业微信...")
            success = self._send_to_wecom(feishu_report)
            if success:
                overall_success = True
                print("✓ 企业微信发送成功\n")
            else:
                print("✗ 企业微信发送失败（请检查企业微信Webhook配置）\n")
        
        # 发送到Google Sheets
        if 'sheets' in targets:
            print("【步骤5】写入日报到Google Sheets...")
            success = self._send_to_sheets(analyses)
            if success:
                overall_success = True
                print("✓ Google Sheets写入成功\n")
            else:
                print("✗ Google Sheets写入失败（请检查Google Sheets配置）\n")
        
        return overall_success
    
    def _send_to_feishu(self, feishu_report: Dict) -> bool:
        """发送到飞书"""
        if not feishu_report:
            return False
        return self.feishu_sender.send_card(feishu_report)
    
    def _send_to_wecom(self, feishu_report: Dict) -> bool:
        """发送到企业微信（使用send_step5_to_wecom.py的逻辑）"""
        if not feishu_report:
            return False
        
        try:
            # 导入send_step5_to_wecom中的函数
            # 由于send_step5_to_wecom.py使用了from __future__ import annotations，需要使用动态导入
            import sys
            from pathlib import Path
            import importlib.util
            
            # 获取项目根目录
            project_root = Path(__file__).parent
            wecom_module_path = project_root / "scripts" / "senders" / "send_step5_to_wecom.py"
            
            # 确保项目根目录在sys.path中
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            # 动态导入模块（避免__future__导入问题）
            spec = importlib.util.spec_from_file_location("send_step5_to_wecom", str(wecom_module_path))
            wecom_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wecom_module)
            
            # 提取需要的函数和类
            chunk_text = wecom_module.chunk_text
            extract_sections_from_step5 = wecom_module.extract_sections_from_step5
            get_feishu_tenant_access_token = wecom_module.get_feishu_tenant_access_token
            download_feishu_image_bytes = wecom_module.download_feishu_image_bytes
            
            from modules.wecom_sender import WeComSender
            import config
            
            # 获取企业微信webhook URL
            wecom_webhook = config.WECOM_WEBHOOK_URL or ""
            if not wecom_webhook:
                print("  警告：未配置企业微信Webhook URL (WECOM_WEBHOOK_URL)")
                return False
            
            # 创建发送器（使用与send_step5_to_wecom相同的配置）
            sender = WeComSender(
                wecom_webhook,
                min_interval_seconds=3.2,
                max_retries=3,
                retry_base_seconds=15.0,
            )
            
            # 使用send_step5_to_wecom的逻辑提取内容
            header_text, games = extract_sections_from_step5(feishu_report)
            
            # 发送头部信息
            if header_text:
                header_chunks = chunk_text(header_text, max_len=3800)
                for chunk in header_chunks:
                    sender.send_markdown(chunk)
            
            # 准备飞书token（用于下载图片）
            app_id = config.FEISHU_APP_ID or ""
            app_secret = config.FEISHU_APP_SECRET or ""
            token = None
            if app_id and app_secret:
                try:
                    token = get_feishu_tenant_access_token(app_id, app_secret)
                except Exception as e:
                    print(f"  警告：获取飞书token失败，将跳过图片发送：{e}")
            
            # 逐游戏发送：文字(分段) -> 中间截图(单独 image)
            failed_images = []
            for g in games:
                text = g.merged_text()
                text_chunks = chunk_text(text, max_len=3800)
                
                # 发送文字内容
                for chunk in text_chunks:
                    sender.send_markdown(chunk)
                
                # 发送中间截图（如果存在）
                if g.middle_img_key and token:
                    try:
                        img_bytes = download_feishu_image_bytes(g.middle_img_key, token)
                        sender.send_image_bytes(img_bytes)
                    except Exception as e:
                        failed_images.append((g.index, g.name, g.middle_img_key))
                        print(f"  [!] 游戏{g.index}《{g.name}》中间截图发送失败：{e}")
                        # 频控场景下给一点缓冲
                        time.sleep(5)
            
            if failed_images:
                print("  [!] 以下游戏的中间截图未发送成功：")
                for idx, name, key in failed_images:
                    print(f"    - 游戏{idx}《{name}》 img_key={key}")
            
            return True
            
        except ImportError as e:
            print(f"  错误：无法导入必要的模块：{e}")
            import traceback
            traceback.print_exc()
            return False
        except Exception as e:
            print(f"  发送到企业微信时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    
    def _send_to_sheets(self, analyses: List[Dict]) -> bool:
        """发送到Google Sheets"""
        try:
            import config
            
            # 检查配置
            if not config.GOOGLE_SHEET_ID:
                print("  警告：未配置Google Sheet ID (GOOGLE_SHEET_ID)")
                return False
            if not config.GOOGLE_SHEETS_CREDENTIALS:
                print("  警告：未配置Google Sheets凭证 (GOOGLE_SHEETS_CREDENTIALS)")
                return False
            
            # 尝试导入Google Sheets相关库
            try:
                from google.oauth2.credentials import Credentials
                from google.oauth2 import service_account
                from google_auth_oauthlib.flow import InstalledAppFlow
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build
            except ImportError:
                print("  错误：未安装Google Sheets API库")
                print("  请运行: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
                return False
            
            # 准备数据行
            rows = []
            # 表头
            headers = ["排名", "游戏名称", "核心玩法", "吸引力", "创新点", "视频链接", "监控日期"]
            rows.append(headers)
            
            # 数据行
            for analysis in analyses:
                game_name = analysis.get("game_name", "")
                game_rank = analysis.get("game_rank", "")
                monitor_date = analysis.get("monitor_date", "")
                
                # 提取核心玩法
                analysis_data = analysis.get("analysis_data", {})
                if isinstance(analysis_data, dict):
                    core_gameplay = analysis_data.get("core_gameplay", {}).get("description", "")
                    attraction = analysis_data.get("attraction", {}).get("description", "")
                    innovation = analysis_data.get("innovation", {}).get("description", "")
                else:
                    # 从文本中提取
                    analysis_text = analysis.get("analysis", "")
                    core_gameplay = self._extract_field(analysis_text, "核心玩法")
                    attraction = self._extract_field(analysis_text, "吸引力")
                    innovation = self._extract_field(analysis_text, "创新点")
                
                # 视频链接
                video_url = analysis.get("gdrive_url", "") or analysis.get("share_url", "")
                
                row = [
                    str(game_rank),
                    game_name,
                    core_gameplay[:500],  # 限制长度
                    attraction[:500],
                    innovation[:500],
                    video_url,
                    monitor_date
                ]
                rows.append(row)
            
            # 写入Google Sheets
            spreadsheet_id = config.GOOGLE_SHEET_ID
            # 从URL中提取ID（如果提供了完整URL）
            if "/" in spreadsheet_id:
                spreadsheet_id = spreadsheet_id.split("/")[-1]
            
            # 获取凭证
            creds = self._get_google_sheets_credentials()
            if not creds:
                return False
            
            service = build("sheets", "v4", credentials=creds)
            sheet_name = "游戏分析日报"
            
            # 创建或获取工作表
            self._get_or_create_sheet(service, spreadsheet_id, sheet_name)
            
            # 写入数据
            range_name = f"{sheet_name}!A1"
            body = {'values': rows}
            result = service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            updated_cells = result.get('updatedCells', 0)
            print(f"  ✓ 已写入 {updated_cells} 个单元格到工作表：{sheet_name}")
            
            return True
            
        except Exception as e:
            print(f"  写入Google Sheets时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _extract_field(self, text: str, field_name: str) -> str:
        """从文本中提取指定字段"""
        import re
        if not text:
            return ""
        patterns = [
            rf"{field_name}[：:]\s*(.+?)(?=\n\n|\n\*\*|$)",
            rf"{field_name}[：:]\s*(.+?)(?=\n|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    def _get_google_sheets_credentials(self):
        """获取Google Sheets凭证"""
        import config
        import json
        import os
        from pathlib import Path
        
        credentials_file = config.GOOGLE_SHEETS_CREDENTIALS
        if not credentials_file or not os.path.exists(credentials_file):
            print(f"  错误：凭证文件不存在：{credentials_file}")
            return None
        
        # 检测是否为服务账号
        try:
            with open(credentials_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                is_service_account = data.get('type') == 'service_account'
        except Exception:
            is_service_account = False
        
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        
        if is_service_account:
            # 服务账号
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_file(
                credentials_file, scopes=SCOPES
            )
        else:
            # OAuth2
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            
            creds = None
            token_file = config.GOOGLE_SHEETS_TOKEN or str(Path(credentials_file).parent / "token_sheets.json")
            
            if os.path.exists(token_file):
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            
            return creds
    
    def _get_or_create_sheet(self, service, spreadsheet_id: str, sheet_name: str):
        """获取或创建工作表"""
        try:
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheet_names = [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
            
            if sheet_name not in sheet_names:
                # 创建工作表
                request_body = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': sheet_name
                            }
                        }
                    }]
                }
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=request_body
                ).execute()
                print(f"  ✓ 已创建工作表：{sheet_name}")
        except Exception as e:
            print(f"  获取/创建工作表时出错：{str(e)}")
    
    def run(self, max_games: int = None, skip_scrape: bool = False, steps: List[int] = None):
        """
        运行完整工作流或指定步骤
        
        Args:
            max_games: 最大处理游戏数量，默认使用配置文件中的值
            skip_scrape: 是否跳过爬取步骤（直接使用现有CSV文件）
            steps: 要执行的步骤列表，如 [0,1,2,3,4,5]，None表示执行所有步骤
        """
        print("=" * 60)
        print("小游戏热榜玩法解析日报工作流")
        print("=" * 60)
        print()
        
        if steps is None:
            steps = [0, 1, 2, 3, 4, 5]
        
        games = None
        video_results = None
        analyses = None
        
        # 步骤0：爬取排行榜
        if 0 in steps:
            if not skip_scrape:
                self.step0_scrape_rankings()
            else:
                print("【步骤0】跳过爬取步骤，使用现有CSV文件\n")
        
        # 步骤1：提取排行榜
        if 1 in steps:
            games = self.step1_extract_rankings(max_games)
            if not games:
                print("错误：未能提取到游戏信息，工作流终止")
                return
        
        # 步骤2：搜索下载视频
        if 2 in steps:
            if games is None:
                # 尝试从中间产物加载
                games = self._load_latest_step1_result()
                if not games:
                    print("错误：没有可用的游戏列表，请先执行步骤1")
                    return
            video_results = self.step2_search_videos(games)
        
        # 步骤3：分析视频
        if 3 in steps:
            if video_results is None:
                # 尝试从中间产物加载
                video_results = self._load_latest_step2_result()
                if not video_results:
                    print("错误：没有可用的视频数据，请先执行步骤2")
                    return
            analyses = self.step3_analyze_videos(video_results)
            if not analyses:
                print("错误：未能生成任何分析结果，工作流终止")
                return
        
        # 步骤4：生成日报
        if 4 in steps:
            if analyses is None:
                # 尝试从中间产物加载
                analyses = self._load_latest_step3_result()
                if not analyses:
                    print("错误：没有可用的分析结果，请先执行步骤3")
                    return
            self.step4_generate_report(analyses)
        
        # 步骤5：发送日报
        if 5 in steps:
            if analyses is None:
                # 尝试从中间产物加载
                analyses = self._load_latest_step3_result()
                if not analyses:
                    print("错误：没有可用的分析结果，请先执行步骤3")
                    return
            self.step5_send_report(analyses)
        
        print("=" * 60)
        print("工作流执行完成")
        print("=" * 60)
    
    def _load_latest_step1_result(self) -> Optional[List[Dict]]:
        """加载最新的步骤1结果"""
        import glob
        import json
        files = glob.glob("data/step1_rankings_*.json")
        if files:
            latest = max(files)
            try:
                with open(latest, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return None
    
    def _load_latest_step2_result(self) -> Optional[List[Dict]]:
        """加载最新的步骤2结果"""
        import glob
        import json
        files = glob.glob("data/step2_videos_*.json")
        if files:
            latest = max(files)
            try:
                with open(latest, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return None
    
    def _load_latest_step3_result(self) -> Optional[List[Dict]]:
        """加载最新的步骤3结果"""
        import glob
        import json
        files = glob.glob("data/step3_analyses_*.json")
        if files:
            latest = max(files)
            try:
                with open(latest, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return None
        
        # 步骤2和3：搜索下载视频并分析
        print("【步骤2-3】搜索视频并分析游戏玩法...")
        analyses = []
        
        for idx, game in enumerate(games, 1):
            game_name = game.get('游戏名称', '未知游戏')
            game_type = game.get('游戏类型')  # 保存原始的游戏类型信息
            print(f"\n处理游戏 {idx}/{len(games)}: {game_name}")
            
            # 步骤1：检查数据库中是否已有完整的视频数据（搜索、下载、Google Drive）
            video_info = None
            video_path = None
            video_url = None
            aweme_id = None
            
            if self.video_searcher.use_database and self.video_searcher.db:
                db_game = self.video_searcher.db.get_game(game_name)
                videos = [db_game] if db_game else []
                if videos:
                    video_info = videos[0]
                    aweme_id = video_info.get("aweme_id")
                    
                    # 检查是否有已下载的视频
                    if video_info.get("downloaded") == 1 and video_info.get("local_path"):
                        video_path = video_info.get("local_path")
                        if os.path.exists(video_path):
                            print(f"  ✓ 从数据库找到已下载的视频：{video_path}")
                        else:
                            video_path = None
                    
                    # 检查是否有Google Drive URL
                    gdrive_url = video_info.get("gdrive_url")
                    if gdrive_url:
                        video_url = gdrive_url
                        print(f"  ✓ 从数据库找到Google Drive URL：{video_url[:50]}...")
            
            # 步骤2：如果数据库中没有视频，进行搜索和下载
            if not video_path or not video_url:
                if not video_path:
                    print(f"  数据库中未找到已下载的视频，开始搜索...")
                    video_path = self.video_searcher.search_and_download(
                        game_name=game_name,
                        game_type=game_type  # 使用保存的原始游戏类型
                    )
                
                # 重新从数据库获取最新信息
                if self.video_searcher.use_database and self.video_searcher.db:
                    game = self.video_searcher.db.get_game(game_name)
                    videos = [game] if game else []
                    if videos:
                        video_info = videos[0]
                        aweme_id = video_info.get("aweme_id")
                        
                        # 检查是否有Google Drive URL
                        if not video_url:
                            gdrive_url = video_info.get("gdrive_url")
                            if gdrive_url:
                                video_url = gdrive_url
                                print(f"  ✓ 从数据库获取Google Drive URL：{video_url[:50]}...")
                            elif video_path and os.path.exists(video_path):
                                # 如果还没有gdrive_url，尝试上传
                                print(f"  尝试上传本地视频到Google Drive...")
                                gdrive_url, gdrive_file_id = self.video_searcher._upload_to_gdrive(
                                    video_path, game_name, aweme_id
                                )
                                if gdrive_url:
                                    video_url = gdrive_url
                                    print(f"  ✓ 已上传并获取Google Drive URL：{video_url[:50]}...")
            
            if not video_url:
                print(f"错误：无法获取Google Drive URL，跳过分析")
                print(f"  请先运行：python upload_existing_videos_to_gdrive.py {game_name}")
                continue
            
            # 分析视频/游戏（必须使用Google Drive URL）
            if video_url:
                if not video_url.startswith("https://drive.google.com"):
                    print(f"  ✗ 错误：URL不是Google Drive链接，跳过分析")
                    continue
                
                analysis = self.video_analyzer.analyze_video(
                    video_path=None,  # 不需要本地文件
                    game_name=game_name,
                    game_info=game,
                    video_url=video_url
                )
            elif video_path:
                # 如果没有URL但有本地文件，使用本地文件（不推荐）
                print(f"  警告：使用本地文件进行分析（建议使用video_url）")
                analysis = self.video_analyzer.analyze_video(
                    video_path=video_path,
                    game_name=game_name,
                    game_info=game
                )
            else:
                # 如果没有视频，使用游戏信息进行基础分析
                analysis = self.video_analyzer.analyze_game_info(
                    game_name=game_name,
                    game_info=game
                )
            
            if analysis:
                # 步骤：提取并上传游戏截图到飞书（先检查数据库）
                screenshot_keys = None
                if self.video_searcher.use_database and self.video_searcher.db:
                    # 先检查数据库中是否已有截图
                    screenshot_keys = self.video_searcher.db.get_screenshot_key(game_name)
                    if screenshot_keys:
                        print(f"  ✓ 从数据库找到截图image_key（共{len(screenshot_keys)}张）")
                    elif video_path and os.path.exists(video_path):
                        # 如果数据库中没有，提取并上传
                        screenshot_keys = self._extract_and_upload_screenshot(video_path, game_name)
                        if screenshot_keys:
                            # 保存到数据库
                            self.video_searcher.db.update_screenshot_key(game_name, screenshot_keys)
                            print(f"  ✓ 已上传游戏截图到飞书并保存到数据库（共{len(screenshot_keys)}张）")
                
                if screenshot_keys:
                    analysis["screenshot_image_keys"] = screenshot_keys
                    # 为了兼容，也保留第一张作为screenshot_image_key
                    analysis["screenshot_image_key"] = screenshot_keys[0] if screenshot_keys else None
                
                analyses.append(analysis)
                print(f"✓ 完成分析：{game_name}")
            else:
                print(f"✗ 分析失败：{game_name}")
        
        if not analyses:
            print("\n错误：未能生成任何分析结果，工作流终止")
            return
        
        print(f"\n成功分析 {len(analyses)} 个游戏\n")
        
        # 步骤4：生成日报（JSON格式）
        print("【步骤4】生成日报...")
        report_json = self.report_generator.generate_daily_report(analyses)
        print("✓ 日报生成完成\n")
        
        # 可选：保存日报到文件（JSON格式）
        report_file = f"data/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            os.makedirs("data", exist_ok=True)
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_json)
            print(f"日报已保存到：{report_file}\n")
        except Exception as e:
            print(f"保存日报文件时出错：{str(e)}\n")
        
        # 步骤5：发送日报到飞书（JSON格式）
        print("【步骤5】发送日报到飞书...")
        feishu_report = self.report_generator.generate_feishu_format(analyses)
        success = self.feishu_sender.send_card(feishu_report)
        
        if success:
            print("✓ 日报发送成功")
        else:
            print("✗ 日报发送失败（请检查飞书Webhook配置）")
        
        print("\n" + "=" * 60)
        print("工作流执行完成")
        print("=" * 60)


def main():
    """主函数"""
    import argparse
    from pathlib import Path
    
    parser = argparse.ArgumentParser(
        description='小游戏热榜玩法解析日报工作流',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
步骤说明：
  0 - 爬取游戏排行榜
  1 - 提取游戏排行榜
  2 - 搜索并下载视频
  3 - 分析视频
  4 - 生成日报
  5 - 发送日报（飞书/企业微信/Google Sheets，通过--send-to参数选择）

示例：
  python main.py                    # 执行所有步骤（默认选择最新的CSV，发送到飞书）
  python main.py --platform dy      # 选择抖音小游戏榜单
  python main.py --platform wx     # 选择微信小游戏榜单
  python main.py --send-to wecom    # 发送到企业微信
  python main.py --send-to sheets   # 写入到Google Sheets
  python main.py --send-to all      # 发送到所有目标（飞书+企业微信+Google Sheets）
  python main.py --steps 0,1        # 只执行步骤0和1
  python main.py --steps 2,3        # 只执行步骤2和3
  python main.py --step 1           # 只执行步骤1
        """
    )
    parser.add_argument('max_games', type=int, nargs='?', default=None,
                        help='最大处理游戏数量')
    parser.add_argument('--skip-scrape', action='store_true',
                        help='跳过爬取步骤，直接使用现有CSV文件')
    parser.add_argument('--scrape-only', action='store_true',
                        help='只执行爬取步骤，不进行后续分析')
    parser.add_argument('--steps', type=str,
                        help='要执行的步骤，用逗号分隔，如：0,1,2,3,4,5')
    parser.add_argument('--step', type=int,
                        help='只执行单个步骤（0-5）')
    parser.add_argument('--rankings-csv', type=str, default="",
                        help='指定输入排行榜CSV文件路径（或目录）；用于切换到周榜/月榜CSV。优先级最高。')
    parser.add_argument('--use-latest-weekly', action='store_true',
                        help='自动选择 data/人气榜 下最新的“周榜CSV”（文件名包含 ~），不指定 --rankings-csv 时生效。')
    parser.add_argument('--force-refresh-analysis', action='store_true',
                        help='强制重新分析：忽略数据库中已有的玩法分析缓存（使用最新提示词重新生成并覆盖）')
    parser.add_argument('--skip-screenshots', action='store_true',
                        help='跳过截图提取/上传（当前提示词/报告不依赖截图时推荐开启）')
    parser.add_argument('--platform', type=str, choices=['dy', 'wx'], default=None,
                        help='选择平台：dy=抖音小游戏，wx=微信小游戏。默认不限制，选择最新的CSV文件')
    parser.add_argument('--send-to', type=str, choices=['feishu', 'wecom', 'sheets', 'all'], default='feishu',
                        help='选择发送目标：feishu=飞书，wecom=企业微信，sheets=Google Sheets，all=全部。默认为feishu')
    
    # 解析参数前，检查常见的拼写错误
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            # 检查是否是拼写错误的 --platform（常见错误：--platfrom）
            if arg.startswith('--platfor') and arg != '--platform':
                print(f"错误：参数 '{arg}' 不存在。")
                print(f"提示：您是否想使用 '--platform'？")
                print(f"      正确的用法：python main.py --platform dy")
                print(f"                  或：python main.py --platform wx")
                sys.exit(1)
    
    # 使用 parse_known_args 来更好地处理未知参数
    args, unknown = parser.parse_known_args()
    
    # 检查是否有未知参数
    if unknown:
        for arg in unknown:
            if arg.startswith('--'):
                # 检查是否是拼写错误
                if 'platfor' in arg.lower() and arg != '--platform':
                    print(f"错误：参数 '{arg}' 不存在。")
                    print(f"提示：您是否想使用 '--platform'？")
                    print(f"      正确的用法：python main.py --platform dy")
                    print(f"                  或：python main.py --platform wx")
                else:
                    print(f"错误：未知参数 '{arg}'")
                    print(f"      使用 python main.py --help 查看所有可用参数")
                sys.exit(1)
        # 如果有其他未知参数（非 -- 开头），可能是位置参数的问题
        if any(not arg.startswith('--') for arg in unknown):
            print(f"错误：无法识别的参数：{unknown}")
            print(f"      使用 python main.py --help 查看所有可用参数")
            sys.exit(1)
    
    rankings_csv_path = (args.rankings_csv or "").strip() or None
    if rankings_csv_path is None and args.use_latest_weekly:
        try:
            base_dir = Path("data") / "人气榜"
            if base_dir.exists() and base_dir.is_dir():
                weekly_files = list(base_dir.glob("*~*.csv"))
                if weekly_files:
                    weekly_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    rankings_csv_path = str(weekly_files[0])
        except Exception:
            rankings_csv_path = None

    workflow = GameAnalysisWorkflow(
        rankings_csv_path=rankings_csv_path,
        force_refresh_analysis=bool(args.force_refresh_analysis),
        skip_screenshots=bool(args.skip_screenshots),
        platform=args.platform,
        send_to=args.send_to,
    )
    
    # 如果只爬取
    if args.scrape_only:
        print("=" * 60)
        print("爬取游戏排行榜")
        print("=" * 60)
        print()
        workflow.step0_scrape_rankings()
        return
    
    # 解析步骤参数
    steps = None
    if args.step is not None:
        steps = [args.step]
    elif args.steps:
        try:
            steps = [int(s.strip()) for s in args.steps.split(',')]
        except ValueError:
            print("错误：步骤格式不正确，应为数字，用逗号分隔")
            sys.exit(1)
    
    # 运行工作流
    workflow.run(max_games=args.max_games, skip_scrape=args.skip_scrape, steps=steps)


if __name__ == "__main__":
    main()