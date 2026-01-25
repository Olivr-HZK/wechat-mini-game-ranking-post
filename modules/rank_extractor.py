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
    
    def __init__(self, csv_path: str = None):
        """
        初始化排行榜提取器
        
        Args:
            csv_path: CSV文件路径，默认使用配置文件中的路径
        """
        self.csv_path = csv_path or config.RANKINGS_CSV_PATH
        self._effective_csv_path: Optional[str] = None

    def get_effective_csv_path(self) -> str:
        """
        返回实际要读取的CSV文件路径。
        - 如果 self.csv_path 是文件：直接返回
        - 如果 self.csv_path 是目录：选择目录下最新的 *.csv
        """
        if self._effective_csv_path and os.path.isfile(self._effective_csv_path):
            return self._effective_csv_path

        p = Path(self.csv_path)

        if p.exists() and p.is_file():
            self._effective_csv_path = str(p)
            return self._effective_csv_path

        if p.exists() and p.is_dir():
            csv_files = list(p.glob("*.csv"))
            if csv_files:
                csv_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                self._effective_csv_path = str(csv_files[0])
                return self._effective_csv_path

        # 兜底：默认尝试 data/人气榜
        fallback_dir = Path("data") / "人气榜"
        if fallback_dir.exists() and fallback_dir.is_dir():
            csv_files = list(fallback_dir.glob("*.csv"))
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