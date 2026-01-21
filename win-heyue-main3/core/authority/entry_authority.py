from __future__ import annotations

"""EntryAuthority: 3D-Bound Executor authorization.

The execution bot does NOT perform market judgment. It only:
1) reads Intel/Strategy outputs
2) validates authorization: Time-Bound, Space-Bound, Direction-Bound
3) returns an executable entry instruction (LONG/SHORT/HOLD)

This module is intentionally permissive in parsing Intel payloads to fit multiple
Market-Intel-Bot output formats.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _bool_env(key: str, default: bool = False) -> bool:
    return str(os.getenv(key, "true" if default else "false")).lower() in ("1", "true", "yes")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_ts(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val.astimezone(timezone.utc)
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(val, str):
        s = val.strip()
        # Accept '2026-01-21T10:22:32.683965+08:00' and '2026-01-21T02:22:28.881567+00:00'
        try:
            return datetime.fromisoformat(s).astimezone(timezone.utc)
        except Exception:
            return None
    return None


@dataclass
class IntelSignal:
    symbol: str
    direction: str  # LONG / SHORT / HOLD
    confidence: float = 0.0
    valid_until: Optional[datetime] = None


class DirectionLock:
    """Enforce single-direction selection per scope (default: daily).

    Scope:
    - "day": lock resets when UTC+8 local date changes (Asia/Singapore/China style)
    - "run": lock resets per process run
    """

    def __init__(self):
        self.scope = os.getenv("DIRECTION_LOCK_SCOPE", "day").strip().lower()
        self.tz_offset_hours = int(os.getenv("DIRECTION_LOCK_TZ_OFFSET_HOURS", "8"))
        self.locked_direction: Optional[str] = None
        self.locked_date_key: Optional[str] = None

    def _date_key(self, now_utc: datetime) -> str:
        local = now_utc + timedelta(hours=self.tz_offset_hours)
        return local.strftime("%Y-%m-%d")

    def maybe_reset(self, now_utc: datetime):
        if self.scope != "day":
            return
        key = self._date_key(now_utc)
        if self.locked_date_key != key:
            self.locked_date_key = key
            self.locked_direction = None

    def apply(self, desired: str, now_utc: datetime) -> str:
        desired = (desired or "HOLD").upper()
        if desired not in ("LONG", "SHORT", "HOLD"):
            desired = "HOLD"
        self.maybe_reset(now_utc)
        if desired in ("LONG", "SHORT"):
            if self.locked_direction is None:
                self.locked_direction = desired
            elif self.locked_direction != desired:
                # Enforce lock: reject conflicting direction -> HOLD
                return "HOLD"
        return desired


class EntryAuthority:
    """Read Intel output and validate entry authorization."""

    def __init__(self):
        self.use_intel = _bool_env("USE_INTEL_TOPN", default=True)
        self.intel_path = os.getenv("INTEL_TOPN_PATH", "store/topn/latest.json")
        self.intel_max_age_seconds = int(os.getenv("INTEL_MAX_AGE_SECONDS", "900"))
        self.intel_symbols_strict = _bool_env("INTEL_SYMBOLS_STRICT", default=True)
        self.min_confidence = float(os.getenv("INTEL_MIN_CONFIDENCE", "0.0"))

        self.direction_lock = DirectionLock() if _bool_env("ENFORCE_SINGLE_DIRECTION", default=True) else None

    def read_intel(self) -> Tuple[Optional[datetime], List[IntelSignal]]:
        """Returns (intel_time_utc, signals). On any failure, returns (None, [])."""
        if not self.use_intel:
            return None, []
        try:
            with open(self.intel_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return None, []

        intel_time = _parse_iso_ts(payload.get("time")) or _parse_iso_ts(payload.get("timestamp"))

        # Support formats:
        # 1) {topn: ["BTCUSDT", ...]}
        # 2) {topn: [{symbol, direction, confidence, valid_until}, ...]}
        # 3) {signals: {...}}
        items = payload.get("topn")
        if items is None:
            items = payload.get("signals")
        if items is None:
            return intel_time, []

        signals: List[IntelSignal] = []
        if isinstance(items, dict):
            # dict symbol -> info
            for sym, info in items.items():
                if isinstance(info, str):
                    direction = info
                    conf = float(payload.get("confidence", 0.0) or 0.0)
                    vu = _parse_iso_ts(payload.get("valid_until"))
                else:
                    direction = str(info.get("direction") or info.get("side") or "HOLD")
                    conf = float(info.get("confidence", info.get("conf", 0.0)) or 0.0)
                    vu = _parse_iso_ts(info.get("valid_until"))
                signals.append(IntelSignal(symbol=str(sym).upper(), direction=direction.upper(), confidence=conf, valid_until=vu))
        elif isinstance(items, list):
            for it in items:
                if isinstance(it, str):
                    signals.append(IntelSignal(symbol=it.upper(), direction=str(payload.get("direction") or "HOLD").upper(), confidence=float(payload.get("confidence", 0.0) or 0.0), valid_until=_parse_iso_ts(payload.get("valid_until"))))
                elif isinstance(it, dict):
                    sym = str(it.get("symbol") or it.get("s") or "").upper()
                    if not sym:
                        continue
                    direction = str(it.get("direction") or it.get("side") or payload.get("direction") or "HOLD").upper()
                    conf = float(it.get("confidence", it.get("conf", payload.get("confidence", 0.0))) or 0.0)
                    vu = _parse_iso_ts(it.get("valid_until") or payload.get("valid_until"))
                    signals.append(IntelSignal(symbol=sym, direction=direction, confidence=conf, valid_until=vu))

        # normalize
        for s in signals:
            if s.direction not in ("LONG", "SHORT", "HOLD"):
                s.direction = "HOLD"
            if s.confidence is None:
                s.confidence = 0.0
        return intel_time, signals

    def validate_time_bound(self, intel_time_utc: Optional[datetime], now_utc: datetime) -> bool:
        if intel_time_utc is None:
            return False
        age = (now_utc - intel_time_utc).total_seconds()
        return age >= 0 and age <= float(self.intel_max_age_seconds)

    def resolve_symbol_universe(self, env_symbols: List[str], signals: List[IntelSignal]) -> List[str]:
        intel_syms = [s.symbol for s in signals]
        if self.intel_symbols_strict:
            return intel_syms
        # union with env symbols, keep intel first
        seen = set()
        out: List[str] = []
        for s in intel_syms + env_symbols:
            s2 = str(s).upper()
            if s2 and s2 not in seen:
                seen.add(s2)
                out.append(s2)
        return out

    def get_entry_instruction(self, symbol: str, signals: List[IntelSignal], now_utc: datetime) -> Tuple[str, float, str]:
        """Return (action, confidence, reason)."""
        sym = str(symbol).upper()
        sig = next((s for s in signals if s.symbol == sym), None)
        if not sig:
            return "HOLD", 0.0, "no_intel_signal"

        if sig.valid_until is not None and now_utc > sig.valid_until:
            return "HOLD", 0.0, "intel_signal_expired"

        if sig.confidence < self.min_confidence:
            return "HOLD", float(sig.confidence), "intel_confidence_below_min"

        action = sig.direction
        if self.direction_lock:
            locked = self.direction_lock.apply(action, now_utc)
            if locked == "HOLD" and action in ("LONG", "SHORT"):
                return "HOLD", float(sig.confidence), "direction_locked"
            action = locked
        return action, float(sig.confidence), "ok"
