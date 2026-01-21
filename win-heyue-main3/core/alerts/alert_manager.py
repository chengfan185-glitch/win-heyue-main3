from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging
import requests
import json
import re

logger = logging.getLogger(__name__)

# ===============================
# 告警等级顺序
# ===============================
_LEVEL_ORDER: Dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "FATAL": 50,
}

# ===============================
# 英文 → 中文 翻译表（统一在这里维护）
# ===============================
_CN_TRANSLATE_MAP: Dict[str, str] = {
    # 通用（短语 / 标签）
    "[INFO]": "【信息】",
    "[WARNING]": "【警告】",
    "[ERROR]": "【错误】",
    "[FATAL]": "【致命错误】",

    # 交易 / 风控
    "Quota Exhausted": "当日下单额度已用完",
    "Daily quota exhausted": "今日交易次数已耗尽",
    "Remaining quota": "剩余下单额度",
    "PAPER OPEN PROBE": "纸上交易｜试探开仓",
    "OPEN PROBE": "试探开仓",

    # 策略 / 样本
    "insufficient_samples_probe_trial": "样本不足，进入试探交易阶段",
    "samples < 50": "样本数量不足 50",
    "samples": "样本",

    # 方向
    "LONG": "做多",
    "SHORT": "做空",

    # 系统状态
    "User interrupt": "用户中断",
    "System Error": "系统错误",
    "System Shutdown": "系统关闭",
    "Trading Error": "交易错误",

    # 其他常见
    "Reason": "原因",
    "Side": "方向",
    "Price": "价格",
    "Qty": "数量",
    "Size": "名义金额",
    "EdgeGate State": "EdgeGate 状态",
    "Mode": "模式",
}

# 字段名替换的正则模式（更鲁棒）
_FIELD_PATTERNS = {
    r"(?m)^\s*Side:\s*(?P<val>\S+)": ("方向：{val}", True),
    r"(?m)^\s*Qty:\s*(?P<val>[\d\.\-eE]+)": ("数量：{val}", True),
    r"(?m)^\s*Price:\s*(?P<val>[\d\.\-eE]+)": ("价格：{val}", True),
    r"(?m)^\s*Size:\s*(?P<val>.+)": ("名义金额：{val}", True),
    r"(?m)^\s*EdgeGate State:\s*(?P<val>.+)": ("EdgeGate 状态：{val}", False),
    r"(?m)^\s*Reason:\s*(?P<val>.+)": ("原因：{val}", False),
    r"(?m)^\s*Quota remaining:\s*(?P<val>\d+)": ("剩余额度：{val}", True),
}

# 方向值映射（用于将 LONG/SHORT 转为中文）
_DIRECTION_MAP = {
    "LONG": "做多",
    "SHORT": "做空",
    "BUY": "买入",
    "SELL": "卖出",
}


# ===============================
# 配置
# ===============================
@dataclass
class AlertConfig:
    enabled: bool
    bot_token: Optional[str]
    chat_id: Optional[str]
    level: str = "INFO"
    lang: str = "zh"  # 语言，用于决定是否做中文本地化（'zh' 表示中文）


