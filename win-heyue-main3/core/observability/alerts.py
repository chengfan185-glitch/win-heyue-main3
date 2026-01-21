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
