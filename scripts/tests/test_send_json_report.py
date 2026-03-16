"""
测试从JSON文件发送飞书日报
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import os
import sys
from pathlib import Path
from modules.feishu_sender import FeishuSender
from modules.report_generator import ReportGenerator


def load_json_report(json_path: str) -> dict:
    """
    从JSON文件加载日报数据
    
    Args:
        json_path: JSON文件路径
    
    Returns:
        日报数据字典
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"文件不存在：{json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def convert_json_to_analyses(report_data: dict) -> list:
    """
    将JSON格式的日报数据转换为analyses格式（用于generate_feishu_format）
    
    Args:
        report_data: JSON格式的日报数据
    
    Returns:
        analyses格式的数据列表
    """
    analyses = []
    
    for game in report_data.get('games', []):
        analysis = {
            "game_name": game.get('game_name', '未知游戏'),
            "analysis": game.get('full_analysis', game.get('core_gameplay', '暂无分析内容')),
            "analysis_data": game.get('analysis_data'),  # 结构化的JSON数据
            "model_used": game.get('analysis_model', 'unknown'),
            "status": game.get('analysis_status', 'unknown')
        }
        analyses.append(analysis)
    
    return analyses


def send_json_report(json_path: str, use_card: bool = True):
    """
    从JSON文件读取日报并发送到飞书
    
    Args:
        json_path: JSON文件路径
        use_card: 是否使用卡片格式，默认True
    """
    print("=" * 60)
    print("测试：从JSON文件发送飞书日报")
    print("=" * 60)
    
    # 检查飞书配置
    try:
        import config
        if not config.FEISHU_WEBHOOK_URL:
            print("⚠ 警告：未配置飞书Webhook URL")
            print("  请在.env文件中配置 FEISHU_WEBHOOK_URL")
            return False
    except Exception as e:
        print(f"⚠ 配置检查失败：{str(e)}")
        return False
    
    # 加载JSON文件
    print(f"\n1. 加载JSON文件：{json_path}")
    try:
        report_data = load_json_report(json_path)
        print(f"   ✓ 文件加载成功")
        print(f"   - 日期：{report_data.get('date', 'N/A')}")
        print(f"   - 游戏数量：{report_data.get('game_count', 0)}")
        print(f"   - 生成时间：{report_data.get('generated_at', 'N/A')}")
    except Exception as e:
        print(f"   ✗ 加载失败：{str(e)}")
        return False
    
    # 初始化发送器
    print(f"\n2. 初始化飞书发送器...")
    feishu_sender = FeishuSender()
    print(f"   ✓ 初始化成功")
    
    if use_card:
        # 使用卡片格式发送
        print(f"\n3. 生成飞书卡片格式...")
        try:
            # 转换为analyses格式
            analyses = convert_json_to_analyses(report_data)
            print(f"   ✓ 转换成功，共 {len(analyses)} 个游戏分析")
            
            # 生成飞书格式
            report_generator = ReportGenerator()
            feishu_report = report_generator.generate_feishu_format(analyses, report_data.get('date'))
            print(f"   ✓ 飞书格式生成成功")
            
            # 显示消息结构
            if "card" in feishu_report and "elements" in feishu_report["card"]:
                element_count = len(feishu_report["card"]["elements"])
                print(f"   - 消息包含 {element_count} 个元素")
            
            # 发送消息
            print(f"\n4. 发送到飞书...")
            success = feishu_sender.send_card(feishu_report)
            
            if success:
                print(f"   ✓ 发送成功！")
                print(f"   请查看飞书群聊中的消息")
            else:
                print(f"   ✗ 发送失败")
            
            return success
            
        except Exception as e:
            print(f"   ✗ 生成失败：{str(e)}")
            import traceback
            traceback.print_exc()
            return False
    else:
        # 直接发送JSON文本
        print(f"\n3. 发送JSON文本...")
        report_json = json.dumps(report_data, ensure_ascii=False, indent=2)
        success = feishu_sender.send_report(report_json, use_card=False)
        
        if success:
            print(f"   ✓ 发送成功！")
        else:
            print(f"   ✗ 发送失败")
        
        return success


def main():
    """主函数"""
    # 默认使用最新的报告文件
    data_dir = Path("data")
    
    # 查找所有报告文件
    report_files = list(data_dir.glob("report_*.json"))
    
    if not report_files:
        print("错误：在data目录下未找到报告文件（report_*.json）")
        print("\n使用方法：")
        print("  python test_send_json_report.py [JSON文件路径]")
        print("\n示例：")
        print("  python test_send_json_report.py data/report_20260113_185330.json")
        return
    
    # 按修改时间排序，最新的在前
    report_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    latest_report = report_files[0]
    
    # 如果提供了命令行参数，使用指定的文件
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
    else:
        json_path = str(latest_report)
        print(f"未指定文件，使用最新的报告：{latest_report.name}\n")
    
    # 发送报告
    success = send_json_report(json_path, use_card=True)
    
    print("\n" + "=" * 60)
    if success:
        print("测试完成：发送成功")
    else:
        print("测试完成：发送失败")
    print("=" * 60)


if __name__ == "__main__":
    main()
