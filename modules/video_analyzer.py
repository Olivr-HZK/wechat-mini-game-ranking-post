"""
视频分析模块
使用OpenRouter API调用多模态模型分析视频内容
"""
import requests
import base64
import os
import json
import re
from typing import Dict, Optional, List
import config

# 尝试导入视频处理库
try:
    from PIL import Image
    import cv2
    VIDEO_PROCESSING_AVAILABLE = True
except ImportError:
    VIDEO_PROCESSING_AVAILABLE = False
    print("警告：未安装视频处理库（opencv-python, pillow），将使用文本模式分析")


class VideoAnalyzer:
    """视频分析器，使用OpenRouter API"""
    
    def __init__(self, api_key: str = None, model: str = None, use_database: bool = True):
        """
        初始化视频分析器
        
        Args:
            api_key: OpenRouter API密钥，默认从配置文件读取
            model: 使用的模型名称，默认从配置文件读取
            use_database: 是否使用数据库存储分析结果，默认True
        """
        self.api_key = api_key or config.OPENROUTER_API_KEY
        self.model = model or config.VIDEO_ANALYSIS_MODEL
        self.base_url = config.OPENROUTER_BASE_URL
        self.use_database = use_database
        
        # 初始化数据库
        if use_database:
            from modules.database import VideoDatabase
            self.db = VideoDatabase()
        else:
            self.db = None
    
    @staticmethod
    def _is_new_entry(rank_change: Optional[str]) -> bool:
        """是否为「新进榜」游戏。"""
        if not rank_change:
            return False
        s = (rank_change or "").strip()
        return "新进榜" in s or "新入榜" in s

    @staticmethod
    def _is_rank_up(rank_change: Optional[str]) -> bool:
        """是否为「排名提升/飙升」游戏（非新进榜但排名上升）。"""
        if not rank_change:
            return False
        s = (rank_change or "").strip()
        if VideoAnalyzer._is_new_entry(s):
            return False
        if "↑" in s:
            return True
        match = re.search(r"([+-]?\d+)", s)
        if match:
            try:
                return int(match.group(1)) > 0
            except ValueError:
                pass
        return False

    def _encode_video_to_base64(self, video_path: str) -> Optional[str]:
        """
        将视频文件编码为base64（已废弃，GPT-4o不支持直接传递视频）
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            base64编码的字符串，如果失败返回None
        """
        try:
            with open(video_path, 'rb') as video_file:
                video_data = video_file.read()
                # 对于大文件，可能需要分块处理，这里简化处理
                base64_data = base64.b64encode(video_data).decode('utf-8')
                return base64_data
        except Exception as e:
            print(f"编码视频文件时出错：{str(e)}")
            return None
    
    def _extract_video_frames(self, video_path: str, max_frames: int = 5) -> List[str]:
        """
        从视频中提取关键帧作为图像
        
        Args:
            video_path: 视频文件路径
            max_frames: 最大提取帧数
        
        Returns:
            base64编码的图像列表
        """
        if not VIDEO_PROCESSING_AVAILABLE:
            return []
        
        try:
            import cv2
            from PIL import Image
            import io
            
            # 打开视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"    无法打开视频文件：{video_path}")
                return []
            
            # 获取视频信息
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            print(f"    视频信息：总帧数={total_frames}, FPS={fps:.2f}, 时长={duration:.2f}秒")
            
            # 计算提取帧的间隔（均匀分布）
            if total_frames <= max_frames:
                frame_indices = list(range(total_frames))
            else:
                step = total_frames // max_frames
                frame_indices = [i * step for i in range(max_frames)]
                # 确保包含最后一帧
                if frame_indices[-1] != total_frames - 1:
                    frame_indices[-1] = total_frames - 1
            
            frames_base64 = []
            
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                
                if not ret:
                    continue
                
                # 转换BGR到RGB（OpenCV使用BGR，PIL使用RGB）
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 转换为PIL Image
                pil_image = Image.fromarray(frame_rgb)
                
                # 调整大小（如果太大，限制最大尺寸）
                max_size = 1024
                if pil_image.width > max_size or pil_image.height > max_size:
                    pil_image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # 转换为JPEG格式的base64
                buffer = io.BytesIO()
                pil_image.save(buffer, format='JPEG', quality=85)
                frame_bytes = buffer.getvalue()
                frame_base64 = base64.b64encode(frame_bytes).decode('utf-8')
                
                frames_base64.append(frame_base64)
            
            cap.release()
            return frames_base64
            
        except Exception as e:
            print(f"    提取视频帧时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def analyze_video(
        self,
        video_path: str = None,
        game_name: str = None,
        game_info: Dict = None,
        video_url: str = None,
        force_refresh: bool = False,
    ) -> Optional[Dict]:
        """
        分析视频内容，提取游戏玩法信息
        
        Args:
            video_path: 视频文件路径（可选，如果提供video_url则不需要）
            game_name: 游戏名称
            game_info: 游戏的其他信息（可选）
            video_url: 视频URL（优先使用，如果不提供则尝试从数据库获取）
            force_refresh: 是否强制重新分析（忽略数据库中的玩法分析缓存）
        
        Returns:
            分析结果字典，包含玩法解析等信息
        """
        # 首先检查数据库是否已有分析结果
        if (not force_refresh) and self.use_database and self.db and game_name:
            existing_analysis = self.db.get_gameplay_analysis(game_name)
            if existing_analysis and existing_analysis.get("gameplay_analysis"):
                print(f"✓ 找到 {game_name} 的已有分析结果（使用数据库缓存）")
                print(f"  分析模型：{existing_analysis.get('analysis_model', 'unknown')}")
                print(f"  分析时间：{existing_analysis.get('analyzed_at', 'unknown')}")
                
                # 获取原始分析文本
                analysis_text = existing_analysis.get("gameplay_analysis")
                
                # 尝试解析JSON格式的分析数据
                analysis_data = self._parse_analysis_json(analysis_text)
                
                if analysis_data:
                    print(f"  ✓ 成功解析缓存中的JSON格式数据")
                else:
                    print(f"  ⚠ 缓存数据不是JSON格式，将使用文本格式")
                
                return {
                    "game_name": game_name,
                    "analysis": analysis_text,  # 原始文本
                    "analysis_data": analysis_data,  # 解析后的结构化数据
                    "model_used": existing_analysis.get("analysis_model", "unknown"),
                    "status": "cached"
                }
        
        if not self.api_key:
            print("警告：未配置OpenRouter API密钥，使用Mock分析结果")
            return self._mock_analyze(video_path, game_name, game_info)
        
        print(f"正在使用 {self.model} 分析视频：{game_name}")
        
        # 优先从数据库获取Google Drive URL，如果没有则尝试其他URL
        if not video_url and self.use_database and self.db and game_name:
            # 从数据库获取视频信息
            game = self.db.get_game(game_name)
            videos = [game] if game else []
            if videos:
                video_info = videos[0]
                # 优先级：Google Drive URL > 原视频URL > 普通video_url
                video_url = video_info.get("gdrive_url") or video_info.get("original_video_url") or video_info.get("video_url")
                if video_url:
                    if video_info.get("gdrive_url"):
                        url_type = "Google Drive URL"
                    elif video_info.get("original_video_url"):
                        url_type = "原视频URL（最高画质）"
                    else:
                        url_type = "视频URL"
                    print(f"  从数据库获取{url_type}：{video_url[:50]}...")
        
        # 如果既没有video_url也没有video_path，使用Mock
        if not video_url and (not video_path or not os.path.exists(video_path)):
            print(f"警告：未提供视频URL或视频文件不存在，使用Mock分析结果")
            return self._mock_analyze(video_path, game_name, game_info)
        
        try:
            # 优先使用video_url
            if video_url:
                print(f"  使用视频URL进行分析：{video_url[:50]}...")
                use_url = True
            else:
                # 如果没有URL，使用本地文件（但用户要求使用URL，所以这里应该报错）
                print(f"  警告：未提供视频URL，尝试使用本地文件（不推荐）")
                use_url = False
            
            # 读取GAME_TYPE.json作为基线游戏参考
            game_type_json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "GAME_TYPE.json")
            baseline_reference = ""
            try:
                if os.path.exists(game_type_json_path):
                    with open(game_type_json_path, 'r', encoding='utf-8') as f:
                        game_types = json.load(f)
                        # 提取所有基线游戏分类信息
                        baseline_list = []
                        for category in game_types.get("休闲游戏分类", []):
                            first_level = category.get("一级分类", "")
                            for second_level in category.get("二级分类", []):
                                second_name = second_level.get("名称", "")
                                for third_level in second_level.get("三级细分", []):
                                    third_name = third_level.get("名称", "")
                                    desc = third_level.get("描述", "")
                                    example = third_level.get("代表作品", "")
                                    baseline_list.append(f"- {first_level} > {second_name} > {third_name}：{desc}（代表作品：{example}）")
                        if baseline_list:
                            baseline_reference = "\n".join(baseline_list[:50])  # 限制长度
            except Exception as e:
                print(f"  警告：读取GAME_TYPE.json失败：{e}")
            
            # 根据排名变化类型选择分析重点
            rank_change = (game_info or {}).get("排名变化") or ""
            is_new_entry = self._is_new_entry(rank_change)
            is_rank_up = self._is_rank_up(rank_change)
            
            if is_new_entry:
                focus_instruction = """【本游戏为新进榜游戏】请正常分析其核心玩法、基线游戏与创新点。在输出的 JSON 中可增加顶层字段 "is_new_entry": true 表示新游戏。"""
            elif is_rank_up:
                focus_instruction = """【本游戏为排名提升/飙升游戏】请重点观察视频中是否存在新玩法或明显创新：
- 若存在新玩法/新内容：正常输出 core_gameplay、baseline_game、innovation_points，并可在 innovation_points 中强调本次新玩法。
- 若仍是老玩法、无显著创新：core_gameplay 与 baseline_game 照常写；在 innovation_points 中只保留一条："未发现新玩法，建议手动观察该游戏动态"。并增加顶层字段 "suggest_manual_watch": true。"""
            else:
                focus_instruction = """请正常分析核心玩法、基线游戏与创新点。"""
            
            # 构建API请求
            # 要求返回结构化且可解析的JSON；只输出三个部分：核心玩法、基线游戏、基于基线游戏的创新点
            prompt = f"""你是一名“小游戏玩法拆解 & 品类微创新”分析师。

{focus_instruction}

本次只输出三个部分（以及上述情形下的可选字段）：
1) 核心玩法（用通俗易懂的话说明游戏怎么玩）
2) 基线游戏（参考下面的基线游戏分类，找出最相似的基线游戏类型）
3) 基于基线游戏的创新点（说明相比基线游戏做了哪些改进或创新）

不要做“吸引力分析/为什么好玩/目标用户/留存点”等内容，也不要输出相关字段。

游戏名称：{game_name}
游戏类型：{game_info.get('游戏类型', '未知') if game_info else '未知'}
排名变化：{rank_change or '--'}

基线游戏分类参考（请从中选择最相似的基线游戏类型）：
{baseline_reference if baseline_reference else "请根据常见游戏类型判断（如：三消、合成、跑酷、射击、解谜等）"}

请仔细观看视频内容，然后以JSON格式返回分析结果（严格JSON，可直接解析；至少包含下面三个顶层字段）：
{{
  "core_gameplay": "用通俗易懂的1-2段话说明核心玩法，包括：玩家要做什么、怎么操作、主要目标是什么。要求简短（80-150字），避免专业术语，用大白话解释。",
  "baseline_game": "基线游戏类型，格式：一级分类 > 二级分类 > 三级细分（例如：益智解谜 > 消除类 > 交换三消），如果找不到完全匹配的，就写最接近的分类，不确定就写“未知”。",
  "innovation_points": [
    "列出 3-5 条基于基线游戏的创新点，每条用一句话说明（20-40字），要具体说明做了什么改进，不要空泛。若为排名提升且无新玩法，则只保留一条：未发现新玩法，建议手动观察该游戏动态。"
  ]
}}

重要要求：
1. **三个部分输出**：至少输出 `core_gameplay`、`baseline_game` 和 `innovation_points`，不要出现其他无关顶层字段。
2. **通俗易懂**：所有描述都要用简单直白的话，避免专业术语，让普通人也能看懂。
3. **简短精炼**：
   - **core_gameplay**：80-150字，用1-2段话说明怎么玩
   - **baseline_game**：直接写分类路径，如"益智解谜 > 消除类 > 交换三消"
   - **innovation_points**：3-5条（或按上述情形为1条），每条20-40字，要具体说明创新点

4. **必须仔细观察视频中的实际游戏画面和操作**

5. **直接返回JSON格式，不要有任何前缀说明文字（如"好的"、"以下是"等）**

6. **确保JSON格式正确，可以被解析**

7. **所有描述都要基于视频中的实际内容，不要编造信息**

示例格式：
{{
  "core_gameplay": "玩家通过点击屏幕发射小鸟攻击旋转的目标。需要找准时机在目标旋转的间隙中攻击，避开TNT等危险障碍物，收集青虫和宝石等奖励。通过不断攻击将目标的生命值清空即可通关。操作简单，只需要点击屏幕即可。",
  "baseline_game": "街机动作 > 技巧/平台 > 精确控制",
  "innovation_points": [
    "将传统射击改为角色本身作为发射物",
    "目标从单一变为可被逐步破坏的多层结构",
    "增加了需要躲避的危险障碍物和可收集的奖励物",
    "引入了生命值进度条，从插满变为摧毁目标"
  ]
}}"""
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/your-repo",  # 可选
                "X-Title": "Game Video Analyzer"  # 可选
            }
            
            # 构建content数组 - 直接使用视频URL
            video_file_size = 0  # 初始化变量
            if use_url:
                # 使用视频URL（HTTP/HTTPS URL）
                content_items = [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": video_url
                        }
                    }
                ]
                print(f"  已添加视频URL到请求：{video_url[:80]}...")
            else:
                # 如果没有URL，使用本地文件（不推荐，但保留兼容性）
                if not os.path.exists(video_path):
                    print("  视频文件不存在，使用Mock分析结果")
                    return self._mock_analyze(video_path, game_name, game_info)
                
                video_file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
                print(f"  视频文件大小：{video_file_size:.2f} MB")
                print(f"  警告：使用本地文件，建议使用video_url")
                
                # 读取视频文件并编码为base64（兼容旧方式）
                print(f"  正在读取并编码视频文件...")
                video_base64 = self._encode_video_to_base64(video_path)
                
                if not video_base64:
                    print("  视频编码失败，使用Mock分析结果")
                    return self._mock_analyze(video_path, game_name, game_info)
                
                print(f"  视频编码完成，base64长度：{len(video_base64)} 字符")
                
                content_items = [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": f"data:video/mp4;base64,{video_base64}"
                        }
                    }
                ]
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": content_items
                    }
                ],
                "max_tokens": 12000  # 增加token限制，确保详细分析结果完整返回
            }
            
            # 发送API请求（增加简单重试，缓解偶发的 SSL/网络错误）
            print(f"  发送API请求到 {self.base_url}/chat/completions...")
            print(f"  注意：视频分析可能需要较长时间，请耐心等待...")
            
            timeout = 180 if use_url else (180 if video_file_size > 10 else 120)

            response = None
            last_err = None
            for attempt in range(3):
                try:
                    response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout,
                    )
                    break
                except requests.exceptions.RequestException as e:
                    last_err = e
                    print(f"  ⚠ 与 OpenRouter 通信失败（第 {attempt + 1}/3 次）：{e}")
                    if attempt < 2:
                        print("    等待 5 秒后重试...")
                        import time as _time
                        _time.sleep(5)
                    else:
                        print("    多次重试仍失败，将退回到 Mock 分析结果。")
            if response is None:
                # 所有重试都失败，走统一异常处理
                raise last_err if last_err else RuntimeError("与 OpenRouter 通信失败（未知错误）")
            
            if response.status_code == 200:
                result = response.json()
                
                # 检查响应格式
                if 'choices' in result and len(result['choices']) > 0:
                    choice = result['choices'][0]
                    analysis_text = choice['message']['content']
                    finish_reason = choice.get('finish_reason', 'unknown')
                    
                    # 检查是否因为token限制被截断
                    if finish_reason == 'length':
                        print(f"  ⚠ 警告：响应因token限制被截断，可能需要增加max_tokens")
                    elif finish_reason == 'stop':
                        print(f"  ✓ 分析成功（完整返回）")
                    else:
                        print(f"  ✓ 分析成功（完成原因：{finish_reason}）")
                    
                    # 清理分析文本：移除开头废话
                    analysis_text = self._clean_analysis_text(analysis_text)
                    
                    # 尝试解析JSON格式
                    analysis_data = self._parse_analysis_json(analysis_text)
                    
                    if analysis_data:
                        print(f"  ✓ 成功解析JSON格式的分析结果")
                    else:
                        print(f"  ⚠ 未能解析JSON格式，将使用文本格式")
                    
                    # 显示返回的文本长度
                    text_length = len(analysis_text)
                    print(f"  返回文本长度：{text_length} 字符")
                    
                    # 保存分析结果到数据库（保存原始文本）
                    if self.use_database and self.db:
                        success = self.db.save_gameplay_analysis(game_name, analysis_text, self.model)
                        if success:
                            print(f"  ✓ 分析结果已保存到数据库")
                    
                    # 排名变化类型，供周报与 weekly 简单表使用
                    change_type = ""
                    if is_new_entry:
                        change_type = "新进榜"
                    elif is_rank_up:
                        change_type = "飙升"
                    
                    return {
                        "game_name": game_name,
                        "analysis": analysis_text,  # 原始文本（已清理）
                        "analysis_data": analysis_data,  # 解析后的结构化数据
                        "model_used": self.model,
                        "status": "success",
                        "finish_reason": finish_reason,
                        "text_length": text_length,
                        "change_type": change_type,  # 新进榜 / 飙升 / 空
                        "is_new_entry": is_new_entry,
                    }
                else:
                    print(f"  API响应格式异常：{result}")
                    print("使用Mock分析结果")
                    return self._mock_analyze(video_path, game_name, game_info)
            else:
                error_text = response.text[:500] if response.text else "无错误信息"
                print(f"  API请求失败：HTTP {response.status_code}")
                print(f"  错误信息：{error_text}")
                
                # 如果是 400 或 404（例如 Qwen 在 OpenRouter 上暂不支持 video_url），
                # 说明当前模型不接受我们传的视频格式，退回到“纯文本模式”继续分析。
                if response.status_code in (400, 404):
                    print("  尝试使用纯文本模式（不包含视频，只基于游戏名称和类型进行分析）...")
                    text_only_payload = {
                        "model": self.model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": prompt + "\n\n注意：由于视频格式限制，请基于游戏名称和类型进行通用分析。"
                                    }
                                ]
                            }
                        ],
                        "max_tokens": 8000  # 增加token限制
                    }
                    # 打印发给 Qwen 的请求体（API 输入）
                    print("  [Qwen API 输入] text_only_payload:")
                    print(json.dumps(text_only_payload, ensure_ascii=False, indent=2))
                    
                    text_response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=text_only_payload,
                        timeout=60
                    )
                    
                    if text_response.status_code == 200:
                        text_result = text_response.json()
                        # 打印 Qwen 返回的原始 JSON（API 输出）
                        print("  [Qwen API 输出] text_result:")
                        print(json.dumps(text_result, ensure_ascii=False, indent=2))
                        if 'choices' in text_result and len(text_result['choices']) > 0:
                            analysis_text = text_result['choices'][0]['message']['content']
                            print(f"  ✓ 文本模式分析成功")
                            return {
                                "game_name": game_name,
                                "analysis": analysis_text,
                                "model_used": self.model,
                                "status": "text_only"  # 标记为仅文本分析
                            }
                
                print("使用Mock分析结果")
                return self._mock_analyze(video_path, game_name, game_info)
                
        except Exception as e:
            print(f"分析视频时出错：{str(e)}")
            print("使用Mock分析结果")
            return self._mock_analyze(video_path, game_name, game_info)
    
    def analyze_game_info(self, game_name: str, game_info: Dict = None) -> Dict:
        """
        基于游戏信息进行分析（当没有视频时使用）
        
        Args:
            game_name: 游戏名称
            game_info: 游戏信息
        
        Returns:
            分析结果
        """
        return self._mock_analyze("", game_name, game_info)
    
    def _upload_to_gdrive_and_get_url(self, video_path: str, game_name: str) -> Optional[str]:
        """
        上传视频到Google Drive并获取公开访问链接
        
        Args:
            video_path: 本地视频文件路径
            game_name: 游戏名称
        
        Returns:
            公开访问的URL，如果失败返回None
        """
        try:
            from modules.gdrive_uploader import GoogleDriveUploader
            
            uploader = GoogleDriveUploader()
            result = uploader.upload_video(video_path, folder_name="Game Videos")
            
            if result and result.get('public_url'):
                public_url = result['public_url']
                print(f"  ✓ 视频已上传到Google Drive")
                print(f"  公开访问链接：{public_url[:60]}...")
                
                # 保存到数据库（如果使用数据库）
                if self.use_database and self.db:
                    game = self.db.get_game(game_name)
                    videos = [game] if game else []
                    if videos:
                        video_info = videos[0]
                        video_info['gdrive_url'] = public_url
                        video_info['gdrive_file_id'] = result.get('file_id')
                        # 更新数据库（需要添加gdrive_url字段，这里先不更新数据库结构）
                        print(f"  ✓ Google Drive链接已记录")
                
                return public_url
            else:
                print(f"  ✗ 上传到Google Drive失败")
                return None
                
        except ImportError:
            print(f"  ⚠ Google Drive上传功能不可用（未安装相关库）")
            print(f"  请运行: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
            return None
        except Exception as e:
            print(f"  上传到Google Drive时出错：{str(e)}")
            return None
    
    def _clean_analysis_text(self, text: str) -> str:
        """
        清理分析文本，移除开头的废话
        
        Args:
            text: 原始分析文本
        
        Returns:
            清理后的文本
        """
        if not text:
            return ""
        
        # 移除常见的开头废话
        patterns = [
            r'^好的[，,]\s*',
            r'^以下是[，,]\s*',
            r'^这是[，,]\s*',
            r'^好的[，,]\s*这是[，,]\s*',
            r'^好的[，,]\s*以下是[，,]\s*',
            r'^这是对游戏[视频]*[《<]?.*?[》>]?的分析[：:]\s*',
            r'^好的[，,]\s*这是对游戏[视频]*[《<]?.*?[》>]?的分析[：:]\s*',
        ]
        
        cleaned = text.strip()
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
        
        return cleaned.strip()
    
    def _parse_analysis_json(self, text: str) -> Optional[Dict]:
        """
        尝试从文本中解析JSON格式的分析结果
        
        Args:
            text: 分析文本
        
        Returns:
            解析后的JSON字典，如果解析失败返回None
        """
        if not text:
            return None
        
        # 尝试多种方式提取和修复JSON
        json_str = None
        
        # 方法1：尝试提取代码块中的JSON
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        
        # 方法2：如果没有代码块，尝试找到第一个{和匹配的最后一个}
        if not json_str:
            brace_start = text.find('{')
            if brace_start != -1:
                # 从第一个{开始，找到匹配的最后一个}
                brace_count = 0
                brace_end = -1
                for i in range(brace_start, len(text)):
                    if text[i] == '{':
                        brace_count += 1
                    elif text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            brace_end = i
                            break
                
                if brace_end != -1:
                    json_str = text[brace_start:brace_end + 1]
                else:
                    json_str = text[brace_start:]
        
        if not json_str:
            return None
        
        # 尝试修复常见的JSON格式问题
        def fix_json_string(s: str) -> str:
            """修复JSON字符串中的常见问题"""
            # 1. 将单引号替换为双引号（但要小心处理字符串内的引号）
            # 先处理键名和值的单引号
            # 使用正则表达式匹配键名和值，但要避免匹配字符串内的引号
            fixed = s
            
            # 2. 修复未转义的控制字符
            fixed = fixed.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            
            # 3. 尝试将单引号替换为双引号（简单方法：先处理键名）
            # 匹配键名：'key': 或 "key": 或 key:
            # 这里我们使用更安全的方法：只替换明显的键名单引号
            fixed = re.sub(r"'(\w+)'\s*:", r'"\1":', fixed)
            
            # 4. 处理值中的单引号（但要小心，因为值可能包含单引号）
            # 这里我们尝试一个更保守的方法：只在明显是JSON结构的地方替换
            
            return fixed
        
        # 尝试解析JSON（多次尝试，逐步修复）
        attempts = [
            # 尝试1：直接解析
            lambda s: json.loads(s),
            # 尝试2：修复单引号键名后解析
            lambda s: json.loads(re.sub(r"'(\w+)'\s*:", r'"\1":', s)),
            # 尝试3：使用ast.literal_eval（如果JSON格式接近Python字典）
            lambda s: self._try_parse_with_ast(s),
            # 尝试4：手动修复更多问题
            lambda s: json.loads(self._manual_fix_json(s)),
        ]
        
        for i, attempt in enumerate(attempts):
            try:
                data = attempt(json_str)
                if data and isinstance(data, dict):
                    if i > 0:
                        print(f"  ✓ 使用修复方法{i+1}成功解析JSON")
                    return data
            except Exception:
                continue
        
        # 如果所有方法都失败，输出更详细的错误信息
        try:
            json.loads(json_str)  # 这会抛出详细的错误信息
        except json.JSONDecodeError as e:
            error_pos = e.pos if hasattr(e, 'pos') else -1
            if error_pos > 0 and error_pos < len(json_str):
                # 显示错误位置附近的内容
                start = max(0, error_pos - 50)
                end = min(len(json_str), error_pos + 50)
                context = json_str[start:end]
                print(f"  ⚠ JSON解析错误位置（字符{error_pos}附近）：...{context}...")
            print(f"  ⚠ 无法解析JSON格式，将使用文本格式：{str(e)[:200]}")
        
        return None
    
    def _try_parse_with_ast(self, text: str) -> Optional[Dict]:
        """尝试使用ast.literal_eval解析（适用于接近Python字典格式的文本）"""
        try:
            import ast
            # 将单引号替换为双引号（简单替换，可能不够准确）
            fixed = text.replace("'", '"')
            # 尝试解析
            result = ast.literal_eval(fixed)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        return None
    
    def _manual_fix_json(self, text: str) -> str:
        """手动修复JSON字符串中的常见问题"""
        fixed = text
        
        # 1. 修复键名的单引号
        fixed = re.sub(r"'(\w+)'\s*:", r'"\1":', fixed)
        
        # 2. 修复值中的单引号（但要小心，只在明显是字符串值的地方）
        # 匹配模式：": 'value' 或 , 'value'
        def fix_string_value(match):
            prefix = match.group(1)
            value = match.group(2)
            # 如果值中包含特殊字符，需要转义
            value_escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'{prefix}"{value_escaped}"'
        
        # 匹配 : 'value' 或 , 'value' 的模式
        fixed = re.sub(r'(:\s*|\,\s*)\'([^\']*)\'', fix_string_value, fixed)
        
        # 3. 修复未转义的控制字符
        fixed = fixed.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        
        return fixed
    
    def _mock_analyze(self, video_path: str, game_name: str, game_info: Dict = None) -> Dict:
        """
        Mock分析结果（当API不可用时使用）
        
        Args:
            video_path: 视频文件路径
            game_name: 游戏名称
            game_info: 游戏信息
        
        Returns:
            Mock分析结果（新格式：三个部分）
        """
        game_type = game_info.get('游戏类型', '未知') if game_info else '未知'
        
        # 新格式：只包含三个部分
        mock_analysis_json = {
            "core_gameplay": f"这是一个{game_type}类游戏。玩家通过简单的点击或滑动操作完成各种挑战任务。游戏规则清晰，目标明确，操作流畅。适合各个年龄段的玩家，可以轻松上手。",
            "baseline_game": "未知",
            "innovation_points": [
                "游戏操作简单易上手",
                "关卡设计丰富多样",
                "适合碎片化时间游玩"
            ]
        }
        
        mock_analysis_text = json.dumps(mock_analysis_json, ensure_ascii=False, indent=2)
        
        return {
            "game_name": game_name,
            "analysis": mock_analysis_text,
            "analysis_data": mock_analysis_json,
            "model_used": "mock",
            "status": "mock"
        }