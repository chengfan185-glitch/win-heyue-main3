# risk/implementations/futures_risk.py
"""
Futures Risk Manager
Handles risk management for futures trading with leverage
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any, Literal
import os


# ============================================
# Data Models
# ============================================

@dataclass
class FuturesPosition:
    """Represents a futures position"""
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: float
    entry_price: float
    current_price: float
    leverage: int
    margin_type: Literal["ISOLATED", "CROSSED"]
    unrealized_pnl: float
    unrealized_pnl_pct: float
    liquidation_price: Optional[float] = None

    # Stop loss and take profit
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None

    # Trailing stop
    trailing_stop_pct: Optional[float] = None
    highest_price_since_entry: Optional[float] = None  # For trailing stop (LONG uses highest, SHORT uses lowest)


@dataclass
class FuturesRiskConfig:
    """Risk management configuration for futures"""
    max_leverage: int = 2  # Default 2x
    default_margin_type: Literal["ISOLATED", "CROSSED"] = "ISOLATED"

    # Stop loss / Take profit
    stop_loss_pct: float = 0.02       # 2% loss
    take_profit_pct: float = 0.04     # 4% profit
    enable_trailing_stop: bool = True
    trailing_stop_pct: float = 0.015  # 1.5% trailing

    # Position size limits
    max_position_pct: float = 0.40        # Max 40% of capital per position (notional approximation)
    max_total_exposure_pct: float = 0.80  # Max 80% total exposure

    # Loss limits
    max_single_loss_pct: float = 0.05  # Max 5% loss per trade
    max_daily_loss_pct: float = 0.15   # Max 15% daily loss

    # Anti-flip protection
    enable_anti_flip: bool = True
    anti_flip_candles_wait: int = 1


# ============================================
# Risk Manager
# ============================================

class FuturesRiskManager:
    """
    Risk management for futures trading with:
    - Stop loss / Take profit (price-based)
    - Trailing stop
    - Position size limits
    - Anti-flip logic (close first, wait, then open opposite)
    """

    def __init__(self, config: Optional[FuturesRiskConfig] = None):
        self.config = config or self._load_config_from_env()
        self._positions: Dict[str, FuturesPosition] = {}
        self._last_close_times: Dict[str, datetime] = {}
        self._daily_pnl: float = 0.0
        self._daily_pnl_date: str = ""

    @staticmethod
    def _load_config_from_env() -> FuturesRiskConfig:
        """Load risk configuration from environment variables"""
        return FuturesRiskConfig(
            max_leverage=int(os.getenv("MAX_LEVERAGE", "2")),
            default_margin_type=os.getenv("MARGIN_TYPE", "ISOLATED").upper(),
            stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.02")),
            take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.04")),
            enable_trailing_stop=os.getenv("ENABLE_TRAILING_STOP", "true").lower() == "true",
            trailing_stop_pct=float(os.getenv("TRAILING_STOP_PCT", "0.015")),
            max_position_pct=float(os.getenv("MAX_POSITION_PCT", "0.40")),
            max_total_exposure_pct=float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.80")),
            max_single_loss_pct=float(os.getenv("MAX_SINGLE_LOSS_PCT", "0.05")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.15")),
            enable_anti_flip=os.getenv("ENABLE_ANTI_FLIP", "true").lower() == "true",
            anti_flip_candles_wait=int(os.getenv("ANTI_FLIP_CANDLES_WAIT", "1")),
        )

    def check_can_open_position(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        size_usd: float,
        account_balance: float,
        leverage: int,
        entry_price: Optional[float] = None,   # NEW: 用于正确计算 TP/SL
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Check if we can open a new position

        Returns:
            (allowed, reason, adjusted_params)

        Notes:
        - 风控层不应该把 size_usd 当价格使用
        - TP/SL 只能基于 entry_price 计算（若 entry_price 未提供，则不计算价格）
        """
        current_time = current_time or datetime.now(timezone.utc)

        # 1. Anti-flip logic (minimal, do not break existing behavior)
        if self.config.enable_anti_flip:
            if symbol in self._last_close_times:
                if symbol in self._positions:
                    last_side = self._positions[symbol].side
                    if last_side != side:
                        return (False, "anti_flip_protection", None)

        # 2. Leverage limit
        if leverage > self.config.max_leverage:
            return (False, f"leverage_too_high_max_{self.config.max_leverage}x", None)

        # 3. Position size vs account (notional approx)
        if account_balance <= 0:
            return (False, "invalid_account_balance", None)

        position_pct = (size_usd * leverage) / account_balance
        if position_pct > self.config.max_position_pct:
            max_size = (self.config.max_position_pct * account_balance) / max(leverage, 1)
            return (False, "position_size_too_large", {"adjusted_size_usd": max_size})

        # 4. Total exposure
        total_exposure = sum(
            abs(pos.quantity * pos.current_price * pos.leverage)
            for pos in self._positions.values()
        )
        new_exposure = total_exposure + (size_usd * leverage)
        exposure_pct = new_exposure / account_balance
        if exposure_pct > self.config.max_total_exposure_pct:
            return (False, "total_exposure_limit", None)

        # 5. Daily loss limit
        self._update_daily_pnl(current_time)
        if self._daily_pnl < 0:
            daily_loss_pct = abs(self._daily_pnl) / account_balance
            if daily_loss_pct >= self.config.max_daily_loss_pct:
                return (False, "daily_loss_limit_reached", None)

        # 6. Calculate stop loss and take profit prices (ONLY if entry_price is provided)
        stop_loss_price: Optional[float] = None
        take_profit_price: Optional[float] = None

        if entry_price is not None and entry_price > 0:
            if side == "LONG":
                stop_loss_price = entry_price * (1 - self.config.stop_loss_pct)
                take_profit_price = entry_price * (1 + self.config.take_profit_pct)
            else:  # SHORT
                stop_loss_price = entry_price * (1 + self.config.stop_loss_pct)
                take_profit_price = entry_price * (1 - self.config.take_profit_pct)

        return (True, "ok", {
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "stop_loss_pct": self.config.stop_loss_pct,
            "take_profit_pct": self.config.take_profit_pct,
            "leverage": min(leverage, self.config.max_leverage),
            "margin_type": self.config.default_margin_type
        })

    def update_position(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        quantity: float,
        entry_price: float,
        current_price: float,
        leverage: int,
        margin_type: Literal["ISOLATED", "CROSSED"],
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> FuturesPosition:
        """Update or create a position"""
        unrealized_pnl = 0.0
        if side == "LONG":
            unrealized_pnl = (current_price - entry_price) * quantity
        else:  # SHORT
            unrealized_pnl = (entry_price - current_price) * quantity

        denom = (entry_price * quantity) if quantity > 0 and entry_price > 0 else 0.0
        unrealized_pnl_pct = (unrealized_pnl / denom) if denom > 0 else 0.0

        position = FuturesPosition(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            leverage=leverage,
            margin_type=margin_type,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=self.config.trailing_stop_pct if self.config.enable_trailing_stop else None,
            highest_price_since_entry=current_price,  # LONG uses highest, SHORT uses lowest (we reuse the same field)
        )

        self._positions[symbol] = position
        return position

    def check_stop_conditions(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Check if stop loss or take profit conditions are hit

        Returns:
            (should_close, reason, close_params)
        """
        if symbol not in self._positions:
            return (False, "no_position", None)

        pos = self._positions[symbol]
        pos.current_price = current_price

        # Recalculate PnL
        if pos.side == "LONG":
            pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
        else:
            pos.unrealized_pnl = (pos.entry_price - current_price) * pos.quantity

        denom = (pos.entry_price * pos.quantity) if pos.quantity > 0 and pos.entry_price > 0 else 0.0
        pos.unrealized_pnl_pct = (pos.unrealized_pnl / denom) if denom > 0 else 0.0

        # 1. Stop loss
        if pos.stop_loss_price:
            if pos.side == "LONG" and current_price <= pos.stop_loss_price:
                return (True, "stop_loss", {"price": current_price})
            elif pos.side == "SHORT" and current_price >= pos.stop_loss_price:
                return (True, "stop_loss", {"price": current_price})

        # 2. Take profit
        if pos.take_profit_price:
            if pos.side == "LONG" and current_price >= pos.take_profit_price:
                return (True, "take_profit", {"price": current_price})
            elif pos.side == "SHORT" and current_price <= pos.take_profit_price:
                return (True, "take_profit", {"price": current_price})

        # 3. Trailing stop
        if self.config.enable_trailing_stop and pos.trailing_stop_pct:
            if pos.side == "LONG":
                # highest
                if pos.highest_price_since_entry is None or current_price > pos.highest_price_since_entry:
                    pos.highest_price_since_entry = current_price

                if pos.highest_price_since_entry and pos.highest_price_since_entry > 0:
                    drop_pct = (pos.highest_price_since_entry - current_price) / pos.highest_price_since_entry
                    if drop_pct >= pos.trailing_stop_pct:
                        return (True, "trailing_stop", {
                            "price": current_price,
                            "highest_price": pos.highest_price_since_entry
                        })
            else:  # SHORT: use lowest (stored in highest_price_since_entry)
                if pos.highest_price_since_entry is None or current_price < pos.highest_price_since_entry:
                    pos.highest_price_since_entry = current_price

                if pos.highest_price_since_entry and pos.highest_price_since_entry > 0:
                    rise_pct = (current_price - pos.highest_price_since_entry) / pos.highest_price_since_entry
                    if rise_pct >= pos.trailing_stop_pct:
                        return (True, "trailing_stop", {
                            "price": current_price,
                            "lowest_price": pos.highest_price_since_entry
                        })

        # 4. Max single loss
        loss_pct = abs(pos.unrealized_pnl_pct)
        if pos.unrealized_pnl < 0 and loss_pct >= self.config.max_single_loss_pct:
            return (True, "max_loss_limit", {"loss_pct": loss_pct})

        return (False, "holding", None)

    def close_position(
        self,
        symbol: str,
        close_price: float,
        realized_pnl: float,
        close_time: Optional[datetime] = None
    ) -> None:
        """Close a position and update tracking"""
        close_time = close_time or datetime.now(timezone.utc)

        if symbol in self._positions:
            self._update_daily_pnl(close_time)
            self._daily_pnl += realized_pnl
            self._last_close_times[symbol] = close_time
            del self._positions[symbol]

    def clear_anti_flip_restriction(self, symbol: str) -> None:
        """Manually clear anti-flip restriction (e.g., after N candles)"""
        if symbol in self._last_close_times:
            del self._last_close_times[symbol]

    def _update_daily_pnl(self, current_time: datetime) -> None:
        """Reset daily PnL if it's a new day"""
        current_date = current_time.strftime("%Y-%m-%d")
        if self._daily_pnl_date != current_date:
            self._daily_pnl = 0.0
            self._daily_pnl_date = current_date

    def get_position(self, symbol: str) -> Optional[FuturesPosition]:
        """Get position for a symbol"""
        return self._positions.get(symbol)

    def get_all_positions(self) -> Dict[str, FuturesPosition]:
        """Get all positions"""
        return self._positions.copy()

    def get_risk_summary(self, account_balance: float) -> Dict[str, Any]:
        """Get risk summary"""
        total_exposure = sum(
            abs(pos.quantity * pos.current_price * pos.leverage)
            for pos in self._positions.values()
        )
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in self._positions.values())

        return {
            "num_positions": len(self._positions),
            "total_exposure_usd": total_exposure,
            "exposure_pct": total_exposure / account_balance if account_balance > 0 else 0,
            "total_unrealized_pnl": total_unrealized_pnl,
            "daily_pnl": self._daily_pnl,
            "daily_pnl_pct": self._daily_pnl / account_balance if account_balance > 0 else 0,
            "positions": {
                sym: {
                    "side": pos.side,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_pct": pos.unrealized_pnl_pct,
                    "stop_loss_price": pos.stop_loss_price,
                    "take_profit_price": pos.take_profit_price,
                }
                for sym, pos in self._positions.items()
            }
        }
