"""
把“测试分析结果（test_innovation_prompt_*.json）”按原工作流方式发送到飞书 + 企业微信。

逻辑对齐：
- 飞书：复用 ReportGenerator.generate_feishu_format() + FeishuSender.send_card()
- 企业微信：复用 send_step5_to_wecom.py 的解析/发送逻辑（从生成的 step5 卡片转发）

用法：
  python send_test_to_feishu_wecom.py --input data/test_innovation_prompt_xxx.json
  python send_test_to_feishu_wecom.py --latest
  python send_test_to_feishu_wecom.py --latest --wecom-webhook real
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from modules.feishu_sender import FeishuSender
from modules.report_generator import ReportGenerator

import config


def _pick_latest_test_json() -> Optional[Path]:
    data_dir = Path("data")
    files = list(data_dir.glob("test_innovation_prompt_*.json"))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def _analysis_from_test_payload(payload: Dict) -> Dict:
    game_name = payload.get("game_name") or payload.get("game") or "未知游戏"
    game_info = payload.get("game_info") or {}

    def _g(k: str, default: str = "") -> str:
        v = game_info.get(k, default)
        return "" if v is None else str(v)

    analysis: Dict = {
        "game_name": str(game_name),
        "analysis": payload.get("analysis") or "",
        "analysis_data": payload.get("analysis_data"),
        "model_used": payload.get("model_used") or payload.get("analysis_model") or "unknown",
        "status": payload.get("status") or "success",
        # 对齐 ReportGenerator 字段
        "game_rank": _g("排名"),
        "game_company": _g("开发公司"),
        "rank_change": _g("排名变化", "--") or "--",
        "platform": _g("平台"),
        "source": _g("来源"),
        "board_name": _g("榜单"),
        "monitor_date": _g("监控日期"),
        # 用视频URL填充 gdrive_url（用于生成“视频链接”）
        "gdrive_url": payload.get("video_url") or "",
    }

    # 尝试从数据库补齐截图 key（如果之前工作流已经上传过）
    try:
        from modules.database import VideoDatabase

        db = VideoDatabase()
        keys = db.get_screenshot_key(analysis["game_name"])
        if keys:
            analysis["screenshot_image_keys"] = keys
    except Exception:
        pass

    return analysis


def main() -> int:
    ap = argparse.ArgumentParser(description="发送测试分析结果到飞书与企业微信（复用工作流逻辑）")
    ap.add_argument("--input", default="", help="data/test_innovation_prompt_*.json 路径")
    ap.add_argument("--latest", action="store_true", help="自动选择 data 下最新的 test_innovation_prompt_*.json")
    ap.add_argument("--skip-feishu", action="store_true", help="不发送到飞书（只生成 step5 文件/或仅企微）")
    ap.add_argument("--skip-wecom", action="store_true", help="不发送到企业微信（只发飞书）")
    ap.add_argument("--dry-run", action="store_true", help="只生成文件并打印路径，不实际发送")

    # 企业微信参数（与 send_step5_to_wecom.py 对齐）
    ap.add_argument("--wecom-webhook", choices=["default", "real"], default="default", help="选择企业微信 webhook")
    ap.add_argument("--wecom-webhook-url", default="", help="直接指定企业微信 webhook URL（优先级最高）")
    ap.add_argument("--max-text-len", type=int, default=3800, help="企业微信每条文本最大字符数")
    ap.add_argument("--min-interval", type=float, default=3.2, help="企业微信发送间隔秒数")
    ap.add_argument("--max-retries", type=int, default=3, help="企业微信频率限制重试次数")
    ap.add_argument("--skip-header", action="store_true", help="企业微信不发头部摘要（测试常用）")
    args = ap.parse_args()

    input_path: Optional[Path]
    if args.input.strip():
        input_path = Path(args.input.strip())
    elif args.latest:
        input_path = _pick_latest_test_json()
    else:
        input_path = _pick_latest_test_json()

    if not input_path or not input_path.exists():
        print("错误：找不到测试文件。请用 --input 指定，或加 --latest。")
        return 1

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    analysis = _analysis_from_test_payload(payload)

    analyses = [analysis]
    rg = ReportGenerator()
    step5 = rg.generate_feishu_format(analyses)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_step5 = Path("data") / f"step5_feishu_card_test_{ts}.json"
    out_step5.write_text(json.dumps(step5, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已生成 step5：{out_step5}")

    # 飞书发送
    if not args.skip_feishu:
        if args.dry_run:
            print("[dry-run] 跳过飞书实际发送")
        else:
            fs = FeishuSender()
            ok = fs.send_card(step5)
            print("✅ 飞书发送成功" if ok else "❌ 飞书发送失败（请检查 FEISHU_WEBHOOK_URL）")

    # 企业微信发送：复用 send_step5_to_wecom 的解析/发送逻辑
    if args.skip_wecom:
        return 0

    if args.dry_run:
        print("[dry-run] 跳过企业微信实际发送")
        return 0

    # 计算 webhook
    if args.wecom_webhook_url:
        wecom_webhook = args.wecom_webhook_url.strip()
    elif args.wecom_webhook == "real":
        wecom_webhook = (os.getenv("WECOM_WEBHOOK_URL_REAL") or config.WECOM_WEBHOOK_URL_REAL or "").strip()
    else:
        wecom_webhook = (os.getenv("WECOM_WEBHOOK_URL") or config.WECOM_WEBHOOK_URL or "").strip()

    if not wecom_webhook:
        print("错误：未配置企业微信 webhook（WECOM_WEBHOOK_URL 或 WECOM_WEBHOOK_URL_REAL）")
        return 1

    # 复用 send_step5_to_wecom.py 的能力
    from send_step5_to_wecom import (
        chunk_text,
        download_feishu_image_bytes,
        extract_sections_from_step5,
        get_feishu_tenant_access_token,
    )
    from modules.wecom_sender import WeComSender

    header_text, games = extract_sections_from_step5(step5)

    sender = WeComSender(
        wecom_webhook,
        min_interval_seconds=args.min_interval,
        max_retries=args.max_retries,
        retry_base_seconds=15.0,
    )

    if header_text and not args.skip_header:
        for c in chunk_text(header_text, args.max_text_len):
            sender.send_markdown(c)

    # 飞书 token（只有需要图片时才获取）
    need_img = any(g.middle_img_key for g in games)
    token = ""
    if need_img:
        app_id = (os.getenv("FEISHU_APP_ID") or config.FEISHU_APP_ID or "").strip()
        app_secret = (os.getenv("FEISHU_APP_SECRET") or config.FEISHU_APP_SECRET or "").strip()
        if not app_id or not app_secret:
            print("错误：未配置 FEISHU_APP_ID/FEISHU_APP_SECRET（需要下载图片后转发到企业微信）")
            return 1
        token = get_feishu_tenant_access_token(app_id, app_secret)

    for g in games:
        merged = g.merged_text()
        for c in chunk_text(merged, args.max_text_len):
            sender.send_markdown(c)

        if g.middle_img_key:
            img_bytes = download_feishu_image_bytes(g.middle_img_key, token)
            sender.send_image_bytes(img_bytes)

    print("✅ 企业微信发送完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

