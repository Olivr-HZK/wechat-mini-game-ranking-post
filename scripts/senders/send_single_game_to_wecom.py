"""
单独发送【一个游戏】的报告到企业微信（群机器人 Webhook）。

复用 step5 飞书卡片（step5_feishu_card_*.json）作为输入：
- 自动选择 data 下最新的 step5 文件（也可 --input 指定）
- 支持按“游戏序号”或“游戏名称”选择单个游戏
- 默认只发文字（不发图片）；如需中间截图可加 --send-image

用法：
  python send_single_game_to_wecom.py --only-game 3
  python send_single_game_to_wecom.py --only-name "羊了个羊：星球"
  python send_single_game_to_wecom.py --input data/step5_feishu_card_20260121_104623.json --only-game 1
  python send_single_game_to_wecom.py --only-game 1 --webhook real
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Tuple

import config
from modules.wecom_sender import WeComSender

# 复用已有逻辑：切块、解析卡片为“游戏段落”、（可选）下载中间截图
from send_step5_to_wecom import (  # noqa: E402
    GameSection,
    chunk_text,
    download_feishu_image_bytes,
    extract_sections_from_step5,
    get_feishu_tenant_access_token,
)


def _pick_latest_step5() -> Optional[Path]:
    data_dir = Path("data")
    patterns = ["step5_feishu_card_*.json", "step5_feishu_card_test_*.json"]
    files = []
    for p in patterns:
        files.extend(list(data_dir.glob(p)))
    if not files:
        return None
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files[0]


def _resolve_input_path(p: str, latest: bool) -> Path:
    if p and p.strip():
        return Path(p.strip())
    if latest:
        f = _pick_latest_step5()
        if f:
            return f
    f = _pick_latest_step5()
    if f:
        return f
    raise SystemExit("未找到 step5_feishu_card_*.json（请先生成 step5，或用 --input 指定文件）")


def _select_game(games: list[GameSection], only_game: int, only_name: str) -> GameSection:
    if only_game and only_game > 0:
        for g in games:
            if g.index == only_game:
                return g
        raise SystemExit(f"未找到要发送的游戏序号：{only_game}")

    name = (only_name or "").strip()
    if name:
        # 优先精确匹配，其次包含匹配
        for g in games:
            if g.name.strip() == name:
                return g
        for g in games:
            if name in g.name:
                return g
        raise SystemExit(f"未找到要发送的游戏名称：{name}")

    raise SystemExit("请指定 --only-game 或 --only-name")


def _resolve_wecom_webhook(args) -> str:
    if args.webhook_url:
        return args.webhook_url.strip()
    if args.webhook == "real":
        return (os.getenv("WECOM_WEBHOOK_URL_REAL") or config.WECOM_WEBHOOK_URL_REAL or "").strip()
    return (os.getenv("WECOM_WEBHOOK_URL") or config.WECOM_WEBHOOK_URL or "").strip()


def _ensure_feishu_token() -> Tuple[str, str, str]:
    app_id = (os.getenv("FEISHU_APP_ID") or config.FEISHU_APP_ID or "").strip()
    app_secret = (os.getenv("FEISHU_APP_SECRET") or config.FEISHU_APP_SECRET or "").strip()
    if not app_id or not app_secret:
        raise SystemExit("未配置 FEISHU_APP_ID/FEISHU_APP_SECRET（需要下载图片后转发到企业微信）")
    token = get_feishu_tenant_access_token(app_id, app_secret)
    return app_id, app_secret, token


def main() -> int:
    ap = argparse.ArgumentParser(description="单独发送一个游戏的报告到企业微信（基于 step5 卡片）")
    ap.add_argument("--input", default="", help="step5_feishu_card_*.json 路径（默认自动取 data 下最新）")
    ap.add_argument("--latest", action="store_true", help="自动选择 data 下最新 step5 文件（默认行为）")
    ap.add_argument("--only-game", type=int, default=0, help="只发送指定游戏序号（例如 3 表示【游戏 3】）")
    ap.add_argument("--only-name", type=str, default="", help="只发送指定游戏名称（支持包含匹配）")
    ap.add_argument("--skip-header", action="store_true", help="不发送头部摘要（默认会发送）")
    ap.add_argument("--max-text-len", type=int, default=3800, help="每条文字消息最大字符数（默认 3800）")
    ap.add_argument("--min-interval", type=float, default=3.2, help="发送节流：每条消息间隔秒数（默认 3.2）")
    ap.add_argument("--max-retries", type=int, default=3, help="企业微信频率限制重试次数（默认 3）")
    ap.add_argument("--send-image", action="store_true", help="发送中间截图（需要 FEISHU_APP_ID/FEISHU_APP_SECRET）")
    ap.add_argument(
        "--webhook",
        choices=["default", "real"],
        default="default",
        help="选择企业微信 webhook：default 使用 WECOM_WEBHOOK_URL；real 使用 WECOM_WEBHOOK_URL_REAL",
    )
    ap.add_argument("--webhook-url", default="", help="直接指定企业微信 webhook URL（优先级最高）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将发送内容，不实际发送")
    args = ap.parse_args()

    wecom_webhook = _resolve_wecom_webhook(args)
    if not wecom_webhook:
        if args.webhook == "real":
            raise SystemExit("未配置 WECOM_WEBHOOK_URL_REAL（请写入 .env 或环境变量）")
        raise SystemExit("未配置 WECOM_WEBHOOK_URL（请写入 .env 或环境变量）")

    input_path = _resolve_input_path(args.input, args.latest)
    if not input_path.exists():
        raise SystemExit(f"找不到输入文件：{input_path}")

    step5 = json.loads(input_path.read_text(encoding="utf-8"))
    header_text, games = extract_sections_from_step5(step5)
    target = _select_game(games, args.only_game, args.only_name)

    sender = WeComSender(
        wecom_webhook,
        min_interval_seconds=args.min_interval,
        max_retries=args.max_retries,
        retry_base_seconds=15.0,
    )

    if header_text and not args.skip_header:
        for c in chunk_text(header_text, args.max_text_len):
            if args.dry_run:
                print(f"[HEADER]\n{c}\n")
            else:
                sender.send_markdown(c)

    merged = target.merged_text()
    for c in chunk_text(merged, args.max_text_len):
        if args.dry_run:
            print(f"[GAME {target.index} {target.name}]\n{c}\n")
        else:
            sender.send_markdown(c)

    if args.send_image and target.middle_img_key:
        if args.dry_run:
            print(f"[IMG middle] {target.middle_img_key}")
        else:
            _, _, token = _ensure_feishu_token()
            img_bytes = download_feishu_image_bytes(target.middle_img_key, token)
            sender.send_image_bytes(img_bytes)

    print("✅ 企业微信发送完成（单游戏）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

