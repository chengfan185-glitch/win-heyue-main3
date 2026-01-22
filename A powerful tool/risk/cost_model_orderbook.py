from __future__ import annotations
"""risk/cost_model_orderbook.py

Order-book based cost model for futures/spot market orders.

Goal
- Provide a *live* fee_estimate_pct (round-trip) even when there are 0 real fills.
- Decompose cost into: fees + spread + impact(slippage).
- Designed to plug into EdgeGate V1/V2 (Runner computes fee_estimate_pct; gates use it).

This module is intentionally self-contained and safe:
- Never raises in normal usage (falls back to configured constants if book is empty).
- Works with Binance depth payload: {"bids": [[price, qty], ...], "asks": ...}.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

Side = Literal["LONG", "SHORT"]


@dataclass
class OrderBookSnap:
    symbol: str
    ts_ms: int
    bids: List[Tuple[float, float]]  # (price, qty)
    asks: List[Tuple[float, float]]  # (price, qty)

    best_bid: float = 0.0
    best_ask: float = 0.0
    mid: float = 0.0

    def finalize(self) -> "OrderBookSnap":
        if self.bids:
            self.best_bid = float(self.bids[0][0])
        if self.asks:
            self.best_ask = float(self.asks[0][0])
        if self.best_bid > 0 and self.best_ask > 0:
            self.mid = (self.best_bid + self.best_ask) / 2.0
        return self


@dataclass
class CostBreakdown:
    # per round-trip (entry + exit)
    fee_rate_effective: float
    fees_pct_roundtrip: float
    half_spread_pct: float
    spread_pct_roundtrip: float
    impact_pct_oneway: float
    impact_pct_roundtrip: float
    total_cost_pct_roundtrip: float


@dataclass
class CostSnapshot:
    symbol: str
    side: Side
    notional_usdt: float
    qty_base_est: float

    ts_ms: int
    best_bid: float
    best_ask: float
    mid: float

    vwap_entry: float
    depth_levels_used: int
    used_fallback: bool
    error: Optional[str]

    breakdown: CostBreakdown

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # flatten breakdown for easier grepping in jsonl
        bd = d.pop("breakdown", {})
        if isinstance(bd, dict):
            for k, v in bd.items():
                d[f"bd_{k}"] = v
        return d


def _parse_levels(raw: Any) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    if not raw:
        return out
    try:
        for lvl in raw:
            if not lvl or len(lvl) < 2:
                continue
            p = float(lvl[0])
            q = float(lvl[1])
            if p > 0 and q > 0:
                out.append((p, q))
    except Exception:
        return out
    return out


def orderbook_from_binance_depth(symbol: str, depth_payload: Dict[str, Any]) -> OrderBookSnap:
    """Build OrderBookSnap from Binance depth payload."""
    ts_ms = int(depth_payload.get("_ts_ms") or 0)
    bids = _parse_levels(depth_payload.get("bids"))
    asks = _parse_levels(depth_payload.get("asks"))
    return OrderBookSnap(symbol=symbol, ts_ms=ts_ms, bids=bids, asks=asks).finalize()


def _vwap_fill(levels: List[Tuple[float, float]], qty_need: float) -> Tuple[float, int, float]:
    """Consume levels until qty is filled.

    Returns (vwap_price, levels_used, qty_filled).
    """
    if qty_need <= 0 or not levels:
        return 0.0, 0, 0.0

    remaining = qty_need
    cost = 0.0
    filled = 0.0
    used = 0

    for price, qty in levels:
        if remaining <= 0:
            break
        take = qty if qty <= remaining else remaining
        cost += take * price
        filled += take
        remaining -= take
        used += 1

    vwap = (cost / filled) if filled > 0 else 0.0
    return vwap, used, filled


def estimate_roundtrip_cost(
    ob: OrderBookSnap,
    *,
    side: Side,
    notional_usdt: float,
    taker_fee_rate: float,
    maker_fee_rate: float,
    expected_taker_ratio: float,
    fallback_total_cost_pct_roundtrip: float = 0.0013,
) -> CostSnapshot:
    """Estimate round-trip cost (entry + exit) in pct-of-notional.

    - Fees: 2 * (p*taker + (1-p)*maker)
    - Spread: (ask-bid)/mid  (crossing twice)
    - Impact: 2 * (VWAP - best)/mid  (one-way impact duplicated for exit)

    If order book is missing/invalid, returns fallback cost.
    """

    # sanitize inputs
    try:
        notional_usdt = float(notional_usdt)
    except Exception:
        notional_usdt = 0.0

    p = min(1.0, max(0.0, float(expected_taker_ratio)))
    fee_rate_effective = p * float(taker_fee_rate) + (1.0 - p) * float(maker_fee_rate)
    fees_pct_roundtrip = 2.0 * fee_rate_effective

    used_fallback = False
    err: Optional[str] = None

    if ob.mid <= 0 or ob.best_bid <= 0 or ob.best_ask <= 0 or not ob.bids or not ob.asks or notional_usdt <= 0:
        used_fallback = True
        total = float(fallback_total_cost_pct_roundtrip)
        bd = CostBreakdown(
            fee_rate_effective=fee_rate_effective,
            fees_pct_roundtrip=fees_pct_roundtrip,
            half_spread_pct=0.0,
            spread_pct_roundtrip=0.0,
            impact_pct_oneway=0.0,
            impact_pct_roundtrip=0.0,
            total_cost_pct_roundtrip=total,
        )
        return CostSnapshot(
            symbol=ob.symbol,
            side=side,
            notional_usdt=notional_usdt,
            qty_base_est=0.0,
            ts_ms=ob.ts_ms,
            best_bid=ob.best_bid,
            best_ask=ob.best_ask,
            mid=ob.mid,
            vwap_entry=0.0,
            depth_levels_used=0,
            used_fallback=True,
            error="orderbook_empty_or_invalid",
            breakdown=bd,
        )

    mid = ob.mid
    qty_base_est = notional_usdt / mid

    # spread
    half_spread_pct = ((ob.best_ask - ob.best_bid) / 2.0) / mid
    spread_pct_roundtrip = 2.0 * half_spread_pct  # cross twice

    # impact (simulate market order)
    if side == "LONG":
        vwap_entry, levels_used, filled = _vwap_fill(ob.asks, qty_base_est)
        # cost if vwap worse than best ask
        impact_oneway = max(0.0, (vwap_entry - ob.best_ask) / mid)
    else:
        vwap_entry, levels_used, filled = _vwap_fill(ob.bids, qty_base_est)
        # selling: vwap may be below best bid
        impact_oneway = max(0.0, (ob.best_bid - vwap_entry) / mid)

    # if cannot fill qty from book, fallback but keep fee and spread
    if filled <= 0 or vwap_entry <= 0:
        used_fallback = True
        err = "insufficient_depth"
        impact_oneway = 0.0
        levels_used = 0

    impact_roundtrip = 2.0 * impact_oneway

    total_cost_pct_roundtrip = fees_pct_roundtrip + spread_pct_roundtrip + impact_roundtrip

    # optional clamp to avoid negative or crazy values due to malformed data
    if total_cost_pct_roundtrip < 0:
        total_cost_pct_roundtrip = float(fallback_total_cost_pct_roundtrip)
        used_fallback = True
        err = "negative_total_clamped"

    bd = CostBreakdown(
        fee_rate_effective=fee_rate_effective,
        fees_pct_roundtrip=fees_pct_roundtrip,
        half_spread_pct=half_spread_pct,
        spread_pct_roundtrip=spread_pct_roundtrip,
        impact_pct_oneway=impact_oneway,
        impact_pct_roundtrip=impact_roundtrip,
        total_cost_pct_roundtrip=total_cost_pct_roundtrip,
    )

    return CostSnapshot(
        symbol=ob.symbol,
        side=side,
        notional_usdt=notional_usdt,
        qty_base_est=qty_base_est,
        ts_ms=ob.ts_ms,
        best_bid=ob.best_bid,
        best_ask=ob.best_ask,
        mid=ob.mid,
        vwap_entry=vwap_entry,
        depth_levels_used=levels_used,
        used_fallback=used_fallback,
        error=err,
        breakdown=bd,
    )


def append_cost_log_jsonl(log_path: str, record: Dict[str, Any]) -> None:
    """Append a single JSON record to a jsonl file, creating directories."""
    try:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # attach canonical timestamp if missing
        if "ts" not in record:
            record["ts"] = datetime.now(timezone.utc).isoformat()
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Logging must never break trading loop
        return
