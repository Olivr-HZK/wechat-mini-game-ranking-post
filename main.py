"""
小游戏热榜玩法解析日报工作流
主程序入口
"""
import sys
import os
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
    
    def __init__(self):
        """初始化工作流"""
        self.rank_extractor = RankExtractor()
        self.video_searcher = VideoSearcher()
        self.video_analyzer = VideoAnalyzer()
        self.report_generator = ReportGenerator()
        self.feishu_sender = FeishuSender()
    
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
            csv_path = config.RANKINGS_CSV_PATH
            
            if not os.path.exists(csv_path):
                print(f"⚠ CSV文件不存在：{csv_path}")
                print(f"  请手动创建CSV文件，格式参考：data/game_rankings_template.csv")
                return False
            
            # 验证CSV文件格式并统计数量
            from modules.rank_extractor import RankExtractor
            extractor = RankExtractor()
            games = extractor.get_top_games(top_n=1)  # 只读取一条验证格式
            
            if not games:
                print(f"⚠ CSV文件格式不正确或为空：{csv_path}")
                print(f"  请检查CSV文件格式，参考：data/game_rankings_template.csv")
                return False
            
            # 统计总游戏数量（读取所有数据）
            all_games = extractor.get_top_games(top_n=None)
            game_count = len(all_games) if all_games else 0
            
            print(f"✓ CSV文件检查通过：{csv_path}")
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
                        "local_path": video_info.get("local_path")
                    })
                
                video_results.append({
                    "game_name": game_name,
                    "game_info": game_info,  # 保存完整的游戏信息（包括开发公司、排名变化等）
                    "video_info": video_info,
                    "video_path": video_path,
                    "video_url": video_url,
                    "gdrive_url": video_url,  # 明确保存gdrive_url
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
            video_info = video_result.get("video_info", {})
            
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
                game_info=video_info,
                video_url=video_url
            )
            
            if analysis:
                # 提取并上传截图
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
                game_info = video_result.get("game_info", {})
                analysis["game_rank"] = game_info.get("排名", "")
                analysis["game_company"] = game_info.get("开发公司", "")
                analysis["rank_change"] = game_info.get("排名变化", "--")
                # 额外补充：监控日期/平台/来源/榜单（来自排行榜CSV）
                analysis["monitor_date"] = game_info.get("监控日期", "")
                analysis["platform"] = game_info.get("平台", "")
                analysis["source"] = game_info.get("来源", "")
                analysis["board_name"] = game_info.get("榜单", "")
                analysis["gdrive_url"] = video_result.get("gdrive_url", video_url)
                
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
        步骤5：发送日报到飞书
        
        Args:
            analyses: 分析结果列表
        
        Returns:
            是否发送成功
        """
        print("【步骤5】发送日报到飞书...")
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
        
        success = self.feishu_sender.send_card(feishu_report)
        
        if success:
            print("✓ 日报发送成功\n")
        else:
            print("✗ 日报发送失败（请检查飞书Webhook配置）\n")
        
        return success
    
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
  5 - 发送日报到飞书

示例：
  python main.py                    # 执行所有步骤
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
    
    args = parser.parse_args()
    
    workflow = GameAnalysisWorkflow()
    
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