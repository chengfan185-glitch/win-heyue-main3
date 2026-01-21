from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np


@dataclass
class Regime4H:
    """Higher-timeframe (4h) regime gate output."""
    regime: str               # UPTREND | DOWNTREND | RANGE
    allowed_actions: List[str] # e.g. ["LONG"] / ["SHORT"] / []
    ema_fast: float
    ema_slow: float
    close: float
    debug: Dict[str, Any]


def _ema(values: np.ndarray, period: int) -> float:
    if len(values) == 0:
        return 0.0
    alpha = 2.0 / (float(period) + 1.0)
    v = float(values[0])
    for x in values[1:]:
        v = alpha * float(x) + (1.0 - alpha) * v
    return float(v)


def classify_regime_4h(
    klines_4h: List[List[Any]],
    ema_fast_period: int = 20,
    ema_slow_period: int = 60,
    swing_lookback_bars: int = 3,
) -> Regime4H:
    """
    Classify 4h regime for trend gating.

    Rules (strict, trend-only):
      - UPTREND: EMA_fast > EMA_slow AND close > EMA_slow AND lows not decreasing (last N bars)
      - DOWNTREND: EMA_fast < EMA_slow AND close < EMA_slow AND highs not increasing (last N bars)
      - else RANGE

    Returns regime + allowed_actions and useful debug fields.
    """
    if not klines_4h or len(klines_4h) < max(ema_slow_period + 5, 80):
        return Regime4H(
            regime="RANGE",
            allowed_actions=[],
            ema_fast=0.0,
            ema_slow=0.0,
            close=float(klines_4h[-1][4]) if klines_4h else 0.0,
            debug={"reason": "insufficient_klines", "n": len(klines_4h) if klines_4h else 0},
        )

    highs = np.array([float(x[2]) for x in klines_4h], dtype=float)
    lows = np.array([float(x[3]) for x in klines_4h], dtype=float)
    closes = np.array([float(x[4]) for x in klines_4h], dtype=float)

    # Use last ~ (ema_slow_period*2) bars for stable EMA
    tail = closes[-(ema_slow_period * 2):]
    ema_fast = _ema(tail, int(ema_fast_period))
    ema_slow = _ema(tail, int(ema_slow_period))
    close = float(closes[-1])

    n = max(2, int(swing_lookback_bars))
    recent_lows = lows[-n:]
    recent_highs = highs[-n:]

    lows_non_decreasing = bool(np.all(np.diff(recent_lows) >= 0.0))
    highs_non_increasing = bool(np.all(np.diff(recent_highs) <= 0.0))

    up = (ema_fast > ema_slow) and (close > ema_slow) and lows_non_decreasing
    dn = (ema_fast < ema_slow) and (close < ema_slow) and highs_non_increasing

    if up:
        regime = "UPTREND"
        allowed = ["LONG"]
        reason = "ema_up_close_above_slow_lows_non_decreasing"
    elif dn:
        regime = "DOWNTREND"
        allowed = ["SHORT"]
        reason = "ema_down_close_below_slow_highs_non_increasing"
    else:
        regime = "RANGE"
        allowed = []
        reason = "no_trend_gate"

    return Regime4H(
        regime=regime,
        allowed_actions=allowed,
        ema_fast=float(ema_fast),
        ema_slow=float(ema_slow),
        close=float(close),
        debug={
            "reason": reason,
            "lows_non_decreasing": lows_non_decreasing,
            "highs_non_increasing": highs_non_increasing,
            "swing_n": n,
        },
    )
