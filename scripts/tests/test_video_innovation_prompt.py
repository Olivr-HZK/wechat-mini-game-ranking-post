"""
测试“视频分析新提示词（聚焦品类创新点）”

只跑 1 个游戏 + 1 个视频：
- 优先使用命令行指定的 --video-url
- 否则从数据库 data/videos.db 里按 game_name 取 gdrive_url/original_video_url/video_url

用法示例：
  python test_video_innovation_prompt.py --game "羊了个羊：星球" --csv "data/人气榜/2026-1-12~2026-1-18.csv"
  python test_video_innovation_prompt.py --game "羊了个羊：星球" --video-url "https://..."
  python test_video_innovation_prompt.py --game "羊了个羊：星球" --clear-cache
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from modules.rank_extractor import RankExtractor
from modules.video_analyzer import VideoAnalyzer


def _sanitize_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[\\/:*?\"<>|]", "_", s)
    s = re.sub(r"\s+", "_", s)
    return s[:80] or "game"


def _load_game_info_from_csv(csv_path: Optional[str], game_name: str) -> Dict:
    if not csv_path:
        return {"游戏名称": game_name, "游戏类型": "未知"}

    extractor = RankExtractor(csv_path=csv_path)
    games = extractor.get_top_games(top_n=None) or []
    for row in games:
        if str(row.get("游戏名称", "")).strip() == game_name:
            row = dict(row)
            row.setdefault("游戏名称", game_name)
            row.setdefault("游戏类型", row.get("游戏类型") or "未知")
            return row
    # 找不到就兜底
    return {"游戏名称": game_name, "游戏类型": "未知"}


def _get_video_url_from_db(game_name: str) -> Optional[str]:
    try:
        from modules.database import VideoDatabase

        db = VideoDatabase()
        g = db.get_game(game_name) or {}
        return g.get("gdrive_url") or g.get("original_video_url") or g.get("video_url")
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="测试：聚焦品类创新点的视频分析提示词（单游戏单视频）")
    ap.add_argument("--game", type=str, required=True, help="游戏名称（必须与数据库/CSV一致）")
    ap.add_argument("--csv", type=str, default="", help="排行榜CSV路径（用于提供游戏类型等信息，可选）")
    ap.add_argument("--video-url", type=str, default="", help="视频URL（可选；不填则从数据库取）")
    ap.add_argument("--clear-cache", action="store_true", help="先清除该游戏在数据库中的玩法分析缓存（gameplay_analysis）")
    ap.add_argument("--use-cache", action="store_true", help="允许直接读取数据库缓存（默认关闭：默认会强制重新分析）")
    ap.add_argument("--output", type=str, default="", help="输出JSON文件路径（可选）")
    args = ap.parse_args()

    game_name = args.game.strip()
    if not game_name:
        print("错误：--game 不能为空")
        return 1

    video_url = (args.video_url or "").strip() or _get_video_url_from_db(game_name)
    if not video_url:
        print("错误：未提供 --video-url 且数据库中找不到该游戏的视频URL（gdrive_url/original_video_url/video_url）")
        print("请先跑 step2 下载/入库视频，或手动传 --video-url")
        return 1

    game_info = _load_game_info_from_csv((args.csv or "").strip() or None, game_name)

    # 测试默认：使用数据库（便于取URL/写回结果），但强制刷新以确保用到“新提示词”
    analyzer = VideoAnalyzer(use_database=True)
    force_refresh = not bool(args.use_cache)

    if args.clear_cache:
        try:
            from modules.database import VideoDatabase

            db = VideoDatabase()
            db.clear_gameplay_analysis(game_name)
        except Exception as e:
            print(f"清除缓存失败：{e}")
            return 1

    print("=" * 60)
    print("单视频分析测试（创新点提示词）")
    print("=" * 60)
    print(f"游戏：{game_name}")
    print(f"类型：{game_info.get('游戏类型', '未知')}")
    print(f"视频URL：{video_url}")
    print(f"模型：{analyzer.model}")
    print(f"数据库缓存读取：{'启用' if args.use_cache else '关闭（强制重新分析）'}")
    print()

    result = analyzer.analyze_video(
        game_name=game_name,
        game_info=game_info,
        video_url=video_url,
        force_refresh=force_refresh,
    )

    if not result:
        print("分析失败：result is None")
        return 1

    analysis_data = result.get("analysis_data")
    print("\n" + "-" * 60)
    print("结构化JSON（analysis_data）")
    print("-" * 60)
    if isinstance(analysis_data, dict):
        print(json.dumps(analysis_data, ensure_ascii=False, indent=2))
    else:
        print("（未解析到JSON，返回了纯文本）")

    # 保存
    out = (args.output or "").strip()
    if not out:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = str(Path("data") / f"test_innovation_prompt_{_sanitize_filename(game_name)}_{ts}.json")

    try:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "game_name": game_name,
            "video_url": video_url,
            "game_info": game_info,
            "model_used": result.get("model_used"),
            "status": result.get("status"),
            "analysis": result.get("analysis"),
            "analysis_data": analysis_data,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已保存：{os.path.abspath(out)}")
    except Exception as e:
        print(f"\n保存失败：{e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

