# core/alerts/alert_manager.py
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# 等级顺序，用于过滤
_LEVEL_ORDER: Dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


@dataclass
class AlertConfig:
    enabled: bool
    bot_token: Optional[str]
    chat_id: Optional[str]
    level: str = "INFO"


class AlertManager:
    """
    Telegram 告警封装

    - 支持等级过滤（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    - 支持基础 send() / debug() / info() / warning() / error()
    - 提供统一 send_alert() 入口，兼容 futures_runner_v2.py 的调用
    - 提供高层语义接口：alert_system_startup / alert_quota_exhausted / alert_order_placed / alert_fatal_error
    - 提供额外语义接口：alert_order_failed / alert_reconciliation_failed / alert_system_shutdown
    - 确保所有异常都被捕获，不传播到调用方
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        level: str = "INFO",
    ) -> None:
        # Load from environment if not provided
        if enabled is None:
            enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
        if bot_token is None:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if chat_id is None:
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        level = (level or "INFO").upper()
        self.config = AlertConfig(
            enabled=bool(enabled and bot_token and chat_id),
            bot_token=bot_token,
            chat_id=chat_id,
            level=level,
        )

        logger.info(
            "[AlertManager] enabled=%s level=%s chat_id=%s",
            self.config.enabled,
            self.config.level,
            self.config.chat_id,
        )

    # ------------ 内部工具 ------------

    def _should_send(self, level_name: str) -> bool:
        if not self.config.enabled:
            return False
        cur = _LEVEL_ORDER.get(self.config.level.upper(), 20)
        incoming = _LEVEL_ORDER.get(level_name.upper(), 20)
        return incoming >= cur

    def _post_telegram(self, text: str) -> None:
        """Post message to Telegram. All exceptions are caught and logged."""
        if not (self.config.bot_token and self.config.chat_id):
            return

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            # 纯文本，不使用 parse_mode，避免 400
            "text": text[:4096],  # Telegram limit
        }
        try:
            r = requests.post(url, data=payload, timeout=10)
            r.raise_for_status()
        except Exception as e:
            # Never propagate exceptions to caller
            logger.error("[ALERT ERROR] Failed to send Telegram alert: %s", e)

    # ------------ 基础接口 ------------

    def send(self, level: AlertLevel | str, text: str) -> None:
        """
        底层发送接口：支持 AlertLevel 或字符串
        确保异常不传播到调用方
        """
        try:
            if isinstance(level, AlertLevel):
                level_name = level.value
            else:
                level_name = str(level).upper()

            if not self._should_send(level_name):
                return

            self._post_telegram(text)
        except Exception as e:
            logger.error("[AlertManager.send] Unexpected error: %s", e)

    def debug(self, text: str) -> None:
        """Send DEBUG level alert"""
        try:
            self.send(AlertLevel.DEBUG, text)
        except Exception as e:
            logger.error("[AlertManager.debug] Error: %s", e)

    def info(self, text: str) -> None:
        """Send INFO level alert"""
        try:
            self.send(AlertLevel.INFO, text)
        except Exception as e:
            logger.error("[AlertManager.info] Error: %s", e)

    def warning(self, text: str) -> None:
        """Send WARNING level alert"""
        try:
            self.send(AlertLevel.WARNING, text)
        except Exception as e:
            logger.error("[AlertManager.warning] Error: %s", e)

    def error(self, text: str) -> None:
        """Send ERROR level alert"""
        try:
            self.send(AlertLevel.ERROR, text)
        except Exception as e:
            logger.error("[AlertManager.error] Error: %s", e)

    # ------------ 统一告警出口（兼容 runner 调用）------------

    def send_alert(
        self,
        level: AlertLevel | str,
        title: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        统一告警出口，兼容 futures_runner_v2.py 中的 alerts.send_alert(...)

        - level: AlertLevel 枚举或 "INFO"/"WARNING"/"ERROR" 等字符串
        - title: 简短标题
        - message: 详细内容
        - extra: 附加信息（dict），仅用于日志打印
        
        确保异常不传播到调用方
        """
        try:
            if isinstance(level, AlertLevel):
                level_name = level.value
            else:
                level_name = str(level).upper()
            if level_name not in _LEVEL_ORDER:
                level_name = "INFO"

            prefix = f"[{level_name}] {title}"

            # 控制台兜底打印一份（即使 Telegram 掉线也能看到）
            print(f"{prefix} - {message}")
            if extra:
                try:
                    extra_str = json.dumps(extra, ensure_ascii=False)[:800]
                    print(f"{prefix} extra={extra_str}")
                except Exception:
                    logger.exception("Failed to dump alert extra payload")

            text = f"{prefix}\n\n{message}"
            self.send(level_name, text)
        except Exception as e:
            logger.error("[AlertManager.send_alert] Unexpected error: %s", e)

    # ------------ 语义封装（供 runner 调用）------------

    def alert_system_startup(self, trading_mode: str, run_id: str) -> None:
        """
        交易系统启动通知：
        - 运行模式（paper/testnet/live）
        - run_id
        """
        try:
            msg = (
                "[INFO] 交易系统已启动\n\n"
                f"运行模式：{trading_mode}\n"
                f"运行ID： {run_id}"
            )
            self.info(msg)
        except Exception as e:
            logger.error("[alert_system_startup] Error: %s", e)

    def alert_quota_exhausted(self, symbol: str, remaining: int) -> None:
        """
        某个品种当日 quota 用完
        """
        try:
            msg = (
                "[WARNING] Quota Exhausted\n\n"
                f"Daily quota exhausted for {symbol}\n"
                f"Remaining quota (report)：{remaining}"
            )
            self.warning(msg)
        except Exception as e:
            logger.error("[alert_quota_exhausted] Error: %s", e)

    def alert_order_placed(
        self,
        symbol: str,
        side: str,
        size_usd: float,
        entry_price: float,
        trading_mode: str,
    ) -> None:
        """
        下单成功通知（paper / testnet / live 通用）
        """
        try:
            msg = (
                "[ORDER] 新订单已提交\n\n"
                f"模式：{trading_mode}\n"
                f"品种：{symbol}\n"
                f"方向：{side}\n"
                f"名义金额：{size_usd:.2f} USDT\n"
                f"入场价：{entry_price}"
            )
            self.info(msg)
        except Exception as e:
            logger.error("[alert_order_placed] Error: %s", e)

    def alert_fatal_error(self, message: str) -> None:
        """
        致命错误通知
        """
        try:
            self.error(f"[FATAL] {message}")
        except Exception as e:
            logger.error("[alert_fatal_error] Error: %s", e)

    def alert_order_failed(self, symbol: str, error_msg: str) -> None:
        """
        订单失败通知
        """
        try:
            msg = (
                "[ERROR] 订单失败\n\n"
                f"品种：{symbol}\n"
                f"错误：{error_msg}"
            )
            self.error(msg)
        except Exception as e:
            logger.error("[alert_order_failed] Error: %s", e)

    def alert_reconciliation_failed(self, report: str) -> None:
        """
        对账失败通知
        """
        try:
            msg = f"[WARNING] Reconciliation Issues\n\n{report}"
            self.warning(msg)
        except Exception as e:
            logger.error("[alert_reconciliation_failed] Error: %s", e)

    def alert_system_shutdown(self, reason: str) -> None:
        """
        系统关闭通知
        """
        try:
            msg = f"[INFO] System Shutdown\n\n原因：{reason}"
            self.info(msg)
        except Exception as e:
            logger.error("[alert_system_shutdown] Error: %s", e)
