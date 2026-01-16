from dataclasses import dataclass
import json
import logging
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)

_LEVEL_ORDER: Dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "FATAL": 50,
}


@dataclass
class AlertConfig:
    enabled: bool
    bot_token: Optional[str]
    chat_id: Optional[str]
    level: str = "INFO"


class AlertManager:
    """
    Lightweight alert manager with:
    - send/debug/info/warning/error
    - send_alert(level, title, message, extra)
    - semantic helpers
    """

    def __init__(
        self,
        enabled: bool = True,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        level: str = "INFO",
    ) -> None:
        level = (level or "INFO").upper()
        actually_enabled = bool(enabled and bot_token and chat_id)
        
        if enabled and not actually_enabled:
            logger.warning(
                "[AlertManager] enabled=True but missing bot_token or chat_id, "
                "alerts will be disabled"
            )
        
        self.config = AlertConfig(
            enabled=actually_enabled,
            bot_token=bot_token,
            chat_id=chat_id,
            level=level,
        )

        logger.info(
            "[AlertManager] initialized enabled=%s level=%s chat_id=%s",
            self.config.enabled,
            self.config.level,
            self.config.chat_id,
        )

    def _should_send(self, level: str) -> bool:
        if not self.config.enabled:
            return False
        cur = _LEVEL_ORDER.get(self.config.level, 20)
        incoming = _LEVEL_ORDER.get((level or "INFO").upper(), 20)
        return incoming >= cur

    def _post_telegram(self, text: str) -> None:
        if not (self.config.bot_token and self.config.chat_id):
            logger.debug("[AlertManager] telegram disabled or missing token/chat_id")
            return

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        payload = {"chat_id": self.config.chat_id, "text": text}
        try:
            r = requests.post(url, data=payload, timeout=10)
            r.raise_for_status()
        except Exception as e:
            logger.error("[ALERT ERROR] Failed to send Telegram alert: %s", e)

    def send(self, level: str, text: str) -> None:
        try:
            if not self._should_send(level):
                return
            self._post_telegram(text)
        except Exception as e:
            logger.exception("[AlertManager] unexpected error in send: %s", e)

    def debug(self, text: str) -> None:
        logger.debug(text)
        self.send("DEBUG", text)

    def info(self, text: str) -> None:
        logger.info(text)
        self.send("INFO", text)

    def warning(self, text: str) -> None:
        logger.warning(text)
        self.send("WARNING", text)

    def error(self, text: str) -> None:
        logger.error(text)
        self.send("ERROR", text)

    def send_alert(
        self,
        level,
        title: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            level_name = getattr(level, "name", str(level))
            level_name = (level_name or "INFO").upper()
            prefix = f"[{level_name}] {title}".strip()
            text = prefix
            if message:
                text = f"{prefix}\n\n{message}"

            if extra:
                try:
                    extra_str = json.dumps(extra, ensure_ascii=False, default=str)
                    text += f"\n\n(extra={extra_str})"
                except Exception:
                    pass

            if "ERROR" in level_name or "FATAL" in level_name:
                self.error(text)
            elif "WARN" in level_name or "WARNING" in level_name:
                self.warning(text)
            elif "DEBUG" in level_name:
                self.debug(text)
            else:
                self.info(text)
        except Exception as e:
            logger.exception("[AlertManager] unexpected error in send_alert: %s", e)

    def alert_system_startup(self, trading_mode: str, run_id: str) -> None:
        msg = (
            "[INFO] 交易系统已启动\n\n"
            f"运行模式：{trading_mode}\n"
            f"运行ID：{run_id}"
        )
        self.info(msg)

    def alert_quota_exhausted(self, symbol: str, remaining: int) -> None:
        msg = (
            "[WARNING] Quota Exhausted\n\n"
            f"Daily quota exhausted for {symbol}\n"
            f"Remaining quota (report)：{remaining}"
        )
        self.warning(msg)

    def alert_order_placed(
        self,
        symbol: str,
        side: str,
        size_usd: float,
        entry_price: float,
        trading_mode: str,
    ) -> None:
        msg = (
            "[ORDER] 新订单已提交\n\n"
            f"模式：{trading_mode}\n"
            f"品种：{symbol}\n"
            f"方向：{side}\n"
            f"名义金额：{size_usd:.2f} USDT\n"
            f"入场价：{entry_price}"
        )
        self.info(msg)

    def alert_fatal_error(self, message: str) -> None:
        self.error(f"[FATAL] {message}")
