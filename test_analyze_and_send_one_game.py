"""
一键测试：任选一个游戏（有视频URL）→ 清除数据库玩法缓存 → 用新提示词重跑分析 → 发送到飞书 + 企业微信

流程对齐“原工作流”：
- 玩法缓存：VideoDatabase.clear_gameplay_analysis()
- 视频分析：VideoAnalyzer.analyze_video(..., force_refresh=True)
- 飞书：ReportGenerator.generate_feishu_format() + FeishuSender.send_card()
- 企业微信：复用 send_step5_to_wecom.py 的解析/分段/图片下载/发送逻辑

用法：
  python test_analyze_and_send_one_game.py
  python test_analyze_and_send_one_game.py --game "羊了个羊：星球"
  python test_analyze_and_send_one_game.py --wecom-webhook real
  python test_analyze_and_send_one_game.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import config
from modules.database import VideoDatabase
from modules.feishu_sender import FeishuSender
from modules.report_generator import ReportGenerator
from modules.video_analyzer import VideoAnalyzer


def _pick_game_and_url(db: VideoDatabase, prefer_game: str = "") -> Tuple[str, str, Dict]:
    """
    返回 (game_name, video_url, db_row)
    video_url 优先级：gdrive_url > original_video_url > video_url
    """
    prefer_game = (prefer_game or "").strip()

    if prefer_game:
        row = db.get_game(prefer_game)
        if row:
            url = row.get("gdrive_url") or row.get("original_video_url") or row.get("video_url")
            if url:
                return prefer_game, url, row

    # 兜底：从库里找任意一个有URL的
    games = db.get_all_games(limit=None) or []
    for row in games:
        name = (row.get("game_name") or "").strip()
        if not name:
            continue
        url = row.get("gdrive_url") or row.get("original_video_url") or row.get("video_url")
        if url:
            return name, url, row

    raise RuntimeError("数据库中找不到任何带视频URL的游戏（gdrive_url/original_video_url/video_url 均为空）")


def _analysis_from_db_row(game_name: str, video_url: str, row: Dict, analysis_result: Dict) -> Dict:
    """组装成 ReportGenerator 期望的 analysis dict"""
    analysis_data = analysis_result.get("analysis_data")
    analysis_text = analysis_result.get("analysis") or ""
    model_used = analysis_result.get("model_used") or "unknown"
    status = analysis_result.get("status") or "success"

    out: Dict = {
        "game_name": game_name,
        "analysis": analysis_text,
        "analysis_data": analysis_data,
        "model_used": model_used,
        "status": status,
        # 这些字段会被标题/卡片使用
        "game_rank": row.get("game_rank") or "",
        "game_company": row.get("game_company") or "",
        "rank_change": row.get("rank_change") or "--",
        "platform": row.get("platform") or "",
        "source": row.get("source") or "",
        "board_name": row.get("board_name") or "",
        "monitor_date": row.get("monitor_date") or "",
        "gdrive_url": video_url,  # 让“视频链接”可点击
    }

    return out


def _wecom_webhook_from_args(args) -> str:
    if args.wecom_webhook_url:
        return args.wecom_webhook_url.strip()
    if args.wecom_webhook == "real":
        return (os.getenv("WECOM_WEBHOOK_URL_REAL") or config.WECOM_WEBHOOK_URL_REAL or "").strip()
    return (os.getenv("WECOM_WEBHOOK_URL") or config.WECOM_WEBHOOK_URL or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="一键：清缓存→重跑视频分析→发送飞书+企微（单游戏）")
    ap.add_argument("--game", default="", help="指定测试的游戏名称（可选；不填则自动从DB挑一个有视频URL的）")
    ap.add_argument("--video-url", default="", help="手动指定视频URL（可选；不填则从DB取）")
    ap.add_argument("--dry-run", action="store_true", help="只生成文件并打印，不实际发送")
    ap.add_argument("--skip-feishu", action="store_true", help="不发送飞书")
    ap.add_argument("--skip-wecom", action="store_true", help="不发送企业微信")

    # 企业微信参数（对齐 send_step5_to_wecom.py）
    ap.add_argument("--wecom-webhook", choices=["default", "real"], default="default", help="选择企业微信 webhook")
    ap.add_argument("--wecom-webhook-url", default="", help="直接指定企业微信 webhook URL（优先级最高）")
    ap.add_argument("--max-text-len", type=int, default=3800, help="企业微信每条文本最大字符数")
    ap.add_argument("--min-interval", type=float, default=3.2, help="企业微信发送间隔秒数")
    ap.add_argument("--max-retries", type=int, default=3, help="企业微信频率限制重试次数")
    ap.add_argument("--skip-header", action="store_true", help="企业微信不发头部摘要（测试常用）")

    args = ap.parse_args()

    db = VideoDatabase()
    game_name, db_video_url, row = _pick_game_and_url(db, prefer_game=args.game)
    video_url = (args.video_url or "").strip() or db_video_url

    # 1) 清除玩法缓存
    db.clear_gameplay_analysis(game_name)

    # 2) 强制重跑分析（使用新提示词）
    analyzer = VideoAnalyzer(use_database=True)
    game_info = {"游戏名称": game_name, "游戏类型": "未知"}  # 不强依赖；如果你希望，可再从CSV补齐
    analysis_result = analyzer.analyze_video(
        game_name=game_name,
        game_info=game_info,
        video_url=video_url,
        force_refresh=True,
    )
    if not analysis_result:
        print("分析失败：analysis_result is None")
        return 1

    # 3) 生成 step5 卡片
    analysis = _analysis_from_db_row(game_name, video_url, row, analysis_result)
    rg = ReportGenerator()
    step5 = rg.generate_feishu_format([analysis])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_test = Path("data") / f"test_innovation_prompt_{game_name}_{ts}.json"
    out_step5 = Path("data") / f"step5_feishu_card_test_{ts}.json"
    out_test.parent.mkdir(parents=True, exist_ok=True)
    out_test.write_text(json.dumps(analysis_result, ensure_ascii=False, indent=2), encoding="utf-8")
    out_step5.write_text(json.dumps(step5, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已保存测试分析：{out_test}")
    print(f"✅ 已生成 step5：{out_step5}")

    # 4) 发送飞书
    if not args.skip_feishu:
        if args.dry_run:
            print("[dry-run] 跳过飞书实际发送")
        else:
            fs = FeishuSender()
            ok = fs.send_card(step5)
            print("✅ 飞书发送成功" if ok else "❌ 飞书发送失败（请检查 FEISHU_WEBHOOK_URL）")

    # 5) 发送企业微信（复用 send_step5_to_wecom 的逻辑）
    if args.skip_wecom:
        return 0
    if args.dry_run:
        print("[dry-run] 跳过企业微信实际发送")
        return 0

    wecom_webhook = _wecom_webhook_from_args(args)
    if not wecom_webhook:
        print("错误：未配置企业微信 webhook（WECOM_WEBHOOK_URL / WECOM_WEBHOOK_URL_REAL）")
        return 1

    from modules.wecom_sender import WeComSender
    from send_step5_to_wecom import chunk_text, extract_sections_from_step5

    sender = WeComSender(
        wecom_webhook,
        min_interval_seconds=args.min_interval,
        max_retries=args.max_retries,
        retry_base_seconds=15.0,
    )

    header_text, games = extract_sections_from_step5(step5)
    if header_text and not args.skip_header:
        for c in chunk_text(header_text, args.max_text_len):
            sender.send_markdown(c)

    for g in games:
        merged = g.merged_text()
        for c in chunk_text(merged, args.max_text_len):
            sender.send_markdown(c)

    print("✅ 企业微信发送完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

