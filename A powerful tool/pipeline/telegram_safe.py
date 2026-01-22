"""
Safe Telegram message sender.

- 不使用 parse_mode，避免富文本解析错误
- 清洗控制字符
- 可选截断超长消息
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")

def sanitize_text(text: str, max_len: int = 4096) -> str:
    if text is None:
        return ""
    cleaned = _CONTROL_CHARS.sub("", text)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 20] + "... [message truncated]"
    return cleaned

def _redact_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 12:
        return "***"
    return token[:8] + "..." + token[-4:]

def send_telegram(
    token: str,
    chat_id: str,
    text: str,
    timeout: int = 10,
) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": sanitize_text(text)}
    try:
        resp = requests.post(url, data=payload, timeout=timeout)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("[ALERT ERROR] Failed to send Telegram alert: %s", exc)
        logger.error("[ALERT DEBUG] payload=%s token=%s", payload, _redact_token(token))
        try:
            os.makedirs("logs", exist_ok=True)
            with open("logs/telegram_failed_payloads.log", "a", encoding="utf-8") as fh:
                fh.write(f"ERROR: {exc}\n")
                fh.write(f"payload={payload} token={_redact_token(token)}\n")
        except Exception:
            logger.exception("Failed to write telegram_failed_payloads.log")
        return False

def send_from_env(text: str) -> bool:
    enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    if not enabled:
        return False
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("[ALERT WARN] TELEGRAM_ENABLED=true but token/chat_id missing.")
        return False
    return send_telegram(token, chat_id, text)
