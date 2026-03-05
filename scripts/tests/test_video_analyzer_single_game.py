"""
从数据库中挑一款「已有视频 URL」的游戏，单独调用 VideoAnalyzer 做一次 Gemini 玩法分析，
用于复现 / 排查「带视频时 OpenRouter 报错」的问题。

运行方式（在项目根目录）：

    python scripts/tests/test_video_analyzer_single_game.py

注意：
- 依赖配置：OPENROUTER_API_KEY、VIDEO_ANALYSIS_MODEL、data/videos.db
- 该脚本会强制使用 force_refresh=True，忽略已有玩法缓存。
"""

import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.video_analyzer import VideoAnalyzer  # noqa: E402
from modules.database import VideoDatabase       # noqa: E402
import config                                    # noqa: E402


def pick_one_game_with_video(db_path: Path):
    """从 games 表中选出一条带视频 URL 的游戏记录。"""
    if not db_path.exists():
        print(f"ERROR: 数据库文件不存在：{db_path}")
        return None

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    # 优先选有 gdrive_url 的，其次 original_video_url，最后 video_url
    cur.execute(
        """
        SELECT game_name, gdrive_url, original_video_url, video_url
        FROM games
        WHERE
            (gdrive_url IS NOT NULL AND gdrive_url != '')
         OR (original_video_url IS NOT NULL AND original_video_url != '')
         OR (video_url IS NOT NULL AND video_url != '')
        ORDER BY updated_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        print("ERROR: 数据库中未找到任何带视频 URL 的游戏记录。")
        return None

    game_name, gdrive_url, original_video_url, video_url = row
    # 选择优先级：gdrive_url > original_video_url > video_url
    url = gdrive_url or original_video_url or video_url
    return {
        "game_name": game_name,
        "video_url": url,
        "gdrive_url": gdrive_url,
        "original_video_url": original_video_url,
        "raw_video_url": video_url,
    }


def main() -> None:
    # 使用与主流程一致的数据库路径
    db = VideoDatabase()
    db_path = Path(db.db_path)
    print(f"使用数据库：{db_path}")

    picked = pick_one_game_with_video(db_path)
    if not picked:
        return

    game_name = picked["game_name"]
    video_url = picked["video_url"]
    print(f"\n选中的游戏：{game_name}")
    print(f"  gdrive_url         : {picked['gdrive_url'] or '<空>'}")
    print(f"  original_video_url : {picked['original_video_url'] or '<空>'}")
    print(f"  video_url          : {picked['raw_video_url'] or '<空>'}")
    print(f"→ 实际用于分析的 URL：{video_url}")

    # 从数据库取完整 game_info
    game_info = db.get_game(game_name) or {}

    # 初始化视频分析器（使用与主流程相同的模型 / Key）
    analyzer = VideoAnalyzer(
        api_key=config.OPENROUTER_API_KEY,
        model=config.VIDEO_ANALYSIS_MODEL,
        use_database=True,
    )

    print("\n===== 开始单次 Gemini 视频分析测试 =====")
    try:
        result = analyzer.analyze_video(
            video_path=None,
            game_name=game_name,
            game_info=game_info,
            video_url=video_url,
            force_refresh=True,  # 强制重算，忽略缓存
        )
    except Exception as e:
        print(f"\n分析函数抛出了未捕获异常：{e!r}")
        import traceback

        traceback.print_exc()
        return

    if not result:
        print("\n分析结果为空（None）。")
        return

    status = result.get("status", "<无 status 字段>")
    print(f"\n分析完成，status = {status}")

    analysis_text = result.get("analysis")
    if analysis_text:
        preview = analysis_text[:600].replace("\n", " ")
        print(f"\nanalysis 文本前 600 字符：\n{preview}")
    else:
        print("\nanalysis 字段为空。")

    analysis_data = result.get("analysis_data")
    if analysis_data:
        import json

        print("\nanalysis_data 结构预览：")
        print(json.dumps(analysis_data, ensure_ascii=False, indent=2)[:800])
    else:
        print("\nanalysis_data 字段为空（可能是 text_only 或 mock）。")


if __name__ == "__main__":
    main()

