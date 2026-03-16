"""
简单测试：直接调用 OpenRouter 上配置的 Gemini 模型，看网络和鉴权是否正常。

运行方式（项目根目录）：

    python scripts/tests/test_openrouter_gemini.py

预期：
- 如果网络 + KEY 正常，打印出模型返回的一小段文本；
- 如果有网络 / TLS / 鉴权问题，会把 HTTP 状态码和错误信息完整打印出来，方便排查。
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402
import config    # noqa: E402


def main() -> None:
    base_url = config.OPENROUTER_BASE_URL
    api_key = getattr(config, "OPENROUTER_API_KEY", "") or ""
    model = getattr(config, "VIDEO_ANALYSIS_MODEL", "google/gemini-2.5-pro")

    print(f"OpenRouter 基础地址: {base_url}")
    print(f"测试模型: {model}")

    if not api_key:
        print("ERROR: 未配置 OPENROUTER_API_KEY，请在 .env 中设置后重试。")
        return

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # 可选信息，方便在 OpenRouter 侧区分来源
        "HTTP-Referer": "https://github.com/your-repo",
        "X-Title": "OpenRouter Gemini Connectivity Test",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请用一句中文简要回答：你现在能正常通过 OpenRouter 被调用吗？"
                    }
                ],
            }
        ],
        "max_tokens": 128,
    }

    print(f"\nPOST {url}")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except Exception as e:
        print(f"\n请求阶段发生异常：{e!r}")
        return

    print(f"\nHTTP 状态码：{resp.status_code}")

    # 打印部分原始响应内容（便于看错误信息）
    raw_text = resp.text or ""
    print("\n原始响应前 800 字符：")
    print(raw_text[:800])

    if resp.status_code != 200:
        print("\n非 200 响应，通常是网络 / 鉴权 / 配额问题，上面那段原始响应就是关键信息。")
        return

    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        print(f"\nJSON 解析失败：{e!r}")
        return

    choices = data.get("choices") or []
    if not choices:
        print("\n响应中没有 choices 字段或为空，完整 JSON 如下：")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1200])
        return

    content = choices[0].get("message", {}).get("content")
    print("\n模型返回内容：")
    print(content)


if __name__ == "__main__":
    main()

