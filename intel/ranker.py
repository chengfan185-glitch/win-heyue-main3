import os, math
from .features import atr_pct, noise_score, trend_strength

def classify_regime(ts, noise):
    # Defaults are intentionally permissive to avoid an "all-skip" TopN.
    # Tighten via .env once the closed-loop is stable.
    if noise > float(os.getenv("NOISE_MAX", "0.60")):
        return "CHAOS"
    if ts > float(os.getenv("TREND_MIN", "0.0008")):
        return "TREND"
    return "RANGE"

def score_symbol(klines, cost_pct: float, hold_minutes: int):
    atr = atr_pct(klines)
    noise = noise_score(klines)
    ts = trend_strength(klines)

    expected_move = atr * math.sqrt(max(hold_minutes/15, 1.0))
    regime = classify_regime(ts, noise)

    space_ok = expected_move >= float(os.getenv("SPACE_K", "1.10")) * cost_pct
    if regime == "CHAOS" or not space_ok:
        return None

    trend_bonus = 15.0 if regime == "TREND" else 0.0
    edge = 100.0 * (expected_move / max(cost_pct, 1e-6)) - 80.0 * noise + trend_bonus

    why = []
    why.append("space_ok")
    why.append("noise_ok")
    why.append(f"regime_{regime.lower()}")

    return {
        "edge_score": edge,
        "expected_move_pct": expected_move,
        "noise_score": noise,
        "regime": regime,
        "why": why
    }
