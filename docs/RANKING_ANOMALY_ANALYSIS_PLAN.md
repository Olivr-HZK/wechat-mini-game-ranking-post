# 榜单异动游戏玩法解析与起量分析方案

## 📋 方案概述

聚焦于**榜单异动检测** → **玩法解析** → **起量验证**的完整流程：
1. 汇总引力引擎（微信/抖音小游戏）和 SensorTower（iOS/Android）的榜单数据
2. 检测排名飙升和新进榜游戏
3. 对异动游戏进行玩法解析
4. 在起量分析中查找这些游戏的起量情况

---

## 🎯 核心流程

```
数据汇总 → 异动检测 → 玩法解析 → 起量查询 → 报告生成
```

### 详细流程

```
1. 数据汇总阶段
   ├── 读取引力引擎榜单（微信/抖音小游戏）
   ├── 读取 SensorTower 榜单（iOS/Android）
   └── 统一数据格式，存储到数据库

2. 异动检测阶段
   ├── 对比本周 vs 上周排名
   ├── 识别排名飙升（≥阈值）
   ├── 识别新进榜游戏
   └── 生成异动游戏列表

3. 玩法解析阶段
   ├── 对异动游戏搜索视频
   ├── 下载视频到 Google Drive
   └── AI 分析游戏玩法

4. 起量查询阶段
   ├── 在 SensorTower 起量数据中查找异动游戏
   ├── 获取下载量数据
   └── 验证是否真的起量

5. 报告生成阶段
   ├── 生成异动游戏报告（含玩法解析）
   ├── 标注起量情况
   └── 发送到飞书/企业微信/Google Sheets
```

---

## 🛠️ 技术实现方案

### 阶段一：数据汇总模块

#### 1.1 创建数据汇总器

**文件：`modules/ranking_aggregator.py`**

```python
"""
榜单数据汇总模块
整合引力引擎和 SensorTower 的榜单数据
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from modules.rank_extractor import RankExtractor
from modules.database import VideoDatabase


class RankingAggregator:
    """榜单数据汇总器"""
    
    def __init__(self):
        self.db = VideoDatabase()
        self.rank_extractor_wx = RankExtractor(platform='wx')
        self.rank_extractor_dy = RankExtractor(platform='dy')
    
    def aggregate_gravity_rankings(self, date: str = None) -> List[Dict]:
        """
        汇总引力引擎榜单数据（微信 + 抖音）
        
        Args:
            date: 监控日期，格式 YYYY-MM-DD，None 表示使用最新数据
        
        Returns:
            统一格式的榜单数据列表
        """
        aggregated = []
        
        # 微信小游戏榜单
        wx_games = self.rank_extractor_wx.get_top_games(top_n=None)
        for game in wx_games:
            aggregated.append({
                'game_name': game.get('游戏名称', ''),
                'rank': game.get('排名', ''),
                'platform': '微信小游戏',
                'source': '引力引擎',
                'board_name': game.get('榜单', ''),
                'monitor_date': game.get('监控日期', date or datetime.now().strftime('%Y-%m-%d')),
                'game_type': game.get('游戏类型', ''),
                'heat_index': game.get('热度指数', ''),
                'company': game.get('开发公司', ''),
                'rank_change': game.get('排名变化', ''),
                'tags': game.get('标签', ''),
            })
        
        # 抖音小游戏榜单
        dy_games = self.rank_extractor_dy.get_top_games(top_n=None)
        for game in dy_games:
            aggregated.append({
                'game_name': game.get('游戏名称', ''),
                'rank': game.get('排名', ''),
                'platform': '抖音小游戏',
                'source': '引力引擎',
                'board_name': game.get('榜单', ''),
                'monitor_date': game.get('监控日期', date or datetime.now().strftime('%Y-%m-%d')),
                'game_type': game.get('游戏类型', ''),
                'heat_index': game.get('热度指数', ''),
                'company': game.get('开发公司', ''),
                'rank_change': game.get('排名变化', ''),
                'tags': game.get('标签', ''),
            })
        
        return aggregated
    
    def aggregate_sensortower_rankings(self, date: str = None) -> List[Dict]:
        """
        汇总 SensorTower 榜单数据（iOS + Android）
        
        Args:
            date: 监控日期，格式 YYYY-MM-DD
        
        Returns:
            统一格式的榜单数据列表
        """
        # TODO: 实现 SensorTower API 调用
        # 需要从 market_monitor_v1.6.js 的逻辑中提取
        # 或者创建 Python 版本的 SensorTower API 客户端
        
        aggregated = []
        
        # 这里需要调用 SensorTower API
        # 暂时返回空列表，后续实现
        return aggregated
    
    def save_ranking_snapshot(self, data: List[Dict], snapshot_date: str):
        """
        保存榜单快照到数据库
        
        Args:
            data: 榜单数据列表
            snapshot_date: 快照日期
        """
        for game in data:
            self.db.save_game({
                'game_name': game['game_name'],
                'game_rank': str(game.get('rank', '')),
                'platform': game.get('platform', ''),
                'source': game.get('source', ''),
                'board_name': game.get('board_name', ''),
                'monitor_date': snapshot_date,
                'game_company': game.get('company', ''),
                'rank_change': game.get('rank_change', ''),
            })
```

