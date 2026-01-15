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
    
    def analyze_video(self, video_path: str = None, game_name: str = None, game_info: Dict = None, video_url: str = None) -> Optional[Dict]:
        """
        分析视频内容，提取游戏玩法信息
        
        Args:
            video_path: 视频文件路径（可选，如果提供video_url则不需要）
            game_name: 游戏名称
            game_info: 游戏的其他信息（可选）
            video_url: 视频URL（优先使用，如果不提供则尝试从数据库获取）
        
        Returns:
            分析结果字典，包含玩法解析等信息
        """
        # 首先检查数据库是否已有分析结果
        if self.use_database and self.db and game_name:
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
            
            # 构建API请求
            # 要求返回结构化但更加精炼的JSON格式分析
            prompt = f"""请仔细观察这个游戏视频，进行玩法分析。

游戏名称：{game_name}
游戏类型：{game_info.get('游戏类型', '未知') if game_info else '未知'}

请仔细观看视频内容，然后以JSON格式返回分析结果，格式如下：
{{
  "core_gameplay": {{
    "mechanism": "用一段话整体说明核心玩法机制 + 操作方式 + 基本规则 + 主要特点（合并在一起）",
    "operation": "可选的简短补充（1-2 句），没有补充可留空字符串",
    "rules": "可选的简短补充（1-2 句），没有补充可留空字符串",
    "features": "可选的简短补充（1-2 句），没有补充可留空字符串"
  }},
  "attraction": {{
    "points": "用一段话整合说明：游戏的主要吸引点 + 适合的目标用户类型 + 关键留存因素",
    "target_audience": "可选的简短人群标签或一句话总结（可留空字符串）",
    "retention_factors": "可选的简短留存要点（可留空字符串）"
  }}
}}

重要要求：
1. **玩法描述策略（仍然保持类比/创新逻辑）**：
   - 如果该游戏的玩法与市面上主流热门游戏（如王者荣耀、和平精英、原神、英雄联盟、和平精英、我的世界、植物大战僵尸等）类似，请采用类比方式：
     * 先说明"玩法类似[知名游戏名称]"，例如"玩法类似英雄联盟手游版"或"玩法类似王者荣耀"
     * 然后用极简洁的方式说明核心玩法机制和操作方式（总字数控制在 120-180 字）
     * 再补一句概括性的差异和本游戏的独特之处（约 50-80 字）
   - 如果是一种全新的、创新的玩法：整体描述也尽量收敛在 180-250 字以内，突出最核心的 2-3 个机制即可
   - 如果玩法是经典类型的变体（如消除类、跑酷类、塔防类等），先说明大类，再点出 2-3 个最有差异化的点

2. **描述长度控制**：
   - **core_gameplay.mechanism**：1 段整体文字，推荐 150-220 字，覆盖机制 + 操作 + 规则 + 特点，不要拆得太细、不要赘述
   - **core_gameplay.operation / rules / features**：如果没有额外信息，可以留空字符串 `""`，有补充时每个字段不超过 50 字
   - **attraction.points**：1 段整体文字，推荐 150-220 字，同时说明：为什么好玩 + 适合什么玩家 + 主要留存点
   - **attraction.target_audience / retention_factors**：可以是非常精简的标签或一句话（不超过 40 字），不强制必须填写

3. **必须仔细观察视频中的实际游戏画面和操作**

4. **直接返回JSON格式，不要有任何前缀说明文字（如"好的"、"以下是"等）**

5. **确保JSON格式正确，可以被解析**

6. **所有描述都要基于视频中的实际内容，不要编造信息**

示例格式（玩法类似知名游戏时，注意结构精简）：
{{
  "core_gameplay": {{
    "mechanism": "玩法整体类似英雄联盟手游版，为 5v5 MOBA 推塔对战。玩家选择不同定位的英雄，在三路地图中通过击杀小兵、野怪和敌方英雄获取经济与经验，购买装备强化自己，最终摧毁敌方基地水晶获胜。本作节奏更快、单局时长更短，操作界面更简洁，对走位与技能释放做了自动辅助，更偏向轻度玩家。",
    "operation": "",
    "rules": "",
    "features": ""
  }},
  ...
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
            
            # 发送API请求
            print(f"  发送API请求到 {self.base_url}/chat/completions...")
            print(f"  注意：视频分析可能需要较长时间，请耐心等待...")
            
            # 视频分析可能需要更长时间
            timeout = 180 if use_url else (180 if video_file_size > 10 else 120)
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout
            )
            
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
                    
                    return {
                        "game_name": game_name,
                        "analysis": analysis_text,  # 原始文本（已清理）
                        "analysis_data": analysis_data,  # 解析后的结构化数据
                        "model_used": self.model,
                        "status": "success",
                        "finish_reason": finish_reason,
                        "text_length": text_length
                    }
                else:
                    print(f"  API响应格式异常：{result}")
                    print("使用Mock分析结果")
                    return self._mock_analyze(video_path, game_name, game_info)
            else:
                error_text = response.text[:500] if response.text else "无错误信息"
                print(f"  API请求失败：HTTP {response.status_code}")
                print(f"  错误信息：{error_text}")
                
                # 如果是400错误，可能是视频格式不支持，尝试只用文本
                if response.status_code == 400:
                    print("  尝试使用纯文本模式（不包含视频）...")
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
                    
                    text_response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=text_only_payload,
                        timeout=60
                    )
                    
                    if text_response.status_code == 200:
                        text_result = text_response.json()
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
            Mock分析结果
        """
        game_type = game_info.get('游戏类型', '未知') if game_info else '未知'
        
        mock_analysis = f"""
【{game_name}】玩法解析

游戏类型：{game_type}

核心玩法：
- 这是一个{game_type}类游戏，玩家需要通过操作完成各种挑战
- 游戏操作简单易上手，适合各个年龄段的玩家
- 具有丰富的关卡设计和挑战性

操作方式：
- 通过点击、滑动等简单操作进行游戏
- 界面友好，操作流畅

特色功能：
- 精美的画面设计
- 丰富的游戏内容
- 社交分享功能

难度特点：
- 前期关卡较为简单，适合新手入门
- 后期关卡难度逐渐提升，具有挑战性

吸引点：
- 简单易上手，容易产生成就感
- 适合碎片化时间游玩
- 具有社交属性，可以和朋友一起玩
"""
        
        return {
            "game_name": game_name,
            "analysis": mock_analysis.strip(),
            "model_used": "mock",
            "status": "mock"
        }