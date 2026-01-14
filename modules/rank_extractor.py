"""
排行提取模块
从CSV文件中提取游戏排行榜信息
"""
import pandas as pd
from typing import List, Dict
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
    
    def extract_rankings(self, limit: int = None) -> List[Dict]:
        """
        提取游戏排行榜
        
        Args:
            limit: 限制提取的游戏数量，None表示提取全部
        
        Returns:
            游戏排行榜列表，每个游戏包含排名、名称、类型等信息
        """
        try:
            df = pd.read_csv(self.csv_path, encoding='utf-8')
            
            # 转换为字典列表
            games = df.to_dict('records')
            
            # 如果指定了限制，只返回前N个
            if limit:
                games = games[:limit]
            
            print(f"成功提取 {len(games)} 个游戏信息")
            return games
            
        except FileNotFoundError:
            print(f"错误：找不到文件 {self.csv_path}")
            return []
        except Exception as e:
            print(f"提取排行榜时发生错误：{str(e)}")
            return []
    
    def get_top_games(self, top_n: int = 5) -> List[Dict]:
        """
        获取前N名游戏
        
        Args:
            top_n: 前N名
        
        Returns:
            前N名游戏列表
        """
        return self.extract_rankings(limit=top_n)