#### 1.2 SensorTower API 客户端

**文件：`modules/sensortower_client.py`**

```python
"""
SensorTower API 客户端
从 market_monitor_v1.6.js 移植 API 调用逻辑
"""

import requests
from typing import Dict, List, Optional
import config


class SensorTowerClient:
    """SensorTower API 客户端"""
    
    def __init__(self, api_token: str = None):
        self.api_token = api_token or getattr(config, 'SENSORTOWER_API_TOKEN', '')
        self.base_url = "https://api.sensortower.com/v1"
    
    def get_ranking(self, 
                   platform: str,  # 'ios' or 'android'
                   category: str,
                   chart_type: str,
                   country: str,
                   date: str) -> Dict:
        """
        获取榜单数据
        
        Args:
            platform: 平台（ios/android）
            category: 品类ID（iOS: "7012", Android: "game_puzzle"）
            chart_type: 榜单类型（iOS: "topfreeapplications", Android: "topselling_free"）
            country: 国家代码（US, JP, GB, DE, IN）
            date: 日期（YYYY-MM-DD）
        
        Returns:
            API 响应数据
        """
        endpoint = f"/{platform}/ranking"
        params = {
            'auth_token': self.api_token,
            'category': category,
            'chart_type': chart_type,
            'country': country,
            'date': date
        }
        
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            return {'success': True, 'data': response.json()}
        else:
            return {'success': False, 'status': response.status_code, 'message': response.text}
    
    def get_app_name(self, app_id: str, platform: str) -> Optional[str]:
        """
        获取应用名称
        
        Args:
            app_id: 应用ID
            platform: 平台（ios/android）
        
        Returns:
            应用名称
        """
        # TODO: 实现获取应用名称的 API 调用
        pass
```

---

### 阶段二：异动检测模块

#### 2.1 创建异动检测器

**文件：`modules/anomaly_detector.py`**

