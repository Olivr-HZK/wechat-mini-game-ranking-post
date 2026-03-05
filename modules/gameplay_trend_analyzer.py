"""
游戏玩法趋势分析模块
基于本周各平台的分析结果与排名变化，汇总每个平台的本周热点玩法趋势；
若有上周趋势记录则进行对比。
支持两种方式：规则汇总（analyze_all_platforms）与大模型合成（synthesize_trends_with_llm）。
"""
import json
import re
from typing import List, Dict, Optional
from collections import defaultdict


def _normalize_platform(platform: str, source: str) -> str:
    """将平台名称规范为 wx/dy/ios/android"""
    if not platform:
        return ""
    p = (platform or "").strip()
    s = (source or "").strip()
    if "微信" in p or (s == "引力引擎" and "wx" in p.lower()):
        return "wx"
    if "抖音" in p or "dy" in p.lower():
        return "dy"
    if "iOS" in p or "ios" in p.lower():
        return "ios"
    if "Android" in p or "android" in p.lower():
        return "android"
    return p


def _extract_baseline_or_type(analysis: Dict) -> List[str]:
    """
    从单条分析中提取玩法类型标签：优先 baseline_game，否则从 core_gameplay 取前段关键词。
    返回可读的玩法类型列表（如 ["益智解谜", "排序/收纳"]）。
    """
    labels = []
    ad = analysis.get("analysis_data") or {}
    if isinstance(ad, str):
        try:
            import json
            ad = json.loads(ad) if ad.strip().startswith("{") else {}
        except Exception:
            ad = {}
    baseline = (ad.get("baseline_game") or "").strip()
    if baseline:
        # 格式多为 "大类 > 子类 > 具体"，取前两级或一级
        parts = [x.strip() for x in re.split(r"\s*>\s*", baseline) if x.strip()]
        if parts:
            labels.append(parts[0])
        if len(parts) > 1:
            labels.append(parts[1])
    core = (ad.get("core_gameplay") or "").strip()
    if not labels and core:
        # 取前一句或前 30 字作为简单标签
        first_sent = re.split(r"[。！？\n]", core)[0].strip()[:40]
        if first_sent:
            labels.append(first_sent)
    return labels if labels else ["未分类"]


def _rank_change_direction(rank_change: str) -> str:
    """排名变化方向：up / new / down / flat"""
    if not rank_change:
        return "flat"
    rc = (rank_change or "").strip()
    if "新进" in rc or "新进榜" in rc:
        return "new"
    if "↑" in rc or "升" in rc:
        return "up"
    if "↓" in rc or "降" in rc:
        return "down"
    return "flat"


def analyze_platform_trend(
    platform_analyses: List[Dict],
    platform_key: str,
    platform_display: str,
    source: str,
    monitor_date: str,
    week_range: Optional[str],
    last_week_trend_text: Optional[str],
) -> str:
    """
    针对单个平台的分析列表，生成一段「本周热点玩法趋势分析」文本。
    若有上周趋势则包含简要对比。
    """
    if not platform_analyses:
        return "本周该平台无分析数据。"

    # 按玩法类型聚合：类型 -> [ (game_name, rank_change_direction) ]
    type_to_games = defaultdict(list)
    for a in platform_analyses:
        name = (a.get("game_name") or "").strip()
        rc = a.get("rank_change") or ""
        direction = _rank_change_direction(rc)
        labels = _extract_baseline_or_type(a)
        for lb in labels:
            type_to_games[lb].append((name, direction))

    # 统计上升/新进榜较多的玩法类型
    type_summary = []
    for play_type, games in type_to_games.items():
        up_count = sum(1 for _, d in games if d in ("up", "new"))
        type_summary.append((play_type, len(games), up_count, games))

    # 按出现次数降序，再按上升/新进数量降序
    type_summary.sort(key=lambda x: (-x[1], -x[2]))

    lines = []
    lines.append(f"【{platform_display}】本周共分析 {len(platform_analyses)} 款游戏。")
    lines.append("")
    lines.append("热点玩法类型（按出现次数与排名上升情况），并列出代表游戏：")
    for play_type, count, up_count, game_list in type_summary[:8]:
        sample = [g[0] for g in game_list[:5]]
        # 明确提到具体游戏名，用《》标注
        games_str = "".join([f"《{name}》" for name in sample])
        if len(game_list) > 5:
            games_str += " 等"
        up_desc = f"，其中排名上升/新进榜 {up_count} 款" if up_count > 0 else ""
        lines.append(f"· **{play_type}**（{count} 款{up_desc}）代表游戏：{games_str}")
    lines.append("")

    if last_week_trend_text and last_week_trend_text.strip():
        lines.append("与上周对比：")
        prev = last_week_trend_text.strip()
        if len(prev) > 400:
            prev = prev[:400].rstrip() + "…"
        lines.append(prev)
    else:
        lines.append("（暂无上周趋势数据，无法做周同比。）")

    return "\n".join(lines).strip()


