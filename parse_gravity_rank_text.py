"""
从“引力引擎”页面复制出来的纯文本中，解析出排行榜并导出 CSV。

适用场景：
- 你在浏览器里把榜单列表全选复制（或从终端输出复制）得到类似文本：
    羊了个羊：星球
    休闲:2名
    消除
    北京简游科技有限公司
    NO.4
    腾讯欢乐斗地主
    棋牌:1名
    牌类
    ...
    NO.5

解析规则（尽量稳健，但仍属“兜底方案”）：
- 以行 `NO.<数字>` 作为一条记录的结束标记（该 NO 数字归属上一条记录的“排名”）
- 每条记录首行视为“游戏名称”
- `xxx:<数字>名` 行用于跳过（代表分类内名次）
- “游戏类型”取分类名次行后第一个有效标签（如“消除/益智/枪战/牌类”等）
- “开发公司”取记录内最后一个像公司/开发者的行（含“公司/有限公司/股份有限公司/个人开发者”等）
- “发布时间”优先提取 “霸榜N天”，否则留空
- “热度指数”缺失时按排名简单生成：100 - (rank-1)*2（最低 0）
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Iterable, List, Dict, Optional


NO_RE = re.compile(r"^NO\.\s*(\d+)\s*$", re.IGNORECASE)
CATE_RANK_RE = re.compile(r"^(.+?):\s*(\d+)\s*名\s*$")
DOMINATE_DAYS_RE = re.compile(r"霸榜\s*(\d+)\s*天")


def _is_company_like(s: str) -> bool:
    s = s.strip()
    if not s or s == "--":
        return False
    keywords = [
        "有限公司",
        "有限责任公司",
        "股份有限公司",
        "公司",
        "工作室",
        "个人开发者",
    ]
    return any(k in s for k in keywords)


def _pick_game_type(attrs: List[str]) -> str:
    for s in attrs:
        s = s.strip()
        if not s or s == "--":
            continue
        if NO_RE.match(s) or CATE_RANK_RE.match(s):
            continue
        if DOMINATE_DAYS_RE.search(s):
            continue
        if _is_company_like(s):
            continue
        return s
    return ""


def _pick_company(attrs: List[str]) -> str:
    for s in reversed(attrs):
        s = s.strip()
        if _is_company_like(s):
            return s
    return "--"


def _pick_publish_days(attrs: List[str]) -> str:
    for s in attrs:
        m = DOMINATE_DAYS_RE.search(s)
        if m:
            return f"{m.group(1)}天"
    return ""


def _parse_record(block_lines: List[str], overall_rank: Optional[int]) -> Optional[Dict[str, str]]:
    lines = [ln.strip() for ln in block_lines if ln and ln.strip()]
    if not lines:
        return None

    name = lines[0].strip()
    if not name or NO_RE.match(name):
        return None

    # 找到“分类内名次”行，用于定位属性起点
    cate_idx = None
    for i, ln in enumerate(lines[1:], start=1):
        if CATE_RANK_RE.match(ln):
            cate_idx = i
            break

    attrs = lines[cate_idx + 1 :] if cate_idx is not None else lines[1:]

    game_type = _pick_game_type(attrs) or "休闲游戏"
    company = _pick_company(attrs)
    publish_days = _pick_publish_days(attrs)

    rank = overall_rank
    rank_str = str(rank) if rank is not None else ""

    # 热度指数：若没有排名就先留空，后面补
    heat = ""
    if rank is not None:
        heat = str(max(0, 100 - (rank - 1) * 2))

    return {
        "排名": rank_str,
        "游戏名称": name,
        "游戏类型": game_type,
        "热度指数": heat,
        "平台": "微信小游戏",
        "发布时间": publish_days,
        "开发公司": company,
        "排名变化": "--",
    }


def parse_text(text: str) -> List[Dict[str, str]]:
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    blocks: List[Dict[str, str]] = []
    cur: List[str] = []

    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue

        m = NO_RE.match(ln)
        if m:
            rank = int(m.group(1))
            rec = _parse_record(cur, overall_rank=rank)
            if rec:
                blocks.append(rec)
            cur = []
            continue

        cur.append(ln)

    # 末尾没有 NO 的残余块也尝试解析
    tail = _parse_record(cur, overall_rank=None)
    if tail:
        blocks.append(tail)

    # 补齐缺失排名/热度（按出现顺序）
    next_rank = 1
    for rec in blocks:
        if not rec.get("排名"):
            rec["排名"] = str(next_rank)
        try:
            r = int(rec["排名"])
        except Exception:
            r = next_rank
            rec["排名"] = str(r)
        if not rec.get("热度指数"):
            rec["热度指数"] = str(max(0, 100 - (r - 1) * 2))
        next_rank = max(next_rank, r + 1)

    # 按排名排序
    try:
        blocks.sort(key=lambda x: int(x.get("排名") or 999999))
    except Exception:
        pass

    return blocks


def write_csv(rows: List[Dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["排名", "游戏名称", "游戏类型", "热度指数", "平台", "发布时间", "开发公司", "排名变化"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="从复制文本解析引力引擎榜单并导出CSV")
    ap.add_argument(
        "--input",
        "-i",
        type=str,
        default="",
        help="输入文本文件路径；不提供则从标准输入读取（粘贴后 Ctrl+Z 回车结束）",
    )
    ap.add_argument(
        "--output",
        "-o",
        type=str,
        default="data/game_rankings.csv",
        help="输出CSV路径（默认 data/game_rankings.csv）",
    )
    ap.add_argument("--limit", type=int, default=0, help="最多输出前 N 条（0 表示不限制）")
    args = ap.parse_args(argv)

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8", errors="ignore")
    else:
        print("请粘贴榜单文本，然后按 Ctrl+Z 回车结束输入：", file=sys.stderr)
        text = sys.stdin.read()

    rows = parse_text(text)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    out = Path(args.output)
    write_csv(rows, out)
    print(f"✅ 已导出 {len(rows)} 条到: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