```python
"""
榜单异动检测模块
检测排名飙升和新进榜游戏
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from modules.database import VideoDatabase
import config


class AnomalyDetector:
    """榜单异动检测器"""
    
    def __init__(self):
        self.db = VideoDatabase()
        
        # 异动阈值配置
        self.rank_change_threshold = {
            '微信小游戏': getattr(config, 'WECHAT_RANK_CHANGE_THRESHOLD', 15),
            '抖音小游戏': getattr(config, 'DOUYIN_RANK_CHANGE_THRESHOLD', 15),
            'iOS': getattr(config, 'IOS_RANK_CHANGE_THRESHOLD', 20),
            'Android': getattr(config, 'ANDROID_RANK_CHANGE_THRESHOLD', 20),
        }
        
        self.new_entry_top_n = {
            '微信小游戏': getattr(config, 'WECHAT_NEW_ENTRY_TOP', 50),
            '抖音小游戏': getattr(config, 'DOUYIN_NEW_ENTRY_TOP', 50),
            'iOS': getattr(config, 'IOS_NEW_ENTRY_TOP', 50),
            'Android': getattr(config, 'ANDROID_NEW_ENTRY_TOP', 50),
        }
    
    def detect_anomalies(self, 
                        current_date: str,
                        previous_date: str = None) -> List[Dict]:
        """
        检测榜单异动
        
        Args:
            current_date: 当前日期（YYYY-MM-DD）
            previous_date: 对比日期（YYYY-MM-DD），None 表示自动计算（7天前）
        
        Returns:
            异动游戏列表
        """
        if previous_date is None:
            prev_date_obj = datetime.strptime(current_date, '%Y-%m-%d') - timedelta(days=7)
            previous_date = prev_date_obj.strftime('%Y-%m-%d')
        
        anomalies = []
        
        # 获取当前榜单数据
        current_rankings = self._get_rankings_by_date(current_date)
        previous_rankings = self._get_rankings_by_date(previous_date)
        
        # 按平台分组处理
        platforms = ['微信小游戏', '抖音小游戏', 'iOS', 'Android']
        
        for platform in platforms:
            current_platform = [r for r in current_rankings if r.get('platform') == platform]
            previous_platform = [r for r in previous_rankings if r.get('platform') == platform]
            
            # 构建上周排名映射
            prev_rank_map = {}
            for game in previous_platform:
                game_name = game.get('game_name', '')
                rank = self._parse_rank(game.get('game_rank', ''))
                if game_name and rank:
                    prev_rank_map[game_name] = rank
            
            # 检测异动
            for game in current_platform:
                game_name = game.get('game_name', '')
                current_rank = self._parse_rank(game.get('game_rank', ''))
                
                if not game_name or not current_rank:
                    continue
                
                # 检查是否在新进榜范围内
                if current_rank > self.new_entry_top_n.get(platform, 50):
                    continue
                
                previous_rank = prev_rank_map.get(game_name)
                
                anomaly_type = None
                change_value = None
                
                if previous_rank is None:
                    # 新进榜
                    anomaly_type = '新进榜'
                    change_value = f"新进 #{current_rank}"
                else:
                    # 排名变化
                    rank_change = previous_rank - current_rank
                    threshold = self.rank_change_threshold.get(platform, 15)
                    
                    if rank_change >= threshold:
                        anomaly_type = '排名飙升'
                        change_value = f"↑{rank_change} (#{previous_rank} → #{current_rank})"
                    elif rank_change >= threshold // 2:
                        anomaly_type = '排名上升'
                        change_value = f"↑{rank_change} (#{previous_rank} → #{current_rank})"
                
                if anomaly_type:
                    anomalies.append({
                        'game_name': game_name,
                        'platform': platform,
                        'current_rank': current_rank,
                        'previous_rank': previous_rank,
                        'rank_change': rank_change if previous_rank else None,
                        'anomaly_type': anomaly_type,
                        'change_value': change_value,
                        'monitor_date': current_date,
                        'company': game.get('company', ''),
                        'game_type': game.get('game_type', ''),
                        'source': game.get('source', ''),
                    })
        
        # 按异动类型和排名变化排序
        anomalies.sort(key=lambda x: (
            {'新进榜': 0, '排名飙升': 1, '排名上升': 2}.get(x['anomaly_type'], 3),
            -(x.get('rank_change') or 0)
        ))
        
        return anomalies
    
    def _get_rankings_by_date(self, date: str) -> List[Dict]:
        """从数据库获取指定日期的榜单数据"""
        # TODO: 实现从数据库查询
        # 需要根据 monitor_date 查询 games 表
        return []
    
    def _parse_rank(self, rank_str: str) -> Optional[int]:
        """解析排名字符串为整数"""
        if not rank_str:
            return None
        try:
            # 处理 "1", "#1", "排名1" 等格式
            rank_str = str(rank_str).strip().replace('#', '').replace('排名', '')
            return int(rank_str)
        except:
            return None
```

