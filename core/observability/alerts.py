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

    # ------------ 兼容 futures_runner_v2.py 的 send_alert 接口 ------------
    def send_alert(
        self,
        level,
        title: str,
        message: str,
        extra: Optional[dict] = None,
    ) -> None:
        """
        兼容 futures_runner_v2.py 调用：
          alerts.send_alert(AlertLevel.ERROR, "System Error", "XXX", extra_info)

        - level: 可以是 AlertLevel 枚举，或者字符串
        - title, message: 文本
        - extra: 可选字典，会被忽略（不抛异常）
        
        此方法不抛异常，确保告警失败不会中断主流程
        """
        try:
            # Handle level - could be AlertLevel enum or string
            if isinstance(level, AlertLevel):
                level_val = level
            elif isinstance(level, str):
                level_name = level.upper()
                try:
                    level_val = AlertLevel[level_name]
                except KeyError:
                    level_val = AlertLevel.INFO
            elif hasattr(level, "name"):
                # Handle enum-like objects with .name attribute
                level_name = str(level.name).upper()
                try:
                    level_val = AlertLevel[level_name]
                except KeyError:
                    level_val = AlertLevel.INFO
            else:
                level_val = AlertLevel.INFO

            # Combine title and message
            prefix = f"[{level_val.name}] {title}".strip()
            text = prefix
            if message:
                text = f"{prefix}\n\n{message}"

            # Send the alert
            self.send(level_val, text)
        except Exception as e:
            # Never raise exceptions to calling code
            logger.exception("[AlertManager] unexpected error in send_alert: %s", e)

    # ------------ 语义封装方法（供 runner 调用）------------
    def alert_system_startup(self, trading_mode: str, run_id: str) -> None:
        """交易系统启动通知"""
        try:
            msg = (
                "[INFO] 交易系统已启动\n\n"
                f"运行模式：{trading_mode}\n"
                f"运行ID：{run_id}"
            )
            self.info(msg)
        except Exception as e:
            logger.exception("[AlertManager] error in alert_system_startup: %s", e)

    def alert_quota_exhausted(self, symbol: str, remaining: int) -> None:
        """某个品种当日 quota 用完"""
        try:
            msg = (
                "[WARNING] Quota Exhausted\n\n"
                f"Daily quota exhausted for {symbol}\n"
                f"Remaining quota (report)：{remaining}"
            )
            self.warning(msg)
        except Exception as e:
            logger.exception("[AlertManager] error in alert_quota_exhausted: %s", e)

    def alert_order_placed(
        self,
        symbol: str,
        side: str,
        size_usd: float,
        entry_price: float,
        trading_mode: str,
    ) -> None:
        """下单成功通知"""
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
            logger.exception("[AlertManager] error in alert_order_placed: %s", e)

    def alert_fatal_error(self, message: str) -> None:
        """致命错误通知"""
        try:
            self.error(f"[FATAL] {message}")
        except Exception as e:
            logger.exception("[AlertManager] error in alert_fatal_error: %s", e)

    def alert_order_failed(self, symbol: str, error_msg: str) -> None:
        """订单失败通知"""
        try:
            msg = f"[ORDER FAILED] {symbol}\n\nError: {error_msg}"
            self.error(msg)
        except Exception as e:
            logger.exception("[AlertManager] error in alert_order_failed: %s", e)

    def alert_reconciliation_failed(self, report: str) -> None:
        """对账失败通知"""
        try:
            msg = f"[RECONCILIATION] Failed\n\n{report}"
            self.warning(msg)
        except Exception as e:
            logger.exception("[AlertManager] error in alert_reconciliation_failed: %s", e)

    def alert_system_shutdown(self, reason: str) -> None:
        """系统关闭通知"""
        try:
            msg = f"[SHUTDOWN] System shutting down\n\nReason: {reason}"
            self.warning(msg)
        except Exception as e:
            logger.exception("[AlertManager] error in alert_system_shutdown: %s", e)