def analyze_all_platforms(
    analyses: List[Dict],
    monitor_date: str,
    week_range: Optional[str] = None,
    last_week_trends_by_platform: Optional[Dict[str, str]] = None,
) -> List[Dict]:
    """
    对所有分析按平台分组，逐平台生成玩法趋势分析。

    Args:
        analyses: 本周的分析结果列表（含 game_name, platform, source, rank_change, analysis_data）
        monitor_date: 监控日期（如 2026-01-27）
        week_range: 周范围（如 2026-1-19~2026-1-25），可选
        last_week_trends_by_platform: 上周各平台的趋势文本，key 为 wx/dy/ios/android

    Returns:
        列表，每项为 {
            "monitor_date": str,
            "week_range": str | None,
            "platform": str,   # wx/dy/ios/android
            "source": str,
            "trend_analysis": str,
        }
    """
    last_week_trends_by_platform = last_week_trends_by_platform or {}
    by_platform = defaultdict(list)
    for a in analyses:
        platform = _normalize_platform(a.get("platform") or "", a.get("source") or "")
        if platform:
            by_platform[platform].append(a)

    platform_display = {"wx": "微信小游戏", "dy": "抖音小游戏", "ios": "iOS", "android": "Android"}
    source_by_platform = {"wx": "引力引擎", "dy": "引力引擎", "ios": "SensorTower", "android": "SensorTower"}

    result = []
    for platform_key in ("wx", "dy", "ios", "android"):
        platform_analyses = by_platform.get(platform_key)
        if not platform_analyses:
            continue
        source = source_by_platform.get(platform_key, "未知")
        display = platform_display.get(platform_key, platform_key)
        last_text = last_week_trends_by_platform.get(platform_key)

        trend_text = analyze_platform_trend(
            platform_analyses=platform_analyses,
            platform_key=platform_key,
            platform_display=display,
            source=source,
            monitor_date=monitor_date,
            week_range=week_range,
            last_week_trend_text=last_text,
        )
        result.append({
            "monitor_date": monitor_date,
            "week_range": week_range,
            "platform": platform_key,
            "source": source,
            "trend_analysis": trend_text,
        })
    return result


# 平台显示名与来源（供大模型合成使用）
PLATFORM_DISPLAY = {"wx": "微信小游戏", "dy": "抖音小游戏", "ios": "iOS", "android": "Android"}
PLATFORM_SOURCE = {"wx": "引力引擎", "dy": "引力引擎", "ios": "SensorTower", "android": "SensorTower"}


def _extract_platform_json_fallback(content: str) -> Dict[str, str]:
    """
    当大模型返回的 JSON 被截断或含未转义引号时，用正则/扫描从内容中提取各平台字符串值。
    返回 {"wx": "...", "dy": "...", ...}，能提取多少算多少。
    """
    out = {}
    if not content or "{" not in content:
        return out
    content = content.strip()
    for key in ("wx", "dy", "ios", "android"):
        # 匹配 "key": " 或 "key": " 带空白
        pat = re.compile(r'"' + re.escape(key) + r'"\s*:\s*"', re.DOTALL)
        m = pat.search(content)
        if not m:
            continue
        start = m.end()
        i = start
        value_chars = []
        while i < len(content):
            if content[i] == "\\" and i + 1 < len(content):
                value_chars.append(content[i])
                value_chars.append(content[i + 1])
                i += 2
                continue
            if content[i] == '"':
                break
            value_chars.append(content[i])
            i += 1
        val = "".join(value_chars).strip()
        if val:
            out[key] = val
    return out

# 单条玩法在 prompt 中的最大字符数，避免 token 超限
_MAX_GAMEPLAY_CHARS = 600


def _build_gameplay_text_for_platform(platform_key: str, items: List[Dict]) -> str:
    """将某平台的 (game_name, gameplay_analysis, rank_change) 列表整理成一段可读文本。"""
    display = PLATFORM_DISPLAY.get(platform_key, platform_key)
    lines = [f"【{display}】本周榜单中已有玩法分析的游戏："]
    for i, it in enumerate(items, 1):
        name = (it.get("game_name") or "").strip()
        rc = (it.get("rank_change") or "").strip()
        analysis = (it.get("gameplay_analysis") or "").strip()
        if len(analysis) > _MAX_GAMEPLAY_CHARS:
            analysis = analysis[:_MAX_GAMEPLAY_CHARS].rstrip() + "…"
        rc_part = f" 排名变化：{rc}" if rc else ""
        lines.append(f"{i}. 《{name}》{rc_part}")
        lines.append(f"   玩法分析：{analysis}")
        lines.append("")
    return "\n".join(lines).strip()