---

### 阶段三：玩法解析集成

#### 3.1 创建异动游戏分析工作流

**文件：`modules/anomaly_game_analyzer.py`**

```python
"""
异动游戏玩法解析模块
对异动游戏进行视频搜索和玩法分析
"""

from typing import List, Dict
from modules.anomaly_detector import AnomalyDetector
from modules.video_searcher import VideoSearcher
from modules.video_analyzer import VideoAnalyzer
from modules.database import VideoDatabase


class AnomalyGameAnalyzer:
    """异动游戏分析器"""
    
    def __init__(self):
        self.anomaly_detector = AnomalyDetector()
        self.video_searcher = VideoSearcher()
        self.video_analyzer = VideoAnalyzer()
        self.db = VideoDatabase()
    
    def analyze_anomaly_games(self, 
                             current_date: str,
                             previous_date: str = None,
                             max_games: int = None) -> List[Dict]:
        """
        分析异动游戏
        
        Args:
            current_date: 当前日期
            previous_date: 对比日期
            max_games: 最大分析游戏数量，None 表示分析所有
        
        Returns:
            分析结果列表
        """
        # 1. 检测异动
        print("【步骤1】检测榜单异动...")
        anomalies = self.anomaly_detector.detect_anomalies(current_date, previous_date)
        
        if not anomalies:
            print("未发现异动游戏")
            return []
        
        print(f"发现 {len(anomalies)} 个异动游戏")
        
        # 限制数量
        if max_games:
            anomalies = anomalies[:max_games]
        
        # 2. 对异动游戏进行玩法解析
        print("\n【步骤2】对异动游戏进行玩法解析...")
        analysis_results = []
        
        for idx, anomaly in enumerate(anomalies, 1):
            game_name = anomaly['game_name']
            platform = anomaly['platform']
            
            print(f"\n[{idx}/{len(anomalies)}] 分析游戏: {game_name} ({platform})")
            print(f"  异动类型: {anomaly['anomaly_type']}")
            print(f"  排名变化: {anomaly['change_value']}")
            
            # 检查数据库中是否已有分析结果
            db_game = self.db.get_game(game_name)
            if db_game and db_game.get('gameplay_analysis'):
                print(f"  ✓ 使用已有分析结果")
                analysis = {
                    'game_name': game_name,
                    'anomaly_info': anomaly,
                    'analysis': db_game.get('gameplay_analysis', ''),
                    'analysis_data': None,  # TODO: 解析 gameplay_analysis JSON
                    'video_url': db_game.get('gdrive_url', ''),
                    'has_video': bool(db_game.get('gdrive_url')),
                }
            else:
                # 搜索并下载视频
                print(f"  搜索视频...")
                video_path = self.video_searcher.search_and_download(
                    game_name=game_name,
                    game_type=anomaly.get('game_type', '')
                )
                
                # 重新从数据库获取最新信息
                db_game = self.db.get_game(game_name)
                video_url = None
                if db_game:
                    video_url = db_game.get('gdrive_url')
                
                # 分析视频
                if video_url:
                    print(f"  分析游戏玩法...")
                    analysis_result = self.video_analyzer.analyze_video(
                        video_path=None,
                        game_name=game_name,
                        game_info={
                            '游戏名称': game_name,
                            '游戏类型': anomaly.get('game_type', ''),
                            '开发公司': anomaly.get('company', ''),
                            '平台': platform,
                        },
                        video_url=video_url,
                        force_refresh=False,
                    )
                    
                    if analysis_result:
                        analysis = {
                            'game_name': game_name,
                            'anomaly_info': anomaly,
                            'analysis': analysis_result.get('analysis', ''),
                            'analysis_data': analysis_result.get('analysis_data', {}),
                            'video_url': video_url,
                            'has_video': True,
                        }
                    else:
                        analysis = {
                            'game_name': game_name,
                            'anomaly_info': anomaly,
                            'analysis': '分析失败',
                            'analysis_data': None,
                            'video_url': video_url,
                            'has_video': bool(video_url),
                        }
                else:
                    print(f"  ⚠ 未找到视频，跳过分析")
                    analysis = {
                        'game_name': game_name,
                        'anomaly_info': anomaly,
                        'analysis': '未找到视频',
                        'analysis_data': None,
                        'video_url': None,
                        'has_video': False,
                    }
            
            analysis_results.append(analysis)
        
        return analysis_results
```

