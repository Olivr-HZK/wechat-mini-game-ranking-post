"""
单独发送【一个游戏】到飞书（机器人 Webhook）。

输入：step5 飞书卡片（step5_feishu_card_*.json）
- 自动选择 data 下最新 step5（也可 --input 指定）
- 支持按“游戏序号”或“游戏名称”选择单个游戏
- 默认保留卡片原样（若原 step5 含截图 img_key，会一并发送）；可用 --no-images 去掉图片相关元素

用法：
  python send_single_game_to_feishu.py --only-game 3
  python send_single_game_to_feishu.py --only-name "羊了个羊"
  python send_single_game_to_feishu.py --input data/step5_feishu_card_20260121_104623.json --only-game 1
  python send_single_game_to_feishu.py --only-game 1 --skip-header
  python send_single_game_to_feishu.py --only-game 1 --no-images
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.feishu_sender import FeishuSender

# 复用已有：标题识别 & markdown 归一化（去掉 ** 后更好匹配）
from send_step5_to_wecom import GAME_TITLE_RE, normalize_lark_md_to_text  # noqa: E402


@dataclass
class GameBlock:
    index: int
    name: str
    elements: List[Dict[str, Any]]


def _pick_latest_step5() -> Optional[Path]:
    data_dir = Path("data")
    patterns = ["step5_feishu_card_*.json", "step5_feishu_card_test_*.json"]
    files: List[Path] = []
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


def _is_game_title_div(el: Dict[str, Any]) -> Optional[tuple[int, str]]:
    if (el or {}).get("tag") != "div":
        return None
    text_obj = (el.get("text") or {})
    content = text_obj.get("content") or ""
    content = normalize_lark_md_to_text(content)
    m = GAME_TITLE_RE.search(content)
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip()


def _split_blocks(elements: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[GameBlock]]:
    """
    把 step5 的 card.elements 拆成：
    - header_elements：第一个“游戏标题”之前的 elements（包含日期摘要等）
    - game_blocks：每个游戏对应的 elements（从标题行开始，到下一个游戏标题前）
    """
    header: List[Dict[str, Any]] = []
    blocks: List[GameBlock] = []

    current_idx: Optional[int] = None
    current_name: str = ""
    current_elems: List[Dict[str, Any]] = []
    started = False

    def flush():
        nonlocal current_idx, current_name, current_elems
        if current_idx is None:
            return
        blocks.append(GameBlock(index=current_idx, name=current_name, elements=current_elems))
        current_idx = None
        current_name = ""
        current_elems = []

    for el in elements or []:
        title_info = _is_game_title_div(el)
        if title_info:
            started = True
            flush()
            current_idx, current_name = title_info
            current_elems = [el]
            continue

        if not started:
            header.append(el)
        else:
            # 游戏区块内
            if current_idx is not None:
                current_elems.append(el)

    flush()
    return header, blocks


def _select_block(blocks: List[GameBlock], only_game: int, only_name: str) -> GameBlock:
    if only_game and only_game > 0:
        for b in blocks:
            if b.index == only_game:
                return b
        raise SystemExit(f"未找到要发送的游戏序号：{only_game}")

    name = (only_name or "").strip()
    if name:
        for b in blocks:
            if b.name.strip() == name:
                return b
        for b in blocks:
            if name in b.name:
                return b
        raise SystemExit(f"未找到要发送的游戏名称：{name}")

    raise SystemExit("请指定 --only-game 或 --only-name")


def _strip_images(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for el in elements:
        tag = (el or {}).get("tag")
        if tag == "img":
            continue
        if tag == "div":
            content = ((el.get("text") or {}).get("content") or "")
            content_n = normalize_lark_md_to_text(content)
            if "截图" in content_n:
                # 去掉 “🎬 游戏截图 / 开头截图 / 中间截图 / 结尾截图” 等说明
                continue
        out.append(el)
    # 去掉末尾多余 hr
    while out and (out[-1] or {}).get("tag") == "hr":
        out.pop()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="单独发送一个游戏到飞书（基于 step5 卡片）")
    ap.add_argument("--input", default="", help="step5_feishu_card_*.json 路径（默认自动取 data 下最新）")
    ap.add_argument("--latest", action="store_true", help="自动选择 data 下最新 step5 文件（默认行为）")
    ap.add_argument("--only-game", type=int, default=0, help="只发送指定游戏序号（例如 3 表示【游戏 3】）")
    ap.add_argument("--only-name", type=str, default="", help="只发送指定游戏名称（支持包含匹配）")
    ap.add_argument("--skip-header", action="store_true", help="不发送头部摘要（日期/数量等）")
    ap.add_argument("--no-images", action="store_true", help="去掉卡片内的图片/截图说明（只发文字）")
    ap.add_argument("--dry-run", action="store_true", help="只生成单游戏 step5 文件，不实际发送")
    args = ap.parse_args()

    input_path = _resolve_input_path(args.input, args.latest)
    if not input_path.exists():
        raise SystemExit(f"找不到输入文件：{input_path}")

    step5 = json.loads(input_path.read_text(encoding="utf-8"))
    card = step5.get("card") or {}
    elements = card.get("elements") or []

    header_elements, blocks = _split_blocks(elements)
    if not blocks:
        raise SystemExit("step5 中未解析到任何游戏区块（请检查输入是否为 step5_feishu_card_*.json）")

    target = _select_block(blocks, args.only_game, args.only_name)

    new_elements: List[Dict[str, Any]] = []
    if not args.skip_header and header_elements:
        new_elements.extend(header_elements)
        # 保险：头部和正文之间加一个分隔线（如果头部没有）
        if not new_elements or (new_elements[-1] or {}).get("tag") != "hr":
            new_elements.append({"tag": "hr"})

    new_elements.extend(target.elements)

    # 去掉末尾 hr
    while new_elements and (new_elements[-1] or {}).get("tag") == "hr":
        new_elements.pop()

    if args.no_images:
        new_elements = _strip_images(new_elements)

    new_step5 = dict(step5)
    new_step5["card"] = dict(card)
    new_step5["card"]["elements"] = new_elements

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path("data") / f"step5_feishu_card_single_game_{target.index}_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(new_step5, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已生成单游戏 step5：{out_path}")

    if args.dry_run:
        print("[dry-run] 不实际发送飞书")
        return 0

    sender = FeishuSender()
    ok = sender.send_card(new_step5)
    print("✅ 飞书发送成功（单游戏）" if ok else "❌ 飞书发送失败（请检查 FEISHU_WEBHOOK_URL）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

