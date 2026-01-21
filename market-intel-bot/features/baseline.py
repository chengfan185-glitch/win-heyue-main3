from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class Features:
    symbol: str
    trend: float
    vol: float
    breakout: float
    noise: float


def _pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return (a - b) / b


def compute_features(symbol: str, klines: List[List]) -> Features:
    # Kline format: [openTime, open, high, low, close, volume, closeTime, ...]
    closes = np.array([float(k[4]) for k in klines], dtype=float)
    highs = np.array([float(k[2]) for k in klines], dtype=float)
    lows = np.array([float(k[3]) for k in klines], dtype=float)

    if len(closes) < 30:
        return Features(symbol=symbol, trend=0.0, vol=0.0, breakout=0.0, noise=0.0)

    # Trend: recent return vs mid-term return
    r1 = _pct(closes[-1], closes[-5])
    r2 = _pct(closes[-1], closes[-20])
    trend = float(0.6 * r1 + 0.4 * r2)

    # Volatility: std of log returns (last 30)
    rets = np.diff(np.log(closes[-31:]))
    vol = float(np.std(rets))

    # Breakout: close relative to last N high/low
    window = 50 if len(closes) >= 50 else len(closes)
    hh = float(np.max(highs[-window:]))
    ll = float(np.min(lows[-window:]))
    if hh == ll:
        breakout = 0.0
    else:
        breakout = float((closes[-1] - ll) / (hh - ll))  # 0..1
        breakout = breakout * 2 - 1  # -1..+1

    # Noise: wickiness proxy (avg range vs close change)
    ranges = highs[-30:] - lows[-30:]
    body = np.abs(np.diff(closes[-31:]))
    noise = float(np.mean(ranges) / (np.mean(body) + 1e-12))

    return Features(symbol=symbol, trend=trend, vol=vol, breakout=breakout, noise=noise)