---

### 阶段四：起量查询模块

#### 4.1 创建起量查询器

**文件：`modules/rising_apps_checker.py`**

```python
"""
起量查询模块
在 SensorTower 起量数据中查找异动游戏
"""

from typing import List, Dict, Optional
from modules.sensortower_client import SensorTowerClient
import config


class RisingAppsChecker:
    """起量游戏查询器"""
    
    def __init__(self):
        self.sensortower = SensorTowerClient()
        self.download_threshold = getattr(config, 'DOWNLOAD_THRESHOLD', 5000)
    
    def check_rising_status(self, 
                          game_name: str,
                          app_id: str = None,
                          platform: str = 'ios') -> Optional[Dict]:
        """
        检查游戏起量状态
        
        Args:
            game_name: 游戏名称
            app_id: 应用ID（如果已知）
            platform: 平台（ios/android）
        
        Returns:
            起量信息，如果未起量返回 None
        """
        # TODO: 实现 SensorTower API 调用
        # 1. 如果不知道 app_id，先通过游戏名称搜索
        # 2. 获取下载量数据
        # 3. 判断是否超过阈值
        
        # 临时实现：返回 None
        return None
    
    def batch_check_rising_status(self, 
                                 anomaly_games: List[Dict]) -> List[Dict]:
        """
        批量检查起量状态
        
        Args:
            anomaly_games: 异动游戏列表
        
        Returns:
            带起量信息的游戏列表
        """
        results = []
        
        for game in anomaly_games:
            game_name = game.get('game_name', '')
            platform = game.get('platform', '')
            
            # 转换平台名称
            st_platform = 'ios' if platform == 'iOS' else 'android'
            
            # 查询起量状态
            rising_info = self.check_rising_status(
                game_name=game_name,
                platform=st_platform
            )
            
            game['rising_info'] = rising_info
            results.append(game)
        
        return results
```

---

### 阶段五：主工作流

#### 5.1 创建异动分析主程序

**文件：`scripts/tools/analyze_ranking_anomalies.py`**

