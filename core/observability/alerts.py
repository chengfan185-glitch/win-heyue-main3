"""
Alert & notification utilities.

设计目标：
- 本地日志 + 统一等级 (INFO/WARNING/ERROR)
- 可选推送 Telegram（通过 pipeline.telegram_safe 封装）
- 作为轻量依赖，不影响核心交易逻辑
"""

from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass
from typing import Optional

from pipeline.telegram_safe import send_from_env

logger = logging.getLogger(__name__)


class AlertLevel(enum.IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass
class AlertConfig:
    enabled: bool = True
    min_level: AlertLevel = AlertLevel.INFO

    @classmethod
    def from_env(cls) -> "AlertConfig":
        enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
        level_str = os.getenv("TELEGRAM_ALERT_LEVEL", "INFO").upper()
        try:
            lvl = AlertLevel[level_str]
        except KeyError:
            lvl = AlertLevel.INFO
        return cls(enabled=enabled, min_level=lvl)


class AlertManager:
    """
    统一的告警管理器。
    """

    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or AlertConfig.from_env()

    def _should_notify(self, level: AlertLevel) -> bool:
        return level >= self.config.min_level

    def _log_local(self, level: AlertLevel, message: str):
        if level >= AlertLevel.CRITICAL:
            logger.critical(message)
        elif level >= AlertLevel.ERROR:
            logger.error(message)
        elif level >= AlertLevel.WARNING:
            logger.warning(message)
        elif level >= AlertLevel.INFO:
            logger.info(message)
        else:
            logger.debug(message)

    def send(self, level: AlertLevel, message: str, *, also_console: bool = True) -> bool:
        """
        发送告警。
        - 永远写入本地 logger
        - 当启用并达到等级时再尝试 Telegram
        """
        if also_console:
            self._log_local(level, message)

        if not self.config.enabled or not self._should_notify(level):
            return False

        prefix = {
            AlertLevel.DEBUG: "[DEBUG]",
            AlertLevel.INFO: "[INFO]",
            AlertLevel.WARNING: "[WARNING]",
            AlertLevel.ERROR: "[ERROR]",
            AlertLevel.CRITICAL: "[CRITICAL]",
        }.get(level, "[INFO]")

        text = f"{prefix} {message}"
        return send_from_env(text)

    # 便捷方法
    def info(self, msg: str) -> bool:
        return self.send(AlertLevel.INFO, msg)

    def warning(self, msg: str) -> bool:
        return self.send(AlertLevel.WARNING, msg)

    def error(self, msg: str) -> bool:
        return self.send(AlertLevel.ERROR, msg)

    def critical(self, msg: str) -> bool:
        return self.send(AlertLevel.CRITICAL, msg)

    # Semantic helper methods for runner compatibility
    def alert_system_startup(self, trading_mode: str, run_id: str) -> bool:
        """System startup notification"""
        msg = (
            "交易系统已启动\n"
            f"运行模式：{trading_mode}\n"
            f"运行ID：{run_id}"
        )
        return self.info(msg)

    def alert_quota_exhausted(self, symbol: str, remaining: int) -> bool:
        """Daily quota exhausted notification"""
        msg = (
            f"Daily quota exhausted for {symbol}\n"
            f"Remaining quota：{remaining}"
        )
        return self.warning(msg)

    def alert_order_placed(
        self,
        symbol: str,
        side: str,
        size_usd: float,
        entry_price: float,
        trading_mode: str,
    ) -> bool:
        """Order placement notification"""
        msg = (
            "新订单已提交\n"
            f"模式：{trading_mode}\n"
            f"品种：{symbol}\n"
            f"方向：{side}\n"
            f"名义金额：{size_usd:.2f} USDT\n"
            f"入场价：{entry_price}"
        )
        return self.info(msg)

    def alert_fatal_error(self, message: str) -> bool:
        """Fatal error notification"""
        return self.critical(f"[FATAL] {message}")

    def alert_order_failed(self, symbol: str, error_msg: str) -> bool:
        """Order failure notification"""
        msg = f"订单失败 - {symbol}\n错误：{error_msg}"
        return self.error(msg)

    def alert_reconciliation_failed(self, report: str) -> bool:
        """Reconciliation failure notification"""
        msg = f"对账失败\n{report}"
        return self.error(msg)

    def alert_system_shutdown(self, reason: str) -> bool:
        """System shutdown notification"""
        msg = f"交易系统关闭\n原因：{reason}"
        return self.warning(msg)

    def send_alert(
        self,
        level,
        title: str,
        message: str,
        extra: Optional[dict] = None,
    ) -> bool:
        """
        Unified alert API compatible with runner expectations.
        Accepts enum or string level.
        """
        try:
            # Convert level to AlertLevel if it's a string or other enum
            if hasattr(level, "name"):
                level_name = level.name
            else:
                level_name = str(level).upper()

            # Map to our AlertLevel
            level_map = {
                "DEBUG": AlertLevel.DEBUG,
                "INFO": AlertLevel.INFO,
                "WARNING": AlertLevel.WARNING,
                "WARN": AlertLevel.WARNING,
                "ERROR": AlertLevel.ERROR,
                "CRITICAL": AlertLevel.CRITICAL,
                "FATAL": AlertLevel.CRITICAL,
            }
            alert_level = level_map.get(level_name, AlertLevel.INFO)

            # Format message
            text = f"{title}\n{message}" if message else title
            return self.send(alert_level, text, also_console=True)
        except Exception as e:
            logger.exception(f"Failed to send alert: {e}")
            return False
