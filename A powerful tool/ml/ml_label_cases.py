# ml/label_cases.py
"""
Labeling utilities for StrategyCase documents.

Provides two sets of rules:
- market rule set: abstracts typical market conditions (trend, volatility, gas spikes, liquidity/TVL flows, APY changes)
- order rule set: derives labels from actual orders/executions present in case documents (order placed, filled, profit realized, slippage, etc.)

These functions are intentionally defensive: they work whether the input case / snapshot / pool features / market / capital are dataclass instances
(from domain.models.market_state) or plain dicts (e.g. read from JSONL or Mongo). Key lookup will try both snake_case and lowerCamelCase keys.

Usage:
- import ml.label_cases
- labels = label_case_doc(case_doc)        # case_doc may be dict or StrategyCase-like
- labels_batch = label_cases(docs_list)
"""
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import math


def _snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:]) if len(parts) > 1 else s


def _get_field(obj: Any, name: str, default=None):
    """
    Safe getter. Works for:
      - dicts: tries name, then lowerCamelCase
      - objects: getattr
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        if name in obj and obj[name] is not None:
            return obj[name]
        camel = _snake_to_camel(name)
        return obj.get(camel, default)
    # object attribute access
    val = getattr(obj, name, None)
    if val is not None:
        return val
    # also try camelCase on object (some dataclasses may use camelCase attrs)
    camel = _snake_to_camel(name)
    return getattr(obj, camel, default)


def _to_float(v, default=0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


# -------------------------
# Market rule set
# -------------------------
def label_market_condition(snapshot: Any,
                           target_pool_id: Optional[str] = None,
                           thresholds: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Produce labels describing the market condition for a given snapshot.

    Returns a dict with keys (example):
      - market_trend: "bull" | "bear" | "sideways"
      - high_volatility: bool
      - gas_spike: bool
      - tvl_outflow: bool
      - apy_spike: bool
      - native_price_change_24h: float (pct)
      - gas_price_gwei: float

    thresholds: optional overrides:
      - volatility_pct: default 0.05  (5% 24h price change considered high)
      - gas_spike_gwei: default 200
      - tvl_outflow_rate: default 0.02 (2%)
      - apy_spike_threshold: default 0.05 (5% relative change)
    """
    thr = {
        "volatility_pct": 0.05,
        "gas_spike_gwei": 200.0,
        "tvl_outflow_rate": 0.02,
        "apy_spike_threshold": 0.05,
    }
    if thresholds:
        thr.update(thresholds)

    # snapshot may be dict or dataclass; support both
    # try get market and capital and pool_features safely
    market = _get_field(snapshot, "market", {})
    capital = _get_field(snapshot, "capital", {})
    pool_features_map = _get_field(snapshot, "pool_features", {}) or {}

    # Market-level signals
    native_price_usd = _to_float(_get_field(market, "native_price_usd", 0.0), 0.0)
    # try to read pct change 24h (may be provided), otherwise attempt to compute from historical fields if available
    native_change_24h = None
    # common keys
    for k in ("native_price_change_24h", "nativePriceChange24h", "native_price_pct_change_24h", "price_change_pct_24h"):
        v = _get_field(market, k, None)
        if v is not None:
            try:
                native_change_24h = float(v)
                break
            except Exception:
                pass
    if native_change_24h is None:
        # fallback: if market carries last_price and price_24h_ago
        last = _to_float(_get_field(market, "native_price_usd", 0.0))
        prev = _to_float(_get_field(market, "native_price_24h_ago", None), None)
        if prev:
            try:
                native_change_24h = (last - prev) / prev
            except Exception:
                native_change_24h = 0.0
        else:
            native_change_24h = 0.0

    high_volatility = abs(native_change_24h) >= thr["volatility_pct"]

    gas_price_gwei = _to_float(_get_field(market, "gas_price_gwei", 0.0))
    gas_spike = gas_price_gwei >= thr["gas_spike_gwei"]

    # Trend: simplistic: if native_change_24h > +volatility_pct -> bull; < -volatility_pct -> bear; else sideways
    if native_change_24h >= thr["volatility_pct"]:
        market_trend = "bull"
    elif native_change_24h <= -thr["volatility_pct"]:
        market_trend = "bear"
    else:
        market_trend = "sideways"

    # Pool-level signals: choose target pool (if None choose highest relative_apy_rank)
    chosen_pf = None
    if pool_features_map:
        if target_pool_id and target_pool_id in pool_features_map:
            chosen_pf = pool_features_map[target_pool_id]
        else:
            # attempt to pick the pool with max relative_apy_rank
            best = None
            best_rank = -math.inf
            for k, v in (pool_features_map.items() if isinstance(pool_features_map, dict) else []):
                rank = _get_field(v, "relative_apy_rank", None)
                try:
                    r = float(rank) if rank is not None else -math.inf
                except Exception:
                    r = -math.inf
                if r > best_rank:
                    best_rank = r
                    best = v
            chosen_pf = best

    tvl_outflow_rate = _to_float(_get_field(chosen_pf, "tvl_outflow_rate", 0.0))
    apy_trend_3h = _to_float(_get_field(chosen_pf, "apy_trend_3h", 0.0))
    apy_spike = abs(apy_trend_3h) >= thr["apy_spike_threshold"]
    tvl_outflow = abs(tvl_outflow_rate) >= thr["tvl_outflow_rate"]

    return {
        "market_trend": market_trend,
        "high_volatility": bool(high_volatility),
        "gas_spike": bool(gas_spike),
        "tvl_outflow": bool(tvl_outflow),
        "apy_spike": bool(apy_spike),
        "native_price_change_24h": float(native_change_24h),
        "gas_price_gwei": float(gas_price_gwei),
        "tvl_outflow_rate": float(tvl_outflow_rate),
        "apy_trend_3h": float(apy_trend_3h),
    }


