"""
排行提取模块
从CSV文件中提取游戏排行榜信息

支持两种输入：
- CSV文件路径
- 目录路径：自动选择目录下“最新修改时间”的 .csv 文件（例如 data/人气榜）
"""

import os
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd

import config


class RankExtractor:
    """游戏排行榜提取器"""
    
    def __init__(self, csv_path: str = None, platform: str = None):
        """
        初始化排行榜提取器
        
        Args:
            csv_path: CSV文件路径，默认使用配置文件中的路径
            platform: 平台类型，'dy'表示抖音，'wx'表示微信小游戏，None表示不限制（选择最新的）
        """
        self.csv_path = csv_path or config.RANKINGS_CSV_PATH
        self.platform = platform  # 'dy' 或 'wx' 或 None
        self._effective_csv_path: Optional[str] = None

    def get_effective_csv_path(self) -> str:
        """
        返回实际要读取的CSV文件路径。
        - 如果 self.csv_path 是文件：直接返回
        - 如果 self.csv_path 是目录：递归查找子目录，根据platform参数选择对应的CSV文件
          - platform='dy': 选择以 'dy_' 开头的CSV文件（抖音），包括 dy_anomalies.csv
          - platform='wx': 选择不以 'dy_' 开头且不是 'sensortower_' 开头的文件（微信小游戏），如 wx_anomalies.csv
          - platform=None: 选择目录下最新的 *.csv（不限制平台）
        """
        if self._effective_csv_path and os.path.isfile(self._effective_csv_path):
            return self._effective_csv_path

        p = Path(self.csv_path)

        if p.exists() and p.is_file():
            self._effective_csv_path = str(p)
            return self._effective_csv_path

        if p.exists() and p.is_dir():
            # 递归查找所有子目录中的CSV文件
            csv_files = list(p.rglob("*.csv"))
            if csv_files:
                # 根据platform参数过滤文件
                if self.platform == 'dy':
                    # 选择以 'dy_' 开头的文件（抖音），包括 dy_anomalies.csv
                    csv_files = [f for f in csv_files if f.name.startswith('dy_')]
                elif self.platform == 'wx':
                    # 选择不以 'dy_' 和 'sensortower_' 开头的文件（微信小游戏），如 wx_anomalies.csv
                    csv_files = [f for f in csv_files if not f.name.startswith('dy_') and not f.name.startswith('sensortower_')]
                # 如果platform为None，不进行过滤，选择所有文件中最新的
                
                if csv_files:
                    csv_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    self._effective_csv_path = str(csv_files[0])
                    return self._effective_csv_path

        # 兜底：默认尝试 data/人气榜（递归查找）
        fallback_dir = Path("data") / "人气榜"
        if fallback_dir.exists() and fallback_dir.is_dir():
            csv_files = list(fallback_dir.rglob("*.csv"))
            if csv_files:
                # 根据platform参数过滤文件
                if self.platform == 'dy':
                    csv_files = [f for f in csv_files if f.name.startswith('dy_')]
                elif self.platform == 'wx':
                    csv_files = [f for f in csv_files if not f.name.startswith('dy_') and not f.name.startswith('sensortower_')]
                
                if csv_files:
                    csv_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    self._effective_csv_path = str(csv_files[0])
                    return self._effective_csv_path

        self._effective_csv_path = str(Path("data") / "game_rankings.csv")
        return self._effective_csv_path
    
    def extract_rankings(self, limit: int = None) -> List[Dict]:
        """
        提取游戏排行榜
        
        Args:
            limit: 限制提取的游戏数量，None表示提取全部
        
        Returns:
            游戏排行榜列表，每个游戏包含排名、名称、类型等信息
        """
        try:
            csv_path = self.get_effective_csv_path()
            # 尝试多种编码格式
            encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
            df = None
            
            for encoding in encodings:
                try:
                    df = pd.read_csv(csv_path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if df is None:
                raise Exception("无法使用任何编码格式读取CSV文件")
            
            # 转换为字典列表
            games = df.to_dict('records')
            
            # 如果指定了限制，只返回前N个
            if limit:
                games = games[:limit]
            
            print(f"成功提取 {len(games)} 个游戏信息")
            return games
            
        except FileNotFoundError:
            print(f"错误：找不到文件 {self.get_effective_csv_path()}")
            print(f"  提示：请先运行爬取步骤或确保CSV文件存在")
            return []
        except Exception as e:
            print(f"提取排行榜时发生错误：{str(e)}")
            return []
    
    def get_top_games(self, top_n: int = None) -> List[Dict]:
        """
        获取前N名游戏
        
        Args:
            top_n: 前N名，如果为None则返回所有游戏
        
        Returns:
            游戏列表
        """
        return self.extract_rankings(limit=top_n)
    
    def extract_all_platforms_rankings(self, limit: int = None) -> List[Dict]:
        """
        提取 dy/wx 平台的排行榜并汇总（仅微信小游戏、抖音小游戏，不包含 SensorTower）
        
        Args:
            limit: 限制每个平台提取的游戏数量，None表示提取全部
        
        Returns:
            汇总后的游戏列表（按游戏名称去重，合并各平台排名）
        """
        p = Path(self.csv_path)
        
        # 如果指定的是文件，直接读取
        if p.exists() and p.is_file():
            return self.extract_rankings(limit=limit)
        
        # 如果是目录，仅查找 dy/wx 的 CSV 文件（不读取 SensorTower）
        base_dir = p if p.exists() and p.is_dir() else Path("data") / "人气榜"
        
        if not base_dir.exists() or not base_dir.is_dir():
            print(f"错误：目录不存在：{base_dir}")
            return []
        
        # 仅 dy、wx 异动文件
        all_csv_files = list(base_dir.rglob("*.csv"))
        wx_files = [f for f in all_csv_files if f.name == "wx_anomalies.csv" or (f.name.startswith("wx_") and f.name != "wx_anomalies.csv")]
        dy_files = [f for f in all_csv_files if f.name == "dy_anomalies.csv" or (f.name.startswith("dy_") and f.name != "dy_anomalies.csv")]
        
        wx_file = next((f for f in all_csv_files if f.name == "wx_anomalies.csv"), None) or (max(wx_files, key=lambda x: x.stat().st_mtime) if wx_files else None)
        dy_file = next((f for f in all_csv_files if f.name == "dy_anomalies.csv"), None) or (max(dy_files, key=lambda x: x.stat().st_mtime) if dy_files else None)
        
        all_games = {}  # 微信/抖音按游戏名称去重合并
        
        # 微信：完整人气榜异动榜单（不限制条数）
        if wx_file:
            try:
                print(f"读取微信小游戏榜单（完整异动）：{wx_file}")
                games = self._read_csv_file(wx_file, limit=None)
                for game in games:
                    game_name = game.get("游戏名称", "").strip()
                    if game_name:
                        if game_name not in all_games:
                            all_games[game_name] = game.copy()
                        all_games[game_name]["rank_wx"] = game.get("排名")
                        all_games[game_name]["platform_wx"] = game.get("平台")
                        all_games[game_name]["source_wx"] = game.get("来源")
            except Exception as e:
                print(f"读取微信小游戏榜单失败：{e}")
        
        # 抖音：完整人气榜异动榜单（不限制条数）
        if dy_file:
            try:
                print(f"读取抖音小游戏榜单（完整异动）：{dy_file}")
                games = self._read_csv_file(dy_file, limit=None)
                for game in games:
                    game_name = game.get("游戏名称", "").strip()
                    if game_name:
                        if game_name not in all_games:
                            all_games[game_name] = game.copy()
                        all_games[game_name]["rank_dy"] = game.get("排名")
                        all_games[game_name]["platform_dy"] = game.get("平台")
                        all_games[game_name]["source_dy"] = game.get("来源")
            except Exception as e:
                print(f"读取抖音小游戏榜单失败：{e}")
        
        # 仅返回 dy/wx 合并列表（不包含 SensorTower）
        result = list(all_games.values())
        print(f"汇总完成：共 {len(result)} 个游戏（仅微信+抖音）")
        return result
    
    def _read_csv_file(self, csv_path: Path, limit: int = None) -> List[Dict]:
        """
        读取单个CSV文件
        
        Args:
            csv_path: CSV文件路径
            limit: 限制提取的游戏数量
        
        Returns:
            游戏列表
        """
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
        df = None
        
        for encoding in encodings:
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if df is None:
            raise Exception(f"无法使用任何编码格式读取CSV文件：{csv_path}")
        
        games = df.to_dict('records')
        
        if limit:
            games = games[:limit]
        
        return games