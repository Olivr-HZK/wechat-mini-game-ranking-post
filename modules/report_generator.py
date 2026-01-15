"""
生成日报模块
根据游戏分析结果生成格式化的日报（JSON格式）
"""
from typing import List, Dict
from datetime import datetime
import json
import re


class ReportGenerator:
    """日报生成器"""
    
    def __init__(self):
        """初始化日报生成器"""
        pass
    
    def _clean_markdown(self, text: str) -> str:
        """
        清理Markdown标签，转换为纯文本格式
        
        Args:
            text: 包含Markdown标签的文本
        
        Returns:
            清理后的纯文本
        """
        if not text:
            return ""
        
        # 移除Markdown标题标记
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # 移除粗体标记
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        # 移除斜体标记
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        # 移除链接标记 [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # 移除代码块标记
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # 移除分隔线
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
        # 移除列表标记
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def _extract_core_content(self, analysis_text: str) -> Dict[str, str]:
        """
        从分析文本中提取核心玩法和吸引力
        
        Args:
            analysis_text: 分析文本
        
        Returns:
            包含core_gameplay和attraction的字典
        """
        core_gameplay = ""
        attraction = ""
        
        # 尝试提取"核心玩法"部分
        gameplay_patterns = [
            r'核心玩法[：:]\s*(.+?)(?=\n\n|\n\*\*|$)',
            r'核心玩法机制[：:]\s*(.+?)(?=\n\n|\n\*\*|$)',
            r'1[\.、]\s*.*?核心玩法[：:]\s*(.+?)(?=\n\n|\n\d+[\.、]|$)',
        ]
        
        for pattern in gameplay_patterns:
            match = re.search(pattern, analysis_text, re.DOTALL | re.IGNORECASE)
            if match:
                core_gameplay = match.group(1).strip()
                break
        
        # 尝试提取"吸引力"部分
        attraction_patterns = [
            r'吸引[点力][：:]\s*(.+?)(?=\n\n|\n\*\*|$)',
            r'6[\.、]\s*.*?吸引[点力][：:]\s*(.+?)(?=\n\n|$)',
            r'为什么.*?喜欢[：:]\s*(.+?)(?=\n\n|\n\*\*|$)',
        ]
        
        for pattern in attraction_patterns:
            match = re.search(pattern, analysis_text, re.DOTALL | re.IGNORECASE)
            if match:
                attraction = match.group(1).strip()
                break
        
        # 如果没找到，尝试按段落分割
        if not core_gameplay or not attraction:
            paragraphs = analysis_text.split('\n\n')
            for para in paragraphs:
                para_clean = para.strip()
                if '核心玩法' in para_clean or '玩法机制' in para_clean:
                    if not core_gameplay:
                        core_gameplay = self._clean_markdown(para_clean)
                elif '吸引' in para_clean or '喜欢' in para_clean:
                    if not attraction:
                        attraction = self._clean_markdown(para_clean)
        
        # 如果还是没找到，使用前两段作为核心玩法，最后一段作为吸引力
        if not core_gameplay or not attraction:
            paragraphs = [p.strip() for p in analysis_text.split('\n\n') if p.strip()]
            if paragraphs:
                if not core_gameplay and len(paragraphs) > 0:
                    core_gameplay = self._clean_markdown(paragraphs[0])
                if not attraction and len(paragraphs) > 1:
                    attraction = self._clean_markdown(paragraphs[-1])
        
        return {
            "core_gameplay": self._clean_markdown(core_gameplay) if core_gameplay else "暂无核心玩法分析",
            "attraction": self._clean_markdown(attraction) if attraction else "暂无吸引力分析"
        }
    
    def generate_daily_report(self, analyses: List[Dict], date: str = None) -> str:
        """
        生成日报内容（JSON格式）
        
        Args:
            analyses: 游戏分析结果列表
            date: 日期字符串，默认为今天
        
        Returns:
            JSON格式的日报内容（字符串）
        """
        if not date:
            date = datetime.now().strftime("%Y年%m月%d日")
        
        # 构建JSON结构
        report_data = {
            "report_type": "小游戏热榜玩法解析日报",
            "date": date,
            "game_count": len(analyses),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "games": []
        }
        
        # 处理每个游戏的分析
        for idx, analysis in enumerate(analyses, 1):
            game_name = analysis.get("game_name", "未知游戏")
            analysis_text = analysis.get("analysis", "暂无分析内容")
            analysis_data = analysis.get("analysis_data")  # 结构化的JSON数据
            model_used = analysis.get("model_used", "unknown")
            status = analysis.get("status", "unknown")
            
            # 如果有关键词数据，直接使用；否则从文本中提取
            if analysis_data and isinstance(analysis_data, dict):
                # 使用结构化的JSON数据
                core_gameplay_data = analysis_data.get("core_gameplay", {})
                attraction_data = analysis_data.get("attraction", {})
                
                # 构建核心玩法文本（合并所有字段）
                core_gameplay_parts = []
                if core_gameplay_data.get("mechanism"):
                    core_gameplay_parts.append(f"玩法机制：{core_gameplay_data['mechanism']}")
                if core_gameplay_data.get("operation"):
                    core_gameplay_parts.append(f"操作方式：{core_gameplay_data['operation']}")
                if core_gameplay_data.get("rules"):
                    core_gameplay_parts.append(f"游戏规则：{core_gameplay_data['rules']}")
                if core_gameplay_data.get("features"):
                    core_gameplay_parts.append(f"特色功能：{core_gameplay_data['features']}")
                
                core_gameplay = "\n\n".join(core_gameplay_parts) if core_gameplay_parts else "暂无核心玩法分析"
                
                # 构建吸引力文本（合并所有字段）
                attraction_parts = []
                if attraction_data.get("points"):
                    attraction_parts.append(f"吸引点：{attraction_data['points']}")
                if attraction_data.get("target_audience"):
                    attraction_parts.append(f"目标用户：{attraction_data['target_audience']}")
                if attraction_data.get("retention_factors"):
                    attraction_parts.append(f"留存因素：{attraction_data['retention_factors']}")
                
                attraction = "\n\n".join(attraction_parts) if attraction_parts else "暂无吸引力分析"
            else:
                # 从文本中提取（兼容旧格式）
                content = self._extract_core_content(analysis_text)
                core_gameplay = content["core_gameplay"]
                attraction = content["attraction"]
            
            game_data = {
                "index": idx,
                "game_name": game_name,
                "game_rank": analysis.get("game_rank", ""),  # 游戏排名
                "game_company": analysis.get("game_company", ""),  # 开发公司
                "rank_change": analysis.get("rank_change", "--"),  # 排名变化
                "gdrive_url": analysis.get("gdrive_url", ""),  # Google Drive视频链接
                "core_gameplay": core_gameplay,
                "attraction": attraction,
                "analysis_data": analysis_data,  # 保留结构化数据
                "full_analysis": analysis_text,  # 保留完整分析文本
                "analysis_model": model_used,
                "analysis_status": status
            }
            
            report_data["games"].append(game_data)
        
        # 添加总结
        report_data["summary"] = {
            "total_games": len(analyses),
            "description": f"本次日报分析了热榜上的 {len(analyses)} 款游戏，涵盖了多种游戏类型。这些游戏都具有简单易上手的特点，适合碎片化时间游玩。建议关注游戏的核心玩法机制和用户留存策略。"
        }
        
        # 转换为JSON字符串（格式化输出，便于阅读）
        return json.dumps(report_data, ensure_ascii=False, indent=2)
    
    def generate_feishu_format(self, analyses: List[Dict], date: str = None) -> Dict:
        """
        生成飞书格式的日报内容（JSON格式）
        
        Args:
            analyses: 游戏分析结果列表
            date: 日期字符串，默认为今天
        
        Returns:
            飞书消息格式的字典（JSON格式）
        """
        if not date:
            date = datetime.now().strftime("%Y年%m月%d日")
        
        # 构建结构化内容
        elements = []
        
        # 标题和摘要
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📅 日期：** {date}\n**🎮 分析游戏数量：** {len(analyses)}"
            }
        })
        
        elements.append({"tag": "hr"})
        
        # 每个游戏的分析
        for idx, analysis in enumerate(analyses, 1):
            game_name = analysis.get("game_name", "未知游戏")
            analysis_text = analysis.get("analysis", "暂无分析内容")
            analysis_data = analysis.get("analysis_data")  # 结构化的JSON数据
            
            # 如果有关键词数据，直接使用；否则从文本中提取
            if analysis_data and isinstance(analysis_data, dict):
                core_gameplay_data = analysis_data.get("core_gameplay", {})
                attraction_data = analysis_data.get("attraction", {})
                
                # 构建核心玩法文本
                core_gameplay_parts = []
                if core_gameplay_data.get("mechanism"):
                    core_gameplay_parts.append(f"**玩法机制：** {core_gameplay_data['mechanism']}")
                if core_gameplay_data.get("operation"):
                    core_gameplay_parts.append(f"**操作方式：** {core_gameplay_data['operation']}")
                if core_gameplay_data.get("rules"):
                    core_gameplay_parts.append(f"**游戏规则：** {core_gameplay_data['rules']}")
                if core_gameplay_data.get("features"):
                    core_gameplay_parts.append(f"**特色功能：** {core_gameplay_data['features']}")
                
                core_gameplay = "\n\n".join(core_gameplay_parts) if core_gameplay_parts else "暂无核心玩法分析"
                
                # 构建吸引力文本
                attraction_parts = []
                if attraction_data.get("points"):
                    attraction_parts.append(f"**吸引点：** {attraction_data['points']}")
                if attraction_data.get("target_audience"):
                    attraction_parts.append(f"**目标用户：** {attraction_data['target_audience']}")
                if attraction_data.get("retention_factors"):
                    attraction_parts.append(f"**留存因素：** {attraction_data['retention_factors']}")
                
                attraction = "\n\n".join(attraction_parts) if attraction_parts else "暂无吸引力分析"
            else:
                # 从文本中提取（兼容旧格式）
                content = self._extract_core_content(analysis_text)
                core_gameplay = content["core_gameplay"]
                attraction = content["attraction"]
            
            # 游戏标题和信息
            game_rank = analysis.get("game_rank", "")
            game_company = analysis.get("game_company", "")
            rank_change = analysis.get("rank_change", "--")
            gdrive_url = analysis.get("gdrive_url", "")
            
            # 构建游戏信息标题
            title_parts = [f"**【游戏 {idx}】{game_name}**"]
            if game_rank:
                title_parts.append(f"排名：{game_rank}")
            if game_company:
                title_parts.append(f"开发公司：{game_company}")
            if rank_change and rank_change != "--":
                title_parts.append(f"排名变化：{rank_change}")
            if gdrive_url:
                title_parts.append(f"[视频链接]({gdrive_url})")
            
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": " | ".join(title_parts)
                }
            })
            
            # 核心玩法 - 分段显示，避免内容过长
            if core_gameplay and core_gameplay != "暂无核心玩法分析":
                # 如果内容太长，可能需要分段
                # 飞书单个元素建议不超过2000字符
                if len(core_gameplay) > 1800:
                    # 分段显示
                    gameplay_lines = core_gameplay.split("\n\n")
                    current_section = ""
                    for line in gameplay_lines:
                        if len(current_section) + len(line) > 1800:
                            if current_section:
                                elements.append({
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**📋 核心玩法解析（续）：**\n{current_section}"
                                    }
                                })
                            current_section = line
                        else:
                            current_section += "\n\n" + line if current_section else line
                    if current_section:
                        elements.append({
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**📋 核心玩法解析{'（续）' if len(core_gameplay) > 1800 else ''}：**\n{current_section}"
                            }
                        })
                else:
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**📋 核心玩法解析：**\n{core_gameplay}"
                        }
                    })
            
            # 添加游戏截图（支持多张）- 放在玩法拆解下面
            screenshot_keys = analysis.get("screenshot_image_keys")
            if not screenshot_keys:
                # 兼容旧格式：单个screenshot_image_key
                screenshot_key = analysis.get("screenshot_image_key")
                if screenshot_key:
                    screenshot_keys = [screenshot_key]
            
            if screenshot_keys:
                # 添加截图标题
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**🎬 游戏截图：**"
                    }
                })
                
                # 垂直排列所有截图，每张图片都有标签
                screenshot_labels = ["开头", "中间", "结尾"]
                for img_idx, screenshot_key in enumerate(screenshot_keys):
                    label = screenshot_labels[img_idx] if img_idx < len(screenshot_labels) else f"截图{img_idx+1}"
                    # 添加标签
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"*{label}截图*"
                        }
                    })
                    # 添加图片（飞书会自动调整图片大小以适应卡片宽度）
                    elements.append({
                        "tag": "img",
                        "img_key": screenshot_key,
                        "alt": {
                            "tag": "plain_text",
                            "content": f"{game_name}{label}截图"
                        }
                    })
            
            # 吸引力分析 - 分段显示，避免内容过长
            if attraction and attraction != "暂无吸引力分析":
                if len(attraction) > 1800:
                    # 分段显示
                    attraction_lines = attraction.split("\n\n")
                    current_section = ""
                    for line in attraction_lines:
                        if len(current_section) + len(line) > 1800:
                            if current_section:
                                elements.append({
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**⭐ 吸引力分析（续）：**\n{current_section}"
                                    }
                                })
                            current_section = line
                        else:
                            current_section += "\n\n" + line if current_section else line
                    if current_section:
                        elements.append({
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**⭐ 吸引力分析{'（续）' if len(attraction) > 1800 else ''}：**\n{current_section}"
                            }
                        })
                else:
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**⭐ 吸引力分析：**\n{attraction}"
                        }
                    })
            
            if idx < len(analyses):
                elements.append({"tag": "hr"})
        
        # 总结
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📊 总结**\n\n本次日报分析了热榜上的 {len(analyses)} 款游戏，涵盖了多种游戏类型。这些游戏都具有简单易上手的特点，适合碎片化时间游玩。"
            }
        })
        
        # 添加JSON格式的原始数据（作为附件或额外信息）
        # 生成JSON格式的报告数据
        report_json = self.generate_daily_report(analyses, date)
        
        # 构建飞书消息卡片
        feishu_message = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🎮 小游戏热榜玩法解析日报 - {date}"
                    },
                    "template": "blue"
                },
                "elements": elements
            }
        }
        
        return feishu_message
    
    def _simplify_analysis(self, analysis_text: str, max_length: int = 1000) -> str:
        """
        简化分析文本，适应飞书消息长度限制
        
        Args:
            analysis_text: 原始分析文本
            max_length: 最大长度
        
        Returns:
            简化后的文本
        """
        if len(analysis_text) <= max_length:
            return analysis_text
        
        # 提取关键部分
        lines = analysis_text.split('\n')
        simplified = []
        current_length = 0
        
        for line in lines:
            if current_length + len(line) > max_length:
                break
            simplified.append(line)
            current_length += len(line) + 1
        
        result = '\n'.join(simplified)
        if len(result) < len(analysis_text):
            result += "\n\n...（内容已截断）"
        
        return result