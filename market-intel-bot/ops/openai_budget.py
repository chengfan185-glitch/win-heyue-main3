from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict

from src.store import read_json, write_json


@dataclass
class Budget:
    spent_usd: float
    day: str
    last_call_ts: float


def _today_yyyymmdd() -> str:
    return time.strftime("%Y%m%d", time.localtime())


def load_budget(path: str) -> Budget:
    obj = read_json(path, {"spent_usd": 0.0, "day": _today_yyyymmdd(), "last_call_ts": 0.0})
    day = obj.get("day") or _today_yyyymmdd()
    if day != _today_yyyymmdd():
        return Budget(spent_usd=0.0, day=_today_yyyymmdd(), last_call_ts=0.0)
    return Budget(spent_usd=float(obj.get("spent_usd") or 0.0), day=day, last_call_ts=float(obj.get("last_call_ts") or 0.0))


def save_budget(path: str, b: Budget) -> None:
    write_json(path, {"spent_usd": b.spent_usd, "day": b.day, "last_call_ts": b.last_call_ts})


def allow_call(b: Budget, daily_budget_usd: float, cooldown_seconds: int) -> bool:
    if b.spent_usd >= daily_budget_usd:
        return False
    if (time.time() - b.last_call_ts) < cooldown_seconds:
        return False
    return True