def synthesize_trends_with_llm(
    gameplay_by_platform: Dict[str, List[Dict]],
    last_week_trends_by_platform: Optional[Dict[str, str]] = None,
    week_range: Optional[str] = None,
    monitor_date: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> List[Dict]:
    """
    用大模型将各平台排行榜的游戏玩法综合成本周玩法趋势，并与上周对比（若有）。

    Args:
        gameplay_by_platform: 各平台玩法列表，key 为 wx/dy/ios/android，
            每项为 [{"game_name": "...", "gameplay_analysis": "...", "rank_change": "..."}, ...]
        last_week_trends_by_platform: 上周各平台趋势文本，key 为 wx/dy/ios/android
        week_range: 周范围，如 2026-1-19~2026-1-25
        monitor_date: 监控日期，如 2026-01-27
        api_key: OpenRouter API Key，不传则用 config
        base_url: OpenRouter 基础 URL，不传则用 config
        model: 模型名，不传则用 config.VIDEO_ANALYSIS_MODEL

    Returns:
        列表，每项为 {
            "monitor_date": str,
            "week_range": str,
            "platform": str,
            "source": str,
            "trend_analysis": str,
        }
    """
    try:
        import config as _config
        import requests
    except ImportError:
        return []

    api_key = api_key or getattr(_config, "OPENROUTER_API_KEY", "") or ""
    base_url = (base_url or getattr(_config, "OPENROUTER_BASE_URL", "") or "").rstrip("/")
    model = model or getattr(_config, "VIDEO_ANALYSIS_MODEL", "google/gemini-2.5-pro")
    if not api_key or not base_url:
        return []

    last_week_trends_by_platform = last_week_trends_by_platform or {}
    from datetime import datetime
    monitor_date = monitor_date or datetime.now().strftime("%Y-%m-%d")

    # 构建输入：各平台玩法文本 + 上周趋势（若有）
    parts = []
    for platform_key in ("wx", "dy", "ios", "android"):
        items = gameplay_by_platform.get(platform_key) or []
        if not items:
            continue
        parts.append(_build_gameplay_text_for_platform(platform_key, items))

    if not parts:
        return []

    input_text = "\n\n---\n\n".join(parts)

    last_week_block = ""
    if last_week_trends_by_platform:
        last_lines = ["【上周各平台玩法趋势（供对比）】"]
        for pk in ("wx", "dy", "ios", "android"):
            t = (last_week_trends_by_platform.get(pk) or "").strip()
            if t:
                disp = PLATFORM_DISPLAY.get(pk, pk)
                last_lines.append(f"{disp}：{t[:500]}{'…' if len(t) > 500 else ''}")
        last_week_block = "\n".join(last_lines)

    prompt = f"""你是一位游戏市场与玩法分析专家。下面给出的是「本周」各平台（微信小游戏、抖音小游戏、iOS、Android）排行榜中、已有玩法分析的游戏列表及其玩法分析内容与排名变化。

请基于这些内容，为**每个平台**分别写一段「本周玩法趋势」分析（每段控制在 150–250 字，避免过长导致输出被截断）：
1. 概括该平台本周榜单中的主流/热点玩法类型；
2. 结合排名变化（上升/新进榜/下降）指出哪些玩法在升温、哪些在降温；
3. 若有「上周各平台玩法趋势」参考，请简要对比本周与上周的变化（同与异）。

要求：
- **必须**输出一个合法的 JSON 对象，不要任何解释或 markdown 包裹；键必须为 wx, dy, ios, android；某平台无数据则对应值为空字符串 ""；
- JSON 内字符串中的双引号请用反斜杠转义（如 \\"），不要换行，确保可被解析；
- 语言简洁、有条理，可直接用于周报；不要编造未在输入中出现的游戏或玩法。

格式示例（请严格按此格式输出）：
{{"wx": "微信小游戏的趋势分析正文...", "dy": "抖音小游戏的趋势分析正文...", "ios": "iOS 的趋势分析正文...", "android": "Android 的趋势分析正文..."}}

【本周各平台榜单游戏玩法】
{input_text}
"""
    if last_week_block:
        prompt += f"\n\n{last_week_block}\n"

    print(f"  [周报趋势] 使用模型: {model}")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/wechat-mini-game-ranking-post",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8000,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
    except Exception as e:
        print(f"  大模型请求失败：{e}")
        return []

    if resp.status_code != 200:
        print(f"  大模型返回非 200：{resp.status_code} {resp.text[:300]}")
        return []

    try:
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    except Exception:
        return []

    # 解析 JSON：可能被包在 markdown 代码块里
    content = content.strip()
    for start in ("```json", "```"):
        if content.startswith(start):
            content = content[len(start):].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
    try:
        trend_by_platform = json.loads(content)
    except json.JSONDecodeError as e:
        # 可能是响应被截断或内容中含未转义引号，尝试用正则提取各平台块
        trend_by_platform = _extract_platform_json_fallback(content)
        if not trend_by_platform:
            print("  大模型返回无法解析为 JSON，将原始内容按平台拆分失败")
            print(f"  解析错误: {e}")
            print(f"  原始内容前 800 字符: {repr(content[:800])}")
            return []

    result = []
    for platform_key in ("wx", "dy", "ios", "android"):
        text = (trend_by_platform.get(platform_key) or "").strip()
        if not text:
            continue
        result.append({
            "monitor_date": monitor_date,
            "week_range": week_range or "",
            "platform": platform_key,
            "source": PLATFORM_SOURCE.get(platform_key, "未知"),
            "trend_analysis": text,
        })
    return result
