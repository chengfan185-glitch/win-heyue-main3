# core/risk_manager.py
# RiskManager with detailed close reason logging and configurable timeout (MAX_HOLD_SECONDS env var)
#
# check_stop_conditions returns (should_close: bool, ctx: dict) where ctx contains reason and threshold details.

import os
import time
import logging
from typing import Any, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_HOLD_SECONDS = int(os.getenv("MAX_HOLD_SECONDS", str(24 * 60 * 60)))  # default 1 day


class RiskManager:
    def __init__(self, max_hold_seconds: Optional[int] = None):
        self.max_hold_seconds = max_hold_seconds if max_hold_seconds is not None else _DEFAULT_MAX_HOLD_SECONDS
        logger.info("[RISK] MAX_HOLD_SECONDS=%s", self.max_hold_seconds)
        # trailing stop state could be stored here if implemented
        self._state = {}

    def check_stop_conditions(self, position: Any, market_price: float) -> Tuple[bool, Dict]:
        """
        Return (should_close: bool, ctx: dict)
        ctx includes at least: reason (STOP_LOSS/TAKE_PROFIT/TIMEOUT/NO_ACTION), and relevant thresholds.
        """
        try:
            side = getattr(position, "side", None) or (position.get("side") if isinstance(position, dict) else None)
            opened_at = getattr(position, "opened_at", None) or (position.get("opened_at") if isinstance(position, dict) else None)
            now_ts = int(time.time())
            hold_seconds = (now_ts - int(opened_at)) if opened_at else None

            stop_loss = getattr(position, "stop_loss_price", None) or (position.get("stop_loss_price") if isinstance(position, dict) else None)
            take_profit = getattr(position, "take_profit_price", None) or (position.get("take_profit_price") if isinstance(position, dict) else None)
            trailing_pct = getattr(position, "trailing_stop_pct", None) or (position.get("trailing_stop_pct") if isinstance(position, dict) else None)

            # Timeout check
            if hold_seconds is not None and self.max_hold_seconds is not None and hold_seconds >= self.max_hold_seconds:
                reason = "TIMEOUT"
                ctx = {
                    "reason": reason,
                    "hold_seconds": hold_seconds,
                    "max_hold_seconds": self.max_hold_seconds
                }
                logger.info("[RISK] close triggered reason=%s hold_seconds=%s max_hold_seconds=%s", reason, hold_seconds, self.max_hold_seconds)
                return True, ctx

            # Stop loss
            if stop_loss is not None:
                if isinstance(side, str) and side.upper().startswith("LONG"):
                    if market_price <= stop_loss:
                        reason = "STOP_LOSS"
                        ctx = {"reason": reason, "market_price": market_price, "stop_loss": stop_loss}
                        logger.info("[RISK] close triggered reason=%s market_price=%s stop_loss=%s", reason, market_price, stop_loss)
                        return True, ctx
                else:
                    # SHORT or unspecified: stop when price rises to stop_loss
                    if market_price >= stop_loss:
                        reason = "STOP_LOSS"
                        ctx = {"reason": reason, "market_price": market_price, "stop_loss": stop_loss}
                        logger.info("[RISK] close triggered reason=%s market_price=%s stop_loss=%s", reason, market_price, stop_loss)
                        return True, ctx

            # Take profit
            if take_profit is not None:
                if isinstance(side, str) and side.upper().startswith("LONG"):
                    if market_price >= take_profit:
                        reason = "TAKE_PROFIT"
                        ctx = {"reason": reason, "market_price": market_price, "take_profit": take_profit}
                        logger.info("[RISK] close triggered reason=%s market_price=%s take_profit=%s", reason, market_price, take_profit)
                        return True, ctx
                else:
                    if market_price <= take_profit:
                        reason = "TAKE_PROFIT"
                        ctx = {"reason": reason, "market_price": market_price, "take_profit": take_profit}
                        logger.info("[RISK] close triggered reason=%s market_price=%s take_profit=%s", reason, market_price, take_profit)
                        return True, ctx

            # Trailing stop: placeholder to log configured trailing pct; actual trailing logic requires more state
            if trailing_pct is not None:
                logger.debug("[RISK] trailing_stop_pct configured=%s (actual check to be implemented)", trailing_pct)

            return False, {"reason": "NO_ACTION"}
        except Exception:
            logger.exception("[RISK] check_stop_conditions failed")
            return False, {"reason": "ERROR"}