# -------------------------
# Order rule set
# -------------------------
def label_order_execution(case_doc: Any,
                          look_back_seconds: int = 3600,
                          profit_threshold_usd: float = 1.0) -> Dict[str, Any]:
    """
    Produce labels about actual order behavior in a case document.

    Examines fields commonly present in execution records:
      - 'orders', 'executions', 'filled_orders', 'executionsHistory', etc.
    Returns:
      - order_placed: bool
      - order_filled: bool
      - fill_delay_secs: float | None
      - realized_profit_usd: float | None
      - profit_realized: bool (realized_profit_usd >= profit_threshold_usd)
      - slippage_pct: float | None  (if available)
    """
    # case_doc may be dict or dataclass-like
    # normalize accessors
    orders = _get_field(case_doc, "orders", None) or _get_field(case_doc, "executions", None) or _get_field(case_doc, "filled_orders", None) or []
    target_pool_id = _get_field(case_doc, "target_pool_id", None) or _get_field(case_doc, "targetPoolId", None) or _get_field(case_doc, "snapshot", {}).get("target_pool_id", None) if isinstance(case_doc, dict) else _get_field(case_doc, "target_pool_id", None)
    # If case_doc is StrategyCase, decision may be present on top-level
    decision = _get_field(case_doc, "decision", None)

    order_placed = False
    order_filled = False
    fill_delay_secs = None
    realized_profit_usd = None
    slippage_pct = None

    # Helper to parse time safely
    def _parse_ts(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            # assume epoch seconds
            try:
                return datetime.utcfromtimestamp(float(v))
            except Exception:
                return None
        if isinstance(v, str):
            # try ISO formats
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(v, fmt)
                except Exception:
                    continue
            # last resort: attempt fromisoformat
            try:
                return datetime.fromisoformat(v)
            except Exception:
                return None
        return None

    now = datetime.utcnow()

    # orders may be a dict keyed by pool id or a list of order dicts
    found_orders = []
    if isinstance(orders, dict):
        # if keyed by pool id and contains lists
        if target_pool_id and target_pool_id in orders:
            raw = orders[target_pool_id]
            if isinstance(raw, list):
                found_orders.extend(raw)
            elif isinstance(raw, dict):
                found_orders.append(raw)
        else:
            # flatten dict values
            for v in orders.values():
                if isinstance(v, list):
                    found_orders.extend(v)
                else:
                    found_orders.append(v)
    elif isinstance(orders, list):
        found_orders.extend(orders)
    else:
        # single order-like object
        if orders:
            found_orders.append(orders)

    # scan found_orders for placed/filled matching target_pool_id
    for o in found_orders:
        pool = _get_field(o, "pool_id", None) or _get_field(o, "poolId", None) or _get_field(o, "target_pool_id", None)
        status = (_get_field(o, "status", None) or "").lower()
        created_ts = _parse_ts(_get_field(o, "created_at", None) or _get_field(o, "createdAt", None) or _get_field(o, "timestamp", None))
        filled_ts = _parse_ts(_get_field(o, "filled_at", None) or _get_field(o, "filledAt", None))
        filled = False
        if status in ("filled", "executed", "done", "closed"):
            filled = True
        # some docs indicate filled by presence of filled_at or filled_quantity
        if filled_ts or (_get_field(o, "filled_qty", None) or _get_field(o, "filled_quantity", None)):
            filled = True

        # match pool if available - if no pool criteria, consider all
        if target_pool_id and pool and str(pool) != str(target_pool_id):
            continue

        # found a placed order
        order_placed = True
        if filled:
            order_filled = True
            if created_ts and filled_ts:
                try:
                    fill_delay_secs = (filled_ts - created_ts).total_seconds()
                except Exception:
                    fill_delay_secs = None
            # realized profit may be present on order or case-level
            realized_profit_usd = _get_field(o, "realized_profit_usd", None) or _get_field(o, "profit_usd", None) or realized_profit_usd
            slippage_pct = _get_field(o, "slippage_pct", None) or _get_field(o, "slippage", None) or slippage_pct

    # fallback: look for case-level outcome / result fields
    if realized_profit_usd is None:
        realized_profit_usd = _get_field(case_doc, "realized_profit_usd", None) or _get_field(case_doc, "profit_usd", None) or _get_field(case_doc, "outcome_profit", None)

    try:
        realized_profit_usd = float(realized_profit_usd) if realized_profit_usd is not None else None
    except Exception:
        realized_profit_usd = None

    profit_realized = (realized_profit_usd is not None and realized_profit_usd >= profit_threshold_usd)

    return {
        "order_placed": bool(order_placed),
        "order_filled": bool(order_filled),
        "fill_delay_secs": float(fill_delay_secs) if fill_delay_secs is not None else None,
        "realized_profit_usd": float(realized_profit_usd) if realized_profit_usd is not None else None,
        "profit_realized": bool(profit_realized),
        "slippage_pct": float(slippage_pct) if slippage_pct is not None else None,
        "decision": _get_field(case_doc, "decision", None),
        "target_pool_id": target_pool_id,
    }


# -------------------------
# High-level helpers
# -------------------------
def label_case_doc(case_doc: Any,
                   market_thresholds: Optional[Dict[str, float]] = None,
                   order_profit_threshold: float = 1.0) -> Dict[str, Any]:
    """
    Label a single case document with both market and order rule sets.
    Returns a combined dict with 'market' and 'order' keys.
    """
    # case_doc may be a StrategyCase object with .snapshot or a raw dict with snapshot inside
    snapshot = _get_field(case_doc, "snapshot", case_doc) or case_doc
    market_labels = label_market_condition(snapshot, target_pool_id=_get_field(case_doc, "target_pool_id", None), thresholds=market_thresholds)
    order_labels = label_order_execution(case_doc, profit_threshold_usd=order_profit_threshold)
    combined = {"market": market_labels, "order": order_labels}
    return combined


def label_cases(docs: List[Any],
                market_thresholds: Optional[Dict[str, float]] = None,
                order_profit_threshold: float = 1.0) -> List[Dict[str, Any]]:
    """
    Label a list of case documents. Returns a list of label dicts in same order.
    Each element is the output of label_case_doc.
    """
    out = []
    for d in docs:
        try:
            out.append(label_case_doc(d, market_thresholds, order_profit_threshold))
        except Exception:
            # defensive: ensure a label is returned even on unexpected doc formats
            out.append({"market": {}, "order": {}})
    return out