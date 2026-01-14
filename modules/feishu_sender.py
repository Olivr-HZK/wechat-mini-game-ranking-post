"""
飞书机器人发送模块
通过飞书Webhook发送日报
"""
import requests
import json
import os
from typing import Dict, Optional
import config


class FeishuSender:
    """飞书消息发送器"""
    
    def __init__(self, webhook_url: str = None):
        """
        初始化飞书发送器
        
        Args:
            webhook_url: 飞书Webhook URL，默认从配置文件读取
        """
        self.webhook_url = webhook_url or config.FEISHU_WEBHOOK_URL
    
    def send_text(self, text: str) -> bool:
        """
        发送纯文本消息
        
        Args:
            text: 要发送的文本内容
        
        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            print("警告：未配置飞书Webhook URL，消息将不会发送")
            return False
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }
        
        return self._send(payload)
    
    def send_markdown(self, markdown: str) -> bool:
        """
        发送Markdown格式消息
        
        Args:
            markdown: Markdown格式的内容
        
        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            print("警告：未配置飞书Webhook URL，消息将不会发送")
            return False
        
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": markdown
                        }
                    }
                ]
            }
        }
        
        return self._send(payload)
    
    def send_card(self, card_data: Dict) -> bool:
        """
        发送飞书卡片消息
        
        Args:
            card_data: 飞书卡片格式的数据
        
        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            print("警告：未配置飞书Webhook URL，消息将不会发送")
            return False
        
        return self._send(card_data)
    
    def send_image(self, image_url: str, title: str = "游戏截图") -> bool:
        """
        通过飞书机器人发送图片（使用图片URL）
        
        注意：飞书webhook可能不支持直接发送图片URL，此方法使用卡片格式显示图片
        
        Args:
            image_url: 图片URL（必须是公开可访问的）
            title: 图片标题
        
        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            print("警告：未配置飞书Webhook URL，消息将不会发送")
            return False
        
        # 使用卡片格式显示图片
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "img",
                        "img_key": image_url,  # 尝试直接使用URL
                        "alt": {
                            "tag": "plain_text",
                            "content": title
                        }
                    }
                ]
            }
        }
        
        # 如果上面的方式不支持，使用Markdown格式
        # 飞书卡片支持在lark_md中使用图片
        fallback_payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"![{title}]({image_url})"
                        }
                    }
                ]
            }
        }
        
        # 先尝试使用img元素，如果失败则使用Markdown
        result = self._send(payload)
        if not result:
            print("  尝试使用Markdown格式发送图片...")
            result = self._send(fallback_payload)
        
        return result
    
    def send_image_by_file(self, image_path: str, title: str = "游戏截图") -> bool:
        """
        通过飞书API上传并发送图片（需要app_id和app_secret）
        
        注意：此方法需要配置飞书应用的app_id和app_secret
        
        Args:
            image_path: 本地图片文件路径
            title: 图片标题
        
        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            print("警告：未配置飞书Webhook URL，消息将不会发送")
            return False
        
        if not os.path.exists(image_path):
            print(f"错误：图片文件不存在：{image_path}")
            return False
        
        # 检查是否配置了飞书应用凭证
        app_id = config.FEISHU_APP_ID if hasattr(config, 'FEISHU_APP_ID') else None
        app_secret = config.FEISHU_APP_SECRET if hasattr(config, 'FEISHU_APP_SECRET') else None
        
        if not app_id or not app_secret:
            print("警告：未配置飞书应用凭证（FEISHU_APP_ID和FEISHU_APP_SECRET）")
            print("  将使用图片URL方式发送（需要图片是公开可访问的）")
            # 如果图片已经上传到Google Drive，可以获取URL
            return False
        
        try:
            # 步骤1：获取访问令牌
            print("正在获取飞书访问令牌...")
            token_url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/'
            token_headers = {'Content-Type': 'application/json'}
            token_data = {'app_id': app_id, 'app_secret': app_secret}
            
            token_response = requests.post(token_url, json=token_data, headers=token_headers)
            token_result = token_response.json()
            
            if token_result.get('code') != 0:
                print(f"获取访问令牌失败：{token_result.get('msg', '未知错误')}")
                return False
            
            tenant_access_token = token_result.get('tenant_access_token')
            print("  ✓ 访问令牌获取成功")
            
            # 步骤2：上传图片
            print("正在上传图片到飞书...")
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
                print("  警告：未安装requests_toolbelt，使用标准方式上传")
                print("  建议运行: pip install requests-toolbelt")
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
                print(f"上传图片失败：{error_msg}")
                if upload_result.get('data'):
                    print(f"  错误详情：{upload_result.get('data')}")
                print(f"  响应内容：{upload_response.text}")
                return False
            
            image_key = upload_result.get('data', {}).get('image_key')
            if not image_key:
                print("上传图片失败：未获取到image_key")
                return False
            
            print(f"  ✓ 图片上传成功，image_key: {image_key[:20]}...")
            
            # 步骤3：通过webhook发送图片
            print("正在发送图片消息...")
            payload = {
                "msg_type": "image",
                "content": {
                    "image_key": image_key
                }
            }
            
            return self._send(payload)
            
        except Exception as e:
            print(f"发送图片时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _send(self, payload: Dict) -> bool:
        """
        发送消息的内部方法
        
        Args:
            payload: 消息负载
        
        Returns:
            是否发送成功
        """
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    print("消息发送成功")
                    # 调试：显示发送的消息结构
                    if "card" in payload and "elements" in payload["card"]:
                        element_count = len(payload["card"]["elements"])
                        print(f"  消息包含 {element_count} 个元素")
                        # 显示每个元素的类型
                        for i, elem in enumerate(payload["card"]["elements"][:5], 1):
                            if "text" in elem and "content" in elem["text"]:
                                content_preview = elem["text"]["content"][:50].replace("\n", " ")
                                print(f"    元素 {i}: {content_preview}...")
                    return True
                else:
                    print(f"消息发送失败：{result.get('msg', '未知错误')}")
                    if result.get('data'):
                        print(f"  错误详情：{result.get('data')}")
                    return False
            else:
                print(f"HTTP请求失败：{response.status_code}")
                print(f"响应内容：{response.text}")
                return False
                
        except Exception as e:
            print(f"发送消息时出错：{str(e)}")
            return False
    
    def send_report(self, report_content: str, use_card: bool = True) -> bool:
        """
        发送日报的便捷方法
        
        Args:
            report_content: 日报内容（JSON格式字符串）
            use_card: 是否使用卡片格式，默认True
        
        Returns:
            是否发送成功
        """
        if use_card:
            # 解析JSON格式的报告
            try:
                import json
                report_data = json.loads(report_content)
                
                # 构建飞书卡片格式
                elements = []
                
                # 标题和摘要
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📅 日期：** {report_data.get('date', 'N/A')}\n**🎮 分析游戏数量：** {report_data.get('game_count', 0)}"
                    }
                })
                
                elements.append({"tag": "hr"})
                
                # 每个游戏的分析
                for game in report_data.get('games', []):
                    idx = game.get('index', 0)
                    game_name = game.get('game_name', '未知游戏')
                    core_gameplay = game.get('core_gameplay', '暂无')
                    attraction = game.get('attraction', '暂无')
                    
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**【游戏 {idx}】{game_name}**"
                        }
                    })
                    
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**📋 核心玩法解析：**\n{core_gameplay}"
                        }
                    })
                    
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**⭐ 吸引力分析：**\n{attraction}"
                        }
                    })
                    
                    if idx < len(report_data.get('games', [])):
                        elements.append({"tag": "hr"})
                
                # 总结
                elements.append({"tag": "hr"})
                summary = report_data.get('summary', {})
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📊 总结**\n\n{summary.get('description', '')}"
                    }
                })
                
                # 添加JSON数据
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📄 JSON格式数据：**\n```json\n{report_content}\n```"
                    }
                })
                
                card_data = {
                    "msg_type": "interactive",
                    "card": {
                        "config": {
                            "wide_screen_mode": True
                        },
                        "header": {
                            "title": {
                                "tag": "plain_text",
                                "content": f"🎮 小游戏热榜玩法解析日报 - {report_data.get('date', 'N/A')}"
                            },
                            "template": "blue"
                        },
                        "elements": elements
                    }
                }
                
                return self.send_card(card_data)
            except json.JSONDecodeError:
                print("错误：报告内容不是有效的JSON格式")
                return False
            except Exception as e:
                print(f"发送报告时出错：{str(e)}")
                return False
        else:
            # 如果不是卡片格式，直接发送JSON文本
            return self.send_text(report_content)