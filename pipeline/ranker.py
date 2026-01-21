from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Tuple

from features.baseline import Features


def score(f: Features, w_trend: float, w_vol: float, w_breakout: float, w_noise: float) -> float:
    # Normalize vol/noise into soft ranges
    vol_n = min(max(f.vol * 500.0, 0.0), 2.0)  # heuristic scaling
    noise_n = min(max((f.noise - 1.0), 0.0), 5.0) / 5.0

    s = (
        w_trend * f.trend
        + w_vol * vol_n
        + w_breakout * f.breakout
        - w_noise * noise_n
    )
    return float(s)


def rank(features: List[Features], weights: Dict[str, float], topn: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for f in features:
        s = score(f, weights["w_trend"], weights["w_vol"], weights["w_breakout"], weights["w_noise"])
        d = asdict(f)
        d["score"] = s
        rows.append(d)

    rows.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return rows[: max(1, int(topn))]
