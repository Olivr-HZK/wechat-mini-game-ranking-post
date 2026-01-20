"""
把 step5 的飞书卡片（interactive card JSON）转发到企业微信（群机器人 Webhook）。

需求：
- 图片：只发送“中间截图”，且图片需要单独发送
- 文字：每 4000 词/字左右分段（这里按字符长度做分段，默认 3800）

用法：
    python send_step5_to_wecom.py --input data/step5_feishu_card_xxx.json

依赖：
- 企业微信 Webhook：环境变量 WECOM_WEBHOOK_URL（写在 .env / env_example.txt）
- 飞书图片下载：需要 FEISHU_APP_ID / FEISHU_APP_SECRET（用于把 img_key 下载成二进制图片）
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

import requests

import config
from modules.wecom_sender import WeComSender


GAME_TITLE_RE = re.compile(r"【游戏\s*(\d+)】\s*([^\*|]+)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def chunk_text(text: str, max_len: int) -> List[str]:
    """按最大字符长度切分，优先按段落/行切。"""
    text = (text or "").strip()
    if not text:
        return []

    parts = re.split(r"\n{2,}", text)
    chunks: List[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        candidate = p if not buf else (buf + "\n\n" + p)
        if len(candidate) <= max_len:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        # 单段过长就硬切
        while len(p) > max_len:
            chunks.append(p[:max_len])
            p = p[max_len:]
        buf = p
    if buf:
        chunks.append(buf)
    return chunks


def normalize_lark_md_to_text(s: str) -> str:
    """把飞书 lark_md 粗略转成企业微信可读文本。"""
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    # 保留 markdown 链接（企业微信群机器人 markdown 支持 [text](url)，这样链接可点击）
    # 去掉加粗符号（企业微信 markdown 不一定支持）
    s = s.replace("**", "")
    return s.strip()


@dataclass
class GameSection:
    index: int
    name: str
    text_blocks: List[str]
    middle_img_key: Optional[str] = None

    def merged_text(self) -> str:
        return "\n\n".join([b for b in self.text_blocks if b.strip()]).strip()


def extract_sections_from_step5(step5: dict) -> Tuple[str, List[GameSection]]:
    """
    从飞书 card.elements 提取：
    - header_text：总体标题/日期信息
    - games：每个游戏的文字块 + “中间截图”的 img_key
    """
    card = step5.get("card") or {}
    elements = card.get("elements") or []

    header_parts: List[str] = []
    games: List[GameSection] = []

    current_game: Optional[GameSection] = None
    pending_middle = False

    def ensure_game(idx: int, name: str) -> GameSection:
        nonlocal current_game
        g = GameSection(index=idx, name=name.strip(), text_blocks=[])
        games.append(g)
        current_game = g
        return g

    for el in elements:
        tag = el.get("tag")

        if tag == "hr":
            continue

        if tag == "div":
            text_obj = el.get("text") or {}
            content = text_obj.get("content") or ""
            content = normalize_lark_md_to_text(content)
            if not content:
                continue

            # 游戏标题行
            m = GAME_TITLE_RE.search(content)
            if m:
                idx = int(m.group(1))
                name = m.group(2).strip()
                ensure_game(idx, name)
                # 标题行也作为正文第一行保留
                current_game.text_blocks.append(content)
                pending_middle = False
                continue

            # 截图相关文字不要放进正文
            if any(k in content for k in ["游戏截图", "开头截图", "中间截图", "结尾截图"]):
                pending_middle = "中间截图" in content
                continue

            if current_game is None:
                header_parts.append(content)
            else:
                current_game.text_blocks.append(content)
            continue

        if tag == "img":
            img_key = el.get("img_key")
            if pending_middle and current_game is not None and img_key:
                current_game.middle_img_key = img_key
            pending_middle = False
            continue

    header_text = "\n\n".join([p for p in header_parts if p.strip()]).strip()
    return header_text, games


def get_feishu_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0 or not data.get("tenant_access_token"):
        raise RuntimeError(f"获取飞书 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def download_feishu_image_bytes(image_key: str, tenant_access_token: str) -> bytes:
    """
    下载飞书图片二进制。
    文档：GET https://open.feishu.cn/open-apis/im/v1/images/:image_key
    有些场景需要 type=message，做一次兜底重试。
    """
    url = f"https://open.feishu.cn/open-apis/im/v1/images/{image_key}"
    headers = {"Authorization": f"Bearer {tenant_access_token}"}

    r = requests.get(url, headers=headers, timeout=60)
    if r.status_code == 200 and r.content:
        return r.content

    # 兜底：加 type=message
    r2 = requests.get(url, headers=headers, params={"type": "message"}, timeout=60)
    if r2.status_code == 200 and r2.content:
        return r2.content

    raise RuntimeError(f"下载飞书图片失败: status={r.status_code}, status2={r2.status_code}, body={r.text[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="把 step5 飞书卡片发送到企业微信")
    ap.add_argument(
        "--input",
        default="data/step5_feishu_card_20260119_184047.json",
        help="step5_feishu_card_*.json 路径",
    )
    ap.add_argument("--max-text-len", type=int, default=3800, help="每条文字消息最大字符数（默认 3800）")
    ap.add_argument("--min-interval", type=float, default=3.2, help="发送节流：每条消息间隔秒数（默认 3.2）")
    ap.add_argument("--max-retries", type=int, default=3, help="企业微信频率限制重试次数（默认 3）")
    ap.add_argument(
        "--only-game",
        type=int,
        default=0,
        help="只发送指定游戏序号（例如 3 表示只发【游戏 3】；默认 0 表示发送全部）",
    )
    ap.add_argument(
        "--skip-header",
        action="store_true",
        help="只发游戏内容，不发送头部摘要（常用于测试 --only-game）",
    )
    ap.add_argument(
        "--webhook",
        choices=["default", "real"],
        default="default",
        help="选择发送的企业微信 webhook：default 使用 WECOM_WEBHOOK_URL；real 使用 WECOM_WEBHOOK_URL_REAL",
    )
    ap.add_argument(
        "--webhook-url",
        default="",
        help="直接指定企业微信 webhook URL（优先级最高，覆盖 --webhook 选择）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只打印将发送内容，不实际发送")
    args = ap.parse_args()

    if args.webhook_url:
        wecom_webhook = args.webhook_url.strip()
    elif args.webhook == "real":
        wecom_webhook = (os.getenv("WECOM_WEBHOOK_URL_REAL") or config.WECOM_WEBHOOK_URL_REAL or "").strip()
    else:
        wecom_webhook = (os.getenv("WECOM_WEBHOOK_URL") or config.WECOM_WEBHOOK_URL or "").strip()

    if not wecom_webhook:
        if args.webhook == "real":
            raise SystemExit("未配置 WECOM_WEBHOOK_URL_REAL（请写入 .env 或环境变量）")
        raise SystemExit("未配置 WECOM_WEBHOOK_URL（请写入 .env 或环境变量）")

    input_path = Path(args.input)
    step5 = json.loads(input_path.read_text(encoding="utf-8"))

    header_text, games = extract_sections_from_step5(step5)

    if args.only_game and args.only_game > 0:
        games = [g for g in games if g.index == args.only_game]
        if not games:
            raise SystemExit(f"未找到要发送的游戏：{args.only_game}（请检查 step5 卡片里是否存在该序号）")

    # 准备飞书 token（用于下载中间截图）
    app_id = (os.getenv("FEISHU_APP_ID") or config.FEISHU_APP_ID or "").strip()
    app_secret = (os.getenv("FEISHU_APP_SECRET") or config.FEISHU_APP_SECRET or "").strip()
    if not app_id or not app_secret:
        raise SystemExit("未配置 FEISHU_APP_ID/FEISHU_APP_SECRET（需要下载图片后转发到企业微信）")

    sender = WeComSender(
        wecom_webhook,
        min_interval_seconds=args.min_interval,
        max_retries=args.max_retries,
        retry_base_seconds=15.0,
    )

    if header_text and not args.skip_header:
        header_chunks = chunk_text(header_text, args.max_text_len)
        if args.dry_run:
            print("=== HEADER ===")
            for c in header_chunks:
                print(c)
                print("----")
        else:
            for c in header_chunks:
                sender.send_markdown(c)

    token = get_feishu_tenant_access_token(app_id, app_secret)

    # 逐游戏发送：文字(分段) -> 中间截图(单独 image)
    failed_images: List[Tuple[int, str, str]] = []
    for g in games:
        text = g.merged_text()
        text_chunks = chunk_text(text, args.max_text_len)

        if args.dry_run:
            print(f"\n=== GAME {g.index}: {g.name} ===")
            for c in text_chunks:
                print(c)
                print("----")
        else:
            for c in text_chunks:
                sender.send_markdown(c)

        # 图片只发“中间截图”，且单独发送
        if g.middle_img_key:
            if args.dry_run:
                print(f"[IMG middle] {g.middle_img_key}")
            else:
                try:
                    img_bytes = download_feishu_image_bytes(g.middle_img_key, token)
                    sender.send_image_bytes(img_bytes)
                except Exception as e:
                    failed_images.append((g.index, g.name, g.middle_img_key))
                    print(f"[!] 游戏{g.index}《{g.name}》中间截图发送失败：{e}")
                    # 频控场景下给一点缓冲，避免后续继续撞限
                    time.sleep(5)

    if failed_images:
        print("\n[!] 以下游戏的中间截图未发送成功：")
        for idx, name, key in failed_images:
            print(f"  - 游戏{idx}《{name}》 img_key={key}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

