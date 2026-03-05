"""
测试完整工作流：从四个平台各找一个没有玩法的游戏进行测试
平台：微信小游戏、抖音小游戏、iOS（SensorTower）、Android（SensorTower）
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.database import VideoDatabase
from main import GameAnalysisWorkflow


def find_games_without_analysis():
    """
    从数据库中找到四个平台各一个没有玩法分析的游戏
    返回：{platform: game_name}
    """
    db = VideoDatabase()
    
    # 获取所有游戏
    all_games = db.get_all_games(limit=None)
    
    # 按平台分类，找出没有玩法分析的游戏
    platform_games = {
        'wx': [],  # 微信小游戏
        'dy': [],  # 抖音小游戏
        'ios': [],  # iOS
        'android': []  # Android
    }
    
    for game in all_games:
        game_name = game.get("game_name", "").strip()
        if not game_name:
            continue
        
        # 检查是否有玩法分析
        has_analysis = bool(game.get("gameplay_analysis") and game.get("gameplay_analysis").strip())
        
        if not has_analysis:
            # 根据平台分类
            platform = game.get("platform", "").strip()
            source = game.get("source", "").strip()
            
            # 检查是否有视频URL（需要视频才能分析）
            has_video = bool(
                game.get("gdrive_url") or 
                game.get("original_video_url") or 
                game.get("video_url")
            )
            
            if not has_video:
                continue
            
            # 分类到对应平台（优先根据rank字段判断）
            if game.get("rank_wx"):
                platform_games['wx'].append(game_name)
            elif game.get("rank_dy"):
                platform_games['dy'].append(game_name)
            elif game.get("rank_ios"):
                platform_games['ios'].append(game_name)
            elif game.get("rank_android"):
                platform_games['android'].append(game_name)
            elif "微信" in platform or (source == "引力引擎" and not game.get("rank_dy")):
                platform_games['wx'].append(game_name)
            elif "抖音" in platform or (source == "引力引擎" and game.get("rank_dy")):
                platform_games['dy'].append(game_name)
            elif source == "SensorTower":
                if "iOS" in platform or "ios" in platform.lower():
                    platform_games['ios'].append(game_name)
                elif "Android" in platform or "android" in platform.lower():
                    platform_games['android'].append(game_name)
    
    # 选择每个平台的第一个游戏
    selected_games = {}
    for platform, games in platform_games.items():
        if games:
            selected_games[platform] = games[0]
            print(f"✓ 找到{platform}平台游戏：{games[0]}")
        else:
            print(f"⚠ 未找到{platform}平台没有玩法分析的游戏")
    
    return selected_games


def main():
    """主函数：测试完整工作流"""
    print("=" * 60)
    print("测试完整工作流：四个平台各一个游戏")
    print("=" * 60)
    print()
    
    # 查找游戏
    print("【步骤1】查找四个平台各一个没有玩法分析的游戏...")
    selected_games = find_games_without_analysis()
    
    if len(selected_games) < 4:
        print(f"\n⚠ 只找到 {len(selected_games)} 个平台的游戏，需要4个平台")
        print("  提示：请确保数据库中有来自四个平台的游戏，且这些游戏有视频URL但没有玩法分析")
        return
    
    print(f"\n✓ 已选择 {len(selected_games)} 个平台的游戏：")
    for platform, game_name in selected_games.items():
        platform_name = {
            'wx': '微信小游戏',
            'dy': '抖音小游戏',
            'ios': 'iOS（SensorTower）',
            'android': 'Android（SensorTower）'
        }.get(platform, platform)
        print(f"  - {platform_name}: {game_name}")
    
    print("\n" + "=" * 60)
    print("开始测试完整工作流")
    print("=" * 60)
    print()
    
    # 创建工作流实例
    workflow = GameAnalysisWorkflow(
        force_refresh_analysis=True,  # 强制重新分析
        skip_screenshots=True,  # 跳过截图（加快测试速度）
    )
    
    # 从数据库获取选定的游戏信息
    db = VideoDatabase()
    test_games = []
    
    for platform, game_name in selected_games.items():
        game = db.get_game(game_name)
        if game:
            # 构建游戏信息字典（模拟从CSV读取的格式）
            game_info = {
                "游戏名称": game_name,
                "排名": game.get("rank_wx") or game.get("rank_dy") or game.get("rank_ios") or game.get("rank_android") or game.get("game_rank") or "",
                "游戏类型": "puzzle",  # 默认类型
                "平台": game.get("platform") or {
                    'wx': '微信小游戏',
                    'dy': '抖音小游戏',
                    'ios': 'iOS',
                    'android': 'Android'
                }.get(platform, ""),
                "来源": game.get("source") or {
                    'wx': '引力引擎',
                    'dy': '引力引擎',
                    'ios': 'SensorTower',
                    'android': 'SensorTower'
                }.get(platform, ""),
                "榜单": game.get("board_name") or "",
                "监控日期": game.get("monitor_date") or "",
                "开发公司": game.get("game_company") or "",
                "排名变化": game.get("rank_change") or "--",
                "地区": "中国" if platform in ['wx', 'dy'] else "多地区"
            }
            test_games.append(game_info)
    
    if not test_games:
        print("错误：无法从数据库获取游戏信息")
        return
    
    print(f"【步骤2】搜索并下载视频（{len(test_games)}个游戏）...")
    video_results = workflow.step2_search_videos(test_games)
    
    if not video_results:
        print("错误：未能获取视频信息")
        return
    
    print(f"\n【步骤3】分析视频（{len(video_results)}个游戏）...")
    analyses = workflow.step3_analyze_videos(video_results)
    
    if not analyses:
        print("错误：未能生成分析结果")
        return
    
    print(f"\n【步骤4】生成日报...")
    report_json = workflow.step4_generate_report(analyses)
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n分析结果摘要：")
    for analysis in analyses:
        game_name = analysis.get("game_name", "未知")
        analysis_data = analysis.get("analysis_data", {})
        
        core_gameplay = ""
        baseline_game = ""
        innovation_points = []
        
        if isinstance(analysis_data, dict):
            # 新格式
            if isinstance(analysis_data.get("core_gameplay"), str):
                core_gameplay = analysis_data.get("core_gameplay", "")[:100] + "..."
            baseline_game = analysis_data.get("baseline_game", "未知")
            innovation_points = analysis_data.get("innovation_points", [])
        
        print(f"\n游戏：{game_name}")
        print(f"  核心玩法：{core_gameplay[:80]}...")
        print(f"  基线游戏：{baseline_game}")
        print(f"  创新点：{len(innovation_points)}条")
        if innovation_points:
            for i, point in enumerate(innovation_points[:3], 1):
                print(f"    {i}. {point}")


if __name__ == "__main__":
    main()
