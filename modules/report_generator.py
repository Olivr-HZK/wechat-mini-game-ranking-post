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
                # 新格式：core_gameplay是字符串，baseline_game是字符串，innovation_points是数组
                # 兼容旧格式：core_gameplay可能是对象
                core_gameplay_str = analysis_data.get("core_gameplay", "")
                baseline_game_str = analysis_data.get("baseline_game", "")
                innovation_points_list = analysis_data.get("innovation_points", [])
                
                # 处理核心玩法（新格式是字符串，旧格式可能是对象）
                if isinstance(core_gameplay_str, str):
                    core_gameplay = core_gameplay_str if core_gameplay_str else "暂无核心玩法分析"
                elif isinstance(core_gameplay_str, dict):
                    # 兼容旧格式：对象格式
                    core_gameplay_parts = []
                    if core_gameplay_str.get("mechanism"):
                        core_gameplay_parts.append(core_gameplay_str['mechanism'])
                    if core_gameplay_str.get("operation"):
                        core_gameplay_parts.append(f"操作方式：{core_gameplay_str['operation']}")
                    if core_gameplay_str.get("rules"):
                        core_gameplay_parts.append(f"游戏规则：{core_gameplay_str['rules']}")
                    if core_gameplay_str.get("features"):
                        core_gameplay_parts.append(f"特色功能：{core_gameplay_str['features']}")
                    core_gameplay = "\n\n".join(core_gameplay_parts) if core_gameplay_parts else "暂无核心玩法分析"
                else:
                    core_gameplay = "暂无核心玩法分析"
                
                # 处理基线游戏（新格式是字符串）
                baseline_game = baseline_game_str if baseline_game_str else "未知"
                
                # 处理创新点（新格式是数组）
                if isinstance(innovation_points_list, list) and innovation_points_list:
                    innovation = "\n".join([f"- {str(x).strip()}" for x in innovation_points_list if str(x).strip()])
                else:
                    # 兼容旧格式
                    baseline_innovation_data = analysis_data.get("baseline_and_innovation", {})
                    innovation_data = analysis_data.get("innovation", {})
                    innovation_parts = []
                    if isinstance(baseline_innovation_data, dict):
                        pts2 = baseline_innovation_data.get("micro_innovations")
                        if isinstance(pts2, list) and pts2:
                            innovation_parts.append("微调创新点：\n" + "\n".join([f"- {str(x).strip()}" for x in pts2 if str(x).strip()]))
                    if isinstance(innovation_data, dict):
                        pts = innovation_data.get("innovation_points")
                        if isinstance(pts, list) and pts:
                            innovation_parts.append("创新点：\n" + "\n".join([f"- {str(x).strip()}" for x in pts if str(x).strip()]))
                    innovation = "\n\n".join([p for p in innovation_parts if p.strip()]).strip() if innovation_parts else "暂无创新点分析"
                
                # 兼容性：保留attraction字段（虽然新格式不再使用，但为了兼容性保留）
                attraction = "暂无吸引力分析"
            else:
                # 从文本中提取（兼容旧格式）
                content = self._extract_core_content(analysis_text)
                core_gameplay = content["core_gameplay"]
                baseline_game = "未知"
                innovation = "暂无创新点分析"
                # 兼容旧字段
                attraction = content["attraction"]
                genre_baseline = ""
            
            game_data = {
                "index": idx,
                "game_name": game_name,
                "game_rank": analysis.get("game_rank", ""),  # 游戏排名
                "game_company": analysis.get("game_company", ""),  # 开发公司
                "rank_change": analysis.get("rank_change", "--"),  # 排名变化
                "change_type": analysis.get("change_type", ""),  # 新进榜 / 飙升（供周报区分）
                "is_new_entry": analysis.get("is_new_entry", False),  # 是否新进榜游戏
                "monitor_date": analysis.get("monitor_date", ""),  # 监控日期 YYYY-MM-DD
                "platform": analysis.get("platform", ""),  # vx / dy
                "source": analysis.get("source", ""),  # 榜单
                "board_name": analysis.get("board_name", ""),  # 榜单名称
                "gdrive_url": analysis.get("gdrive_url", ""),  # Google Drive视频链接
                "core_gameplay": core_gameplay,
                "baseline_game": baseline_game if 'baseline_game' in locals() else "未知",
                "innovation_points": innovation if 'innovation' in locals() else "暂无创新点分析",
                # 兼容旧字段
                "attraction": attraction if 'attraction' in locals() else "",
                "genre_baseline": genre_baseline if 'genre_baseline' in locals() else "",
                "innovation": innovation if 'innovation' in locals() else "",
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
                # 新格式：core_gameplay是字符串，baseline_game是字符串，innovation_points是数组
                core_gameplay_str = analysis_data.get("core_gameplay", "")
                baseline_game_str = analysis_data.get("baseline_game", "")
                innovation_points_list = analysis_data.get("innovation_points", [])
                
                # 处理核心玩法（新格式是字符串，旧格式可能是对象）
                if isinstance(core_gameplay_str, str):
                    core_gameplay = core_gameplay_str if core_gameplay_str else "暂无核心玩法分析"
                elif isinstance(core_gameplay_str, dict):
                    # 兼容旧格式：对象格式
                    core_gameplay_parts = []
                    if core_gameplay_str.get("mechanism"):
                        core_gameplay_parts.append(f"**玩法机制：** {core_gameplay_str['mechanism']}")
                    if core_gameplay_str.get("operation"):
                        core_gameplay_parts.append(f"**操作方式：** {core_gameplay_str['operation']}")
                    if core_gameplay_str.get("rules"):
                        core_gameplay_parts.append(f"**游戏规则：** {core_gameplay_str['rules']}")
                    if core_gameplay_str.get("features"):
                        core_gameplay_parts.append(f"**特色功能：** {core_gameplay_str['features']}")
                    core_gameplay = "\n\n".join(core_gameplay_parts) if core_gameplay_parts else "暂无核心玩法分析"
                else:
                    core_gameplay = "暂无核心玩法分析"
                
                # 处理基线游戏（新格式是字符串）
                baseline_game = baseline_game_str if baseline_game_str else "未知"
                
                # 处理创新点（新格式是数组）
                if isinstance(innovation_points_list, list) and innovation_points_list:
                    innovation_text = "\n".join([f"- {str(x).strip()}" for x in innovation_points_list if str(x).strip()])
                else:
                    # 兼容旧格式：尝试从其他字段获取
                    baseline_innovation_data = analysis_data.get("baseline_and_innovation", {})
                    innovation_data = analysis_data.get("innovation", {})
                    innovation_parts = []
                    if isinstance(baseline_innovation_data, dict):
                        pts2 = baseline_innovation_data.get("micro_innovations")
                        if isinstance(pts2, list) and pts2:
                            innovation_parts.extend([str(x).strip() for x in pts2 if str(x).strip()])
                    if isinstance(innovation_data, dict):
                        pts = innovation_data.get("innovation_points")
                        if isinstance(pts, list) and pts:
                            innovation_parts.extend([str(x).strip() for x in pts if str(x).strip()])
                    innovation_text = "\n".join([f"- {x}" for x in innovation_parts]) if innovation_parts else "暂无创新点分析"
                
                # 兼容旧格式变量（用于后续代码）
                attraction = "暂无吸引力分析"
                genre_baseline_data = analysis_data.get("genre_baseline", {})
                if 'innovation_data' not in locals():
                    innovation_data = analysis_data.get("innovation", {})
                if 'baseline_innovation_data' not in locals():
                    baseline_innovation_data = analysis_data.get("baseline_and_innovation", {})
            else:
                # 从文本中提取（兼容旧格式）
                content = self._extract_core_content(analysis_text)
                core_gameplay = content["core_gameplay"]
                baseline_game = "未知"
                innovation_text = "暂无创新点分析"
                # 兼容旧格式变量
                attraction = content["attraction"]
                genre_baseline_data = {}
                innovation_data = {}
                baseline_innovation_data = {}
            
            # 游戏标题和信息
            game_rank = analysis.get("game_rank", "")
            game_company = analysis.get("game_company", "")
            rank_change = analysis.get("rank_change", "--")
            # 视频链接：优先跳回抖音分享链接（share_url），否则兜底用 gdrive_url
            share_url = analysis.get("share_url", "")
            gdrive_url = analysis.get("gdrive_url", "")
            monitor_date = analysis.get("monitor_date", "")
            platform = analysis.get("platform", "")
            source = analysis.get("source", "")
            board_name = analysis.get("board_name", "")
            
            def _ok(v: str) -> bool:
                return bool(v and str(v).strip() and str(v).strip() not in {"--", "N/A", "None"})

            # 构建游戏信息标题（多行 + 图标 + 加粗标签，增强可读性）
            title_lines = [f"**【游戏 {idx}】{game_name}**"]
            if _ok(game_rank):
                title_lines.append(f"**🏅 排名：** {game_rank}")
            if _ok(game_company):
                title_lines.append(f"**🏢 开发公司：** {game_company}")
            if _ok(platform):
                title_lines.append(f"**📱 平台：** {platform}")
            if _ok(source):
                title_lines.append(f"**🧭 来源：** {source}")
            if _ok(board_name):
                title_lines.append(f"**🏷️ 榜单：** {board_name}")
            if _ok(monitor_date):
                title_lines.append(f"**🗓️ 监控日期：** {monitor_date}")
            if _ok(rank_change) and str(rank_change).strip() != "--":
                title_lines.append(f"**📈 排名变化：** {rank_change}")
            video_link = share_url if _ok(share_url) else gdrive_url
            if _ok(video_link):
                title_lines.append(f"**🔗 视频链接：** [点击查看]({video_link})")
            
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n".join(title_lines)
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

            # 基线游戏（新格式：字符串）
            if 'baseline_game' in locals() and baseline_game and baseline_game != "未知":
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🎯 基线游戏：** {baseline_game}"
                    }
                })
            
            # 兼容旧格式：品类基线
            if isinstance(genre_baseline_data, dict) and any(
                genre_baseline_data.get(k) for k in ["base_genre", "reference", "baseline_loop"]
            ):
                base_genre = genre_baseline_data.get("base_genre") or ""
                reference = genre_baseline_data.get("reference") or ""
                baseline_loop = genre_baseline_data.get("baseline_loop") or ""

                gb_lines = []
                if base_genre:
                    gb_lines.append(f"**基类品类：** {base_genre}")
                if reference:
                    gb_lines.append(f"**参考范式：** {reference}")
                if baseline_loop:
                    gb_lines.append(f"**品类基线循环：** {baseline_loop}")

                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**🧩 品类基线：**\n" + "\n".join(gb_lines)
                    }
                })

            # 创新点分析（新格式：数组）
            if 'innovation_text' in locals() and innovation_text and innovation_text != "暂无创新点分析":
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**💡 基于基线游戏的创新点：**\n{innovation_text}"
                    }
                })
            
            # 兼容旧格式：创新点分析
            if isinstance(innovation_data, dict) and any(
                innovation_data.get(k) for k in ["summary", "innovation_points", "how_it_changes_play", "evidence_from_video", "tradeoffs"]
            ):
                inv_lines = []
                if innovation_data.get("summary"):
                    inv_lines.append(f"**创新总结：** {innovation_data['summary']}")
                pts = innovation_data.get("innovation_points")
                if isinstance(pts, list) and pts:
                    bullets = "\n".join([f"- {str(x).strip()}" for x in pts if str(x).strip()])
                    if bullets:
                        inv_lines.append("**创新点：**\n" + bullets)
                if innovation_data.get("how_it_changes_play"):
                    inv_lines.append(f"**如何改变玩法：** {innovation_data['how_it_changes_play']}")
                ev = innovation_data.get("evidence_from_video")
                if isinstance(ev, list) and ev:
                    eb = "\n".join([f"- {str(x).strip()}" for x in ev if str(x).strip()])
                    if eb:
                        inv_lines.append("**视频证据：**\n" + eb)
                if innovation_data.get("tradeoffs"):
                    inv_lines.append(f"**代价/风险：** {innovation_data['tradeoffs']}")

                inv_text = "\n\n".join([x for x in inv_lines if x.strip()]).strip()
                if inv_text:
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**💡 创新点分析：**\n{inv_text}"
                        }
                    })

            # 兼容旧格式：两段式：基线 + 微调创新（baseline_and_innovation）
            if isinstance(baseline_innovation_data, dict) and any(
                baseline_innovation_data.get(k) for k in ["base_genre", "baseline_loop", "micro_innovations"]
            ):
                bi_lines = []
                if baseline_innovation_data.get("base_genre"):
                    bi_lines.append(f"**基线品类：** {baseline_innovation_data['base_genre']}")
                if baseline_innovation_data.get("baseline_loop"):
                    bi_lines.append(f"**基线循环：** {baseline_innovation_data['baseline_loop']}")
                pts2 = baseline_innovation_data.get("micro_innovations")
                if isinstance(pts2, list) and pts2:
                    bullets = "\n".join([f"- {str(x).strip()}" for x in pts2 if str(x).strip()])
                    if bullets:
                        bi_lines.append("**微调创新点：**\n" + bullets)

                bi_text = "\n\n".join([x for x in bi_lines if x.strip()]).strip()
                if bi_text:
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**🧱 基线与微调创新：**\n{bi_text}"
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

    def generate_feishu_trend_only(self, trend_records: List[Dict], date: str = None) -> Dict:
        """
        生成仅包含四个平台玩法趋势周报的飞书卡片（不包含单款游戏玩法解析）。

        Args:
            trend_records: 各平台趋势记录列表，每项含 platform, trend_analysis, monitor_date, week_range, source
            date: 日期字符串，默认为今天

        Returns:
            飞书消息格式的字典（与 generate_feishu_format 结构一致）
        """
        if not date:
            date = datetime.now().strftime("%Y年%m月%d日")
        platform_display = {"wx": "微信小游戏", "dy": "抖音小游戏", "ios": "iOS", "android": "Android"}
        elements = []
        # 标题与周范围
        week_range = None
        for r in trend_records:
            if r.get("week_range"):
                week_range = r.get("week_range")
                break
        header_line = f"**📅 日期：** {date}"
        if week_range:
            header_line += f"\n**📆 周范围：** {week_range}"
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": header_line}
        })
        elements.append({"tag": "hr"})
        # 各平台趋势
        for r in trend_records:
            platform = r.get("platform", "")
            display = platform_display.get(platform, platform)
            text = (r.get("trend_analysis") or "").strip()
            if not text:
                continue
            # 单块建议不超过约 2000 字，过长则分段
            if len(text) > 1800:
                chunks = [text[i : i + 1800] for i in range(0, len(text), 1800)]
                for i, chunk in enumerate(chunks):
                    title = f"**📱 {display}**" if i == 0 else f"**📱 {display}（续）**"
                    elements.append({
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"{title}\n\n{chunk}"}
                    })
            else:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**📱 {display}**\n\n{text}"}
                })
            elements.append({"tag": "hr"})
        if elements and elements[-1].get("tag") == "hr":
            elements.pop()  # 去掉最后一条分隔线
        feishu_message = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": f"🎮 玩法趋势周报 - {date}"},
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