```python
"""
榜单异动分析主程序
完整流程：数据汇总 → 异动检测 → 玩法解析 → 起量查询 → 报告生成
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
from datetime import datetime, timedelta
from modules.ranking_aggregator import RankingAggregator
from modules.anomaly_game_analyzer import AnomalyGameAnalyzer
from modules.rising_apps_checker import RisingAppsChecker
from modules.report_generator import ReportGenerator
from modules.feishu_sender import FeishuSender
import config


def main():
    parser = argparse.ArgumentParser(description='榜单异动游戏分析')
    parser.add_argument('--date', type=str, help='分析日期（YYYY-MM-DD），默认今天')
    parser.add_argument('--previous-date', type=str, help='对比日期，默认7天前')
    parser.add_argument('--max-games', type=int, help='最大分析游戏数量')
    parser.add_argument('--skip-rising-check', action='store_true', help='跳过起量查询')
    parser.add_argument('--send-to', type=str, choices=['feishu', 'wecom', 'sheets', 'all'], 
                       default='feishu', help='发送目标')
    
    args = parser.parse_args()
    
    # 确定日期
    if args.date:
        current_date = args.date
    else:
        current_date = datetime.now().strftime('%Y-%m-%d')
    
    if args.previous_date:
        previous_date = args.previous_date
    else:
        previous_date = (datetime.strptime(current_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')
    
    print("=" * 60)
    print("榜单异动游戏分析")
    print("=" * 60)
    print(f"当前日期: {current_date}")
    print(f"对比日期: {previous_date}")
    print()
    
    # 步骤1: 数据汇总
    print("【步骤1】汇总榜单数据...")
    aggregator = RankingAggregator()
    
    # 汇总引力引擎数据
    gravity_data = aggregator.aggregate_gravity_rankings(current_date)
    print(f"  引力引擎: {len(gravity_data)} 个游戏")
    
    # 汇总 SensorTower 数据（如果配置了 API）
    sensortower_data = []
    if hasattr(config, 'SENSORTOWER_API_TOKEN') and config.SENSORTOWER_API_TOKEN:
        sensortower_data = aggregator.aggregate_sensortower_rankings(current_date)
        print(f"  SensorTower: {len(sensortower_data)} 个游戏")
    
    # 保存快照
    aggregator.save_ranking_snapshot(gravity_data + sensortower_data, current_date)
    
    # 步骤2: 异动检测和玩法解析
    print("\n【步骤2】检测异动并分析玩法...")
    analyzer = AnomalyGameAnalyzer()
    analysis_results = analyzer.analyze_anomaly_games(
        current_date=current_date,
        previous_date=previous_date,
        max_games=args.max_games
    )
    
    if not analysis_results:
        print("未发现异动游戏，流程结束")
        return
    
    print(f"\n完成 {len(analysis_results)} 个游戏的玩法分析")
    
    # 步骤3: 起量查询
    if not args.skip_rising_check:
        print("\n【步骤3】查询起量情况...")
        rising_checker = RisingAppsChecker()
        analysis_results = rising_checker.batch_check_rising_status(analysis_results)
        
        # 统计起量情况
        rising_count = sum(1 for r in analysis_results if r.get('rising_info'))
        print(f"  发现 {rising_count} 个游戏有起量情况")
    
    # 步骤4: 生成报告
    print("\n【步骤4】生成报告...")
    report_generator = ReportGenerator()
    
    # 转换为标准分析格式
    standard_analyses = []
    for result in analysis_results:
        anomaly = result['anomaly_info']
        standard_analyses.append({
            'game_name': result['game_name'],
            'analysis': result.get('analysis', ''),
            'analysis_data': result.get('analysis_data', {}),
            'game_rank': str(anomaly.get('current_rank', '')),
            'game_company': anomaly.get('company', ''),
            'rank_change': anomaly.get('change_value', ''),
            'monitor_date': current_date,
            'platform': anomaly.get('platform', ''),
            'source': anomaly.get('source', ''),
            'board_name': '',
            'gdrive_url': result.get('video_url', ''),
            'anomaly_type': anomaly.get('anomaly_type', ''),
            'rising_info': result.get('rising_info'),
        })
    
    # 生成飞书格式报告
    feishu_report = report_generator.generate_feishu_format(standard_analyses)
    
    # 步骤5: 发送报告
    if args.send_to in ['feishu', 'all']:
        print("\n【步骤5】发送到飞书...")
        feishu_sender = FeishuSender()
        feishu_sender.send_card(feishu_report)
    
    if args.send_to in ['sheets', 'all']:
        print("\n【步骤5】写入到 Google Sheets...")
        # TODO: 实现写入 Google Sheets
    
    print("\n" + "=" * 60)
    print("分析完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
```

---

## 📊 报告格式设计

### 异动游戏报告（飞书卡片）

```
📊 榜单异动游戏分析报告
日期：2026-01-26

【新进榜游戏】
1. 游戏A（微信小游戏）
   - 排名：新进 #15
   - 开发公司：公司A
   - 玩法解析：[核心玩法描述]
   - 起量情况：✅ iOS 日均下载 8000（2026-01-20起量）

2. 游戏B（抖音小游戏）
   - 排名：新进 #8
   - 开发公司：公司B
   - 玩法解析：[核心玩法描述]
   - 起量情况：❌ 未发现起量

【排名飙升游戏】
1. 游戏C（iOS）
   - 排名变化：↑25 (#45 → #20)
   - 开发公司：公司C
   - 玩法解析：[核心玩法描述]
   - 起量情况：✅ Android 日均下载 12000（2026-01-18起量）
```

