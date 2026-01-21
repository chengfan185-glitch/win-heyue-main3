# core/force_trade.py
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass
class ForceDecision:
    active: bool
    reason: str
    amount_usd: float = 0.0
    bypass_alpha_gate: bool = True
    bypass_ml_gate: bool = True
    # 仅用于日志，不要用它做扣减依据
    remaining_today: int = 0


class ForceTradeController:
    """
    长期可用的“强制成交控制器”
    - 只改 ENV：FORCE_TRADE_QUOTA=N
    - 配额写入 logs/force_quota.json，跨进程/重启生效
    - 默认绕过 AlphaGate/MLGate，但不绕过执行引擎/风控/交易所规则
    """

    def __init__(self, state_file: str = "logs/force_quota.json"):
        self.state_file = Path(state_file)

    @staticmethod
    def _today_key_utc() -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _read_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_state(self, date_key: str, remaining: int) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps({"date": date_key, "remaining": int(remaining)}, ensure_ascii=False),
            encoding="utf-8",
        )

    def remaining_today(self) -> int:
        """
        优先级：
        1) ENV FORCE_TRADE_QUOTA > 0 ：以 ENV 为准，并覆盖写入状态文件（当天）
        2) 否则读取状态文件（当天）
        """
        date_key = self._today_key_utc()

        env_raw = (os.getenv("FORCE_TRADE_QUOTA", "") or "").strip()
        quota_env = 0
        if env_raw != "":
            try:
                quota_env = int(env_raw)
            except Exception:
                quota_env = 0

        # ENV 明确给了 >0：当天配额以 ENV 为准（并覆盖写入）
        if quota_env > 0:
            self._write_state(date_key, quota_env)
            return quota_env

        # ENV 未开启：读状态文件
        st = self._read_state()
        if st.get("date") == date_key:
            try:
                return int(st.get("remaining", 0))
            except Exception:
                return 0

        # 新的一天或状态无效：归零
        self._write_state(date_key, 0)
        return 0

    def plan(
        self,
        *,
        enable_real_trading: bool,
        symbol: str,
        action_name: str,
        order_params: Optional[dict],
    ) -> ForceDecision:
        """
        根据环境变量 + 当前决策状态，判断本次是否启用强制单（只做“计划”，不扣减）。
        """
        if not enable_real_trading:
            return ForceDecision(active=False, reason="real_trading_disabled")

        remaining = self.remaining_today()
        if remaining <= 0:
            return ForceDecision(active=False, reason="quota_empty", remaining_today=remaining)

        # 可选：只在 HOLD 时强制（默认 true，更符合你的语义）
        only_when_hold = (os.getenv("FORCE_ONLY_WHEN_HOLD", "true").lower() == "true")
        if only_when_hold and not (action_name == "HOLD" or not order_params):
            return ForceDecision(active=False, reason="only_when_hold_skip", remaining_today=remaining)

        # 可选：指定币种白名单
        allow_symbols = (os.getenv("FORCE_SYMBOLS", "") or "").strip()
        if allow_symbols:
            allow_set = {s.strip().upper() for s in allow_symbols.split(",") if s.strip()}
            if symbol.upper() not in allow_set:
                return ForceDecision(active=False, reason="symbol_not_in_force_list", remaining_today=remaining)

        amount = float(os.getenv("FORCE_TRADE_AMOUNT", "10") or "10")

        bypass_alpha = (os.getenv("FORCE_BYPASS_ALPHA_GATE", "true").lower() == "true")
        bypass_ml = (os.getenv("FORCE_BYPASS_ML_GATE", "true").lower() == "true")

        return ForceDecision(
            active=True,
            reason="force_planned",
            amount_usd=amount,
            bypass_alpha_gate=bypass_alpha,
            bypass_ml_gate=bypass_ml,
            remaining_today=remaining,
        )

    def consume_one(self) -> int:
        """
        只有在“真实下单成功 / shadow open 成功”后才调用。
        返回扣减后的 remaining。
        """
        date_key = self._today_key_utc()
        st = self._read_state()
        if st.get("date") != date_key:
            # 新的一天：直接归零
            self._write_state(date_key, 0)
            return 0

        try:
            remaining = int(st.get("remaining", 0))
        except Exception:
            remaining = 0

        remaining = max(0, remaining - 1)
        self._write_state(date_key, remaining)
        return remaining
