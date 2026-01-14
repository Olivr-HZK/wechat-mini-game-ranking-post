"""
小游戏热榜玩法解析日报工作流
主程序入口
"""
import sys
import os
from datetime import datetime
from typing import Optional, List
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
    
    def run(self, max_games: int = None):
        """
        运行完整工作流
        
        Args:
            max_games: 最大处理游戏数量，默认使用配置文件中的值
        """
        print("=" * 60)
        print("小游戏热榜玩法解析日报工作流")
        print("=" * 60)
        print()
        
        # 步骤1：提取排行榜
        print("【步骤1】提取游戏排行榜...")
        max_games = max_games or config.MAX_GAMES_TO_PROCESS
        games = self.rank_extractor.get_top_games(top_n=max_games)
        
        if not games:
            print("错误：未能提取到游戏信息，工作流终止")
            return
        
        print(f"成功提取 {len(games)} 个游戏\n")
        
        # 步骤2和3：搜索下载视频并分析
        print("【步骤2-3】搜索视频并分析游戏玩法...")
        analyses = []
        
        for idx, game in enumerate(games, 1):
            game_name = game.get('游戏名称', '未知游戏')
            print(f"\n处理游戏 {idx}/{len(games)}: {game_name}")
            
            # 步骤1：检查数据库中是否已有完整的视频数据（搜索、下载、Google Drive）
            video_info = None
            video_path = None
            video_url = None
            aweme_id = None
            
            if self.video_searcher.use_database and self.video_searcher.db:
                videos = self.video_searcher.db.get_videos_by_game(game_name)
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
                        game_type=game.get('游戏类型')
                    )
                
                # 重新从数据库获取最新信息
                if self.video_searcher.use_database and self.video_searcher.db:
                    videos = self.video_searcher.db.get_videos_by_game(game_name)
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
    workflow = GameAnalysisWorkflow()
    
    # 可以在这里添加命令行参数解析
    if len(sys.argv) > 1:
        try:
            max_games = int(sys.argv[1])
            workflow.run(max_games=max_games)
        except ValueError:
            print("错误：参数必须是数字")
            sys.exit(1)
    else:
        workflow.run()


if __name__ == "__main__":
    main()