class AlertManager:
    """
    中文增强版 AlertManager

    - 保持原有接口不变（runner 无需修改）
    - Telegram 通知自动中文化（基于配置 lang，默认 'zh'）
    - 支持 INFO / WARNING / ERROR / FATAL
    """

    def __init__(
        self,
        enabled: bool = True,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        level: str = "INFO",
        lang: str = "zh",
    ) -> None:
        level = (level or "INFO").upper()
        self.config = AlertConfig(
            enabled=bool(enabled and bot_token and chat_id),
            bot_token=bot_token,
            chat_id=chat_id,
            level=level,
            lang=(lang or "zh"),
        )

        logger.info(
            "[AlertManager] initialized enabled=%s level=%s chat_id=%s lang=%s",
            self.config.enabled,
            self.config.level,
            self.config.chat_id,
            self.config.lang,
        )

    # ===============================
    # 内部工具
    # ===============================
    def _should_send(self, level: str) -> bool:
        if not self.config.enabled:
            return False
        cur = _LEVEL_ORDER.get(self.config.level, 20)
        incoming = _LEVEL_ORDER.get((level or "INFO").upper(), 20)
        return incoming >= cur

    def _translate_cn(self, text: str) -> str:
        """
        将告警文本中的英文关键字替换为中文（仅当配置语言为中文时生效）
        - 支持短语替换与行级字段正则替换
        - 设计为幂等且容错（不抛异常）
        """
        if not text:
            return text

        try:
            lang = (getattr(self.config, "lang", "") or "").lower()
            if not lang.startswith("zh"):
                # 非中文环境，直接返回原文
                return text

            # 先做简单短语替换（覆盖整体标签）
            for k, v in _CN_TRANSLATE_MAP.items():
                if k in text:
                    text = text.replace(k, v)

            # 行级字段替换：使用正则提取值并格式化
            for pattern, (fmt, map_dir) in _FIELD_PATTERNS.items():
                def _repl(m: re.Match) -> str:
                    val = m.groupdict().get("val", "").strip()
                    # 如果需要映射方向词，做额外替换
                    if map_dir:
                        up = val.strip().upper()
                        if up in _DIRECTION_MAP:
                            val_mapped = _DIRECTION_MAP[up]
                        else:
                            val_mapped = val
                    else:
                        # 对一些字段也做简单的中文关键词替换（如 probe reason 中的关键短语）
                        val_mapped = val
                        # 把 val 中的已知英文短语也翻译
                        for ek, ev in _CN_TRANSLATE_MAP.items():
                            if ek in val_mapped:
                                val_mapped = val_mapped.replace(ek, ev)
                        # 特别处理 LONG/SHORT within value
                        val_mapped = re.sub(r"\b(LONG|SHORT|BUY|SELL)\b", lambda mo: _DIRECTION_MAP.get(mo.group(0), mo.group(0)), val_mapped)
                    return fmt.format(val=val_mapped)

                text = re.sub(pattern, _repl, text)

            # 进一步把单词内的 LONG/SHORT 等尽量替换（通用性替换）
            text = re.sub(r"\bLONG\b", _DIRECTION_MAP.get("LONG", "LONG"), text)
            text = re.sub(r"\bSHORT\b", _DIRECTION_MAP.get("SHORT", "SHORT"), text)
            text = re.sub(r"\bBUY\b", _DIRECTION_MAP.get("BUY", "BUY"), text)
            text = re.sub(r"\bSELL\b", _DIRECTION_MAP.get("SELL", "SELL"), text)

            # 清理重复的级别标签（例如 "[INFO] [INFO]" -> keep one）
            text = re.sub(r"(【信息】\s*){2,}", "【信息】", text)
            text = re.sub(r"(【警告】\s*){2,}", "【警告】", text)
            text = re.sub(r"(【错误】\s*){2,}", "【错误】", text)

        except Exception:
            # 本地化必须容错，任何异常直接返回原始文本（或当前已部分翻译文本）
            try:
                logger.exception("[AlertManager] localization error")
            except Exception:
                pass

        return text

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

    # ===============================
    # 基础接口
    # ===============================
    def send(self, level: str, text: str) -> None:
        try:
            if not self._should_send(level):
                return
            text_local = self._translate_cn(text)
            self._post_telegram(text_local)
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

    # ===============================
    # 兼容 runner 的 send_alert
    # ===============================
    def send_alert(
        self,
        level,
        title: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        与 futures_runner_v2.py 中的调用签名兼容，
        对 title/message 做中文化处理（若配置 lang='zh'），并安全发送。
        """
        try:
            level_name = getattr(level, "name", None) or str(level)
            level_name = (level_name or "INFO").upper()

            # 先构建原始文本
            prefix = f"[{level_name}] {title}".strip()
            text = prefix
            if message:
                text = f"{prefix}\n\n{message}"

            # 附加字段（中文化 key）
            if extra:
                try:
                    extra_str = json.dumps(extra, ensure_ascii=False, default=str)
                    text += f"\n\n附加信息：{extra_str}"
                except Exception:
                    # 忽略序列化错误
                    pass

            # 本地化（如果配置为中文）
            text_local = self._translate_cn(text)

            # 路由到合适的记录/发送方法（这些方法本身会再次调用 send -> _post_telegram）
            if "ERROR" in level_name or "FATAL" in level_name:
                # 注意：error() 会再次调用 send("ERROR", text) -> _post_telegram
                self.error(text_local)
            elif "WARN" in level_name or "WARNING" in level_name:
                self.warning(text_local)
            elif "DEBUG" in level_name:
                self.debug(text_local)
            else:
                self.info(text_local)

        except Exception as e:
            logger.exception("[AlertManager] unexpected error in send_alert: %s", e)

    # ===============================
    # 语义告警（业务级）
    # ===============================
    def alert_system_startup(self, trading_mode: str, run_id: str) -> None:
        msg = (
            "【系统启动】\n\n"
            f"运行模式：{trading_mode}\n"
            f"运行ID：{run_id}"
        )
        self.info(msg)

    def alert_quota_exhausted(self, symbol: str, remaining: int) -> None:
        msg = (
            "【风险提示｜当日额度已用完】\n\n"
            f"交易对：{symbol}\n"
            f"今日剩余下单次数：{remaining}\n\n"
            "系统已自动停止该交易对的新开仓操作"
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
        # 尽量把 side 翻译成中文
        side_text = _DIRECTION_MAP.get((side or "").upper(), side)
        msg = (
            "【新订单已提交】\n\n"
            f"交易模式：{trading_mode}\n"
            f"交易对：{symbol}\n"
            f"方向：{side_text}\n"
            f"名义金额：{size_usd:.2f} USDT\n"
            f"入场价格：{entry_price}"
        )
        self.info(msg)

    def alert_fatal_error(self, message: str) -> None:
        self.error(f"【致命错误】{message}")

    def alert_system_shutdown(self, reason: str = "未知原因") -> None:
        """系统关闭通知"""
        msg = (
            "【系统关闭】\n\n"
            f"关闭原因：{self._translate_cn(reason)}\n"
            f"关闭时间：{self._get_current_time()}"
        )
        self.warning(msg)

    def _get_current_time(self) -> str:
        """获取当前时间的格式化字符串"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")