---

## ⚙️ 配置参数

### config.py 新增配置

```python
# 榜单异动分析配置
RANKING_ANOMALY_ANALYSIS = {
    # 排名变化阈值
    'rank_change_threshold': {
        '微信小游戏': 15,
        '抖音小游戏': 15,
        'iOS': 20,
        'Android': 20,
    },
    
    # 新进榜 Top N
    'new_entry_top_n': {
        '微信小游戏': 50,
        '抖音小游戏': 50,
        'iOS': 50,
        'Android': 50,
    },
    
    # 起量阈值
    'download_threshold': 5000,  # 日均下载量
}

# SensorTower API 配置
SENSORTOWER_API_TOKEN = os.getenv("SENSORTOWER_API_TOKEN", "")
```

---

## 🚀 实施步骤

### Phase 1: 数据汇总（1周）
1. ✅ 实现 RankingAggregator 模块
2. ✅ 实现引力引擎数据汇总
3. ✅ 实现 SensorTower API 客户端（基础）
4. ✅ 实现数据快照存储

### Phase 2: 异动检测（1周）
1. ✅ 实现 AnomalyDetector 模块
2. ✅ 实现排名对比逻辑
3. ✅ 实现异动类型判断
4. ✅ 测试异动检测准确性

### Phase 3: 玩法解析集成（1周）
1. ✅ 实现 AnomalyGameAnalyzer 模块
2. ✅ 集成现有视频搜索和分析功能
3. ✅ 优化分析流程
4. ✅ 测试完整流程

### Phase 4: 起量查询（1周）
1. ✅ 完善 SensorTower API 客户端
2. ✅ 实现起量查询逻辑
3. ✅ 实现批量查询
4. ✅ 测试起量数据准确性

### Phase 5: 报告和集成（1周）
1. ✅ 实现报告生成
2. ✅ 集成到主工作流
3. ✅ 添加定时任务
4. ✅ 文档和测试

---

## 📝 使用示例

### 命令行使用

```bash
# 分析今天的异动游戏（对比7天前）
python scripts/tools/analyze_ranking_anomalies.py

# 分析指定日期
python scripts/tools/analyze_ranking_anomalies.py --date 2026-01-26

# 只分析前10个异动游戏
python scripts/tools/analyze_ranking_anomalies.py --max-games 10

# 跳过起量查询（加快速度）
python scripts/tools/analyze_ranking_anomalies.py --skip-rising-check

# 发送到所有目标
python scripts/tools/analyze_ranking_anomalies.py --send-to all
```

### 集成到主工作流

在 `main.py` 中添加新的步骤：

```python
def step6_analyze_anomalies(self, analyses: List[Dict]) -> List[Dict]:
    """步骤6：分析榜单异动游戏"""
    from modules.anomaly_game_analyzer import AnomalyGameAnalyzer
    
    analyzer = AnomalyGameAnalyzer()
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    anomaly_results = analyzer.analyze_anomaly_games(
        current_date=current_date,
        max_games=10
    )
    
    return anomaly_results
```

---

## ⚠️ 注意事项

1. **数据一致性**：
   - 确保榜单数据的日期对齐
   - 处理时区问题

2. **API 限制**：
   - SensorTower API 有调用频率限制
   - 需要合理设计批量查询策略

3. **游戏名称匹配**：
   - 不同平台的游戏名称可能不同
   - 需要建立名称映射机制

4. **性能优化**：
   - 玩法解析比较耗时，建议异步处理
   - 起量查询可以批量进行

5. **数据存储**：
   - 历史榜单数据会快速增长
   - 需要设计数据归档策略
