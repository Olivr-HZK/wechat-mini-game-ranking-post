"""
测试生成日报和发送日报功能
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
import json
from datetime import datetime
from modules.report_generator import ReportGenerator
from modules.feishu_sender import FeishuSender
from modules.video_analyzer import VideoAnalyzer
from modules.rank_extractor import RankExtractor
from modules.database import VideoDatabase
import config


def load_analysis_from_file(file_path: str) -> dict:
    """从分析结果文件中加载分析数据"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析文件内容
        lines = content.split('\n')
        analysis_data = {
            "game_name": "",
            "analysis": "",
            "model_used": "",
            "status": "success"
        }
        
        in_analysis_section = False
        analysis_lines = []
        
        for line in lines:
            line = line.strip()
            
            if line.startswith("游戏名称："):
                analysis_data["game_name"] = line.replace("游戏名称：", "").strip()
            elif line.startswith("使用模型："):
                analysis_data["model_used"] = line.replace("使用模型：", "").strip()
            elif line.startswith("分析状态："):
                analysis_data["status"] = line.replace("分析状态：", "").strip()
            elif "玩法解析：" in line or line.startswith("=" * 10):
                # 进入分析内容部分
                in_analysis_section = True
                continue
            elif in_analysis_section:
                # 收集分析内容（跳过分隔线）
                if not line.startswith("=") and line:
                    analysis_lines.append(line)
        
        # 合并分析内容
        analysis_data["analysis"] = "\n".join(analysis_lines)
        
        # 如果游戏名称为空，尝试从文件名提取
        if not analysis_data["game_name"]:
            filename = os.path.basename(file_path)
            # 文件名格式：analysis_游戏名_*.txt
            parts = filename.replace("analysis_", "").replace(".txt", "").split("_")
            if len(parts) > 0:
                analysis_data["game_name"] = parts[0]
        
        return analysis_data if analysis_data["game_name"] else None
    except Exception as e:
        print(f"读取分析文件时出错：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_generate_and_send_report():
    """测试生成和发送日报"""
    print("=" * 60)
    print("测试生成日报和发送日报功能")
    print("=" * 60)
    print()
    
    # 初始化
    report_generator = ReportGenerator()
    feishu_sender = FeishuSender()
    db = VideoDatabase()
    
    # 方式1：从分析结果文件加载
    print("【步骤1】加载分析结果...")
    analyses = []
    
    # 查找data目录下的分析结果文件
    analysis_files = []
    if os.path.exists("data"):
        for file in os.listdir("data"):
            if file.startswith("analysis_") and file.endswith(".txt"):
                analysis_files.append(os.path.join("data", file))
    
    if analysis_files:
        print(f"找到 {len(analysis_files)} 个分析结果文件")
        for file_path in analysis_files:
            print(f"  加载：{os.path.basename(file_path)}")
            analysis = load_analysis_from_file(file_path)
            if analysis and analysis.get("game_name"):
                analyses.append(analysis)
                print(f"    ✓ {analysis.get('game_name')}")
    else:
        print("  未找到分析结果文件")
    
    # 方式2：如果没有分析结果，使用Mock数据
    if not analyses:
        print("\n  使用Mock数据进行测试...")
        from modules.video_analyzer import VideoAnalyzer
        analyzer = VideoAnalyzer()
        
        # 获取排行榜中的游戏
        extractor = RankExtractor()
        games = extractor.get_top_games(top_n=3)
        
        for game in games:
            game_name = game.get("游戏名称", "未知游戏")
            mock_analysis = analyzer.analyze_game_info(game_name, game)
            if mock_analysis:
                analyses.append(mock_analysis)
                print(f"    ✓ {game_name} (Mock)")
    
    if not analyses:
        print("错误：没有可用的分析结果")
        return
    
    print(f"\n  共加载 {len(analyses)} 个游戏的分析结果\n")
    
    # 生成日报
    print("【步骤2】生成日报...")
    print("-" * 60)
    
    report = report_generator.generate_daily_report(analyses)
    
    # 保存日报到文件（JSON格式）
    report_file = f"data/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        os.makedirs("data", exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"✓ 日报已生成并保存到：{report_file}")
        print(f"  日报长度：{len(report)} 字符")
        
        # 解析JSON并显示预览
        try:
            report_data = json.loads(report)
            print(f"\n  日报信息：")
            print(f"    日期：{report_data.get('date', 'N/A')}")
            print(f"    游戏数量：{report_data.get('game_count', 0)}")
            print(f"    生成时间：{report_data.get('generated_at', 'N/A')}")
        except:
            pass
    except Exception as e:
        print(f"✗ 保存日报文件时出错：{str(e)}")
        return
    
    # 显示日报预览（前500字符）
    print("\n  日报预览（前500字符）：")
    print("-" * 60)
    print(report[:500])
    if len(report) > 500:
        print("  ...")
    print("-" * 60)
    
    # 发送日报到飞书
    print("\n【步骤3】发送日报到飞书...")
    print("-" * 60)
    
    if not feishu_sender.webhook_url:
        print("⚠ 警告：未配置飞书Webhook URL")
        print("  请在.env文件中设置 FEISHU_WEBHOOK_URL")
        print("  日报已保存到文件，可以手动发送")
        print("\n  如需测试发送功能，请：")
        print("  1. 在飞书群聊中添加'自定义机器人'")
        print("  2. 获取Webhook URL")
        print("  3. 在.env文件中配置 FEISHU_WEBHOOK_URL")
        return
    
    # 生成飞书格式的日报
    print("  生成飞书格式的日报...")
    feishu_report = report_generator.generate_feishu_format(analyses)
    
    # 显示飞书消息预览
    if "card" in feishu_report and "elements" in feishu_report["card"]:
        content = feishu_report["card"]["elements"][0].get("text", {}).get("content", "")
        print(f"  飞书消息长度：{len(content)} 字符")
        print(f"  消息预览（前300字符）：")
        print("  " + "-" * 56)
        print("  " + content[:300].replace("\n", "\n  "))
        if len(content) > 300:
            print("  ...")
        print("  " + "-" * 56)
    
    # 发送日报
    print("\n  正在发送到飞书...")
    success = feishu_sender.send_card(feishu_report)
    
    if success:
        print("✓ 日报发送成功！")
        print("  请查看飞书群聊中的消息")
    else:
        print("✗ 日报发送失败")
        print("  请检查：")
        print("  1. 飞书Webhook URL是否正确")
        print("  2. 网络连接是否正常")
        print("  3. 飞书机器人是否已添加到群聊")
        print("  4. 飞书消息内容是否超过长度限制")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_generate_and_send_report()