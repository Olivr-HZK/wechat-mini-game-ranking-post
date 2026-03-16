"""
清除数据库中某个游戏的“玩法分析缓存”（gameplay_analysis / analysis_model / analyzed_at）

用法：
  python clear_gameplay_analysis_for_game.py --game "羊了个羊：星球"
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from __future__ import annotations

import argparse

from modules.database import VideoDatabase


def main() -> int:
    ap = argparse.ArgumentParser(description="清除指定游戏的玩法分析缓存（不影响视频等其他数据）")
    ap.add_argument("--game", type=str, required=True, help="游戏名称（与数据库一致）")
    args = ap.parse_args()

    game_name = (args.game or "").strip()
    if not game_name:
        print("错误：--game 不能为空")
        return 1

    db = VideoDatabase()
    affected = db.clear_gameplay_analysis(game_name)
    return 0 if affected >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

