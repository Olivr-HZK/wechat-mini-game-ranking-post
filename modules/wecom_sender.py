import base64
import hashlib
import time
from typing import Optional

import requests


class WeComSender:
    """
    企业微信群机器人发送器（Webhook）。
    - 文本：markdown（更高字数上限）
    - 图片：image（base64 + md5），需单独发送
    """

    def __init__(
        self,
        webhook_url: str,
        min_interval_seconds: float = 3.2,
        max_retries: int = 3,
        retry_base_seconds: float = 15.0,
    ):
        self.webhook_url = (webhook_url or "").strip()
        self.min_interval_seconds = float(min_interval_seconds)
        self.max_retries = int(max_retries)
        self.retry_base_seconds = float(retry_base_seconds)
        self._last_send_ts = 0.0

    def _throttle(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        now = time.time()
        gap = now - self._last_send_ts
        if gap < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - gap)

    def _post(self, payload: dict) -> bool:
        if not self.webhook_url:
            raise ValueError("WECOM_WEBHOOK_URL 未配置（为空）")

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            resp = requests.post(self.webhook_url, json=payload, timeout=30)
            # 企业微信机器人一般返回 JSON: {"errcode":0,"errmsg":"ok"}
            try:
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"企业微信返回非JSON: status={resp.status_code}, body={resp.text[:300]}") from e

            if resp.status_code == 200 and data.get("errcode") == 0:
                self._last_send_ts = time.time()
                return True

            errcode = data.get("errcode")
            # 45009: api freq out of limit（频率限制）
            if errcode == 45009 and attempt < self.max_retries:
                sleep_s = min(60.0, self.retry_base_seconds * (2 ** attempt))
                time.sleep(sleep_s)
                last_error = RuntimeError(f"企业微信频率限制: resp={data}")
                continue

            raise RuntimeError(f"企业微信发送失败: status={resp.status_code}, resp={data}")

        if last_error:
            raise last_error
        return False

    def send_markdown(self, content: str) -> bool:
        content = (content or "").strip()
        if not content:
            return True
        return self._post(
            {
                "msgtype": "markdown",
                "markdown": {"content": content},
            }
        )

    def send_image_bytes(self, image_bytes: bytes) -> bool:
        if not image_bytes:
            return True
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        md5 = hashlib.md5(image_bytes).hexdigest()
        return self._post({"msgtype": "image", "image": {"base64": b64, "md5": md5}})

