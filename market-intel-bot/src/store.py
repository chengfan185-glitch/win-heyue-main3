from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import orjson


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "rb") as f:
            return orjson.loads(f.read())
    except Exception:
        return default


def write_json(path: str, data: Any) -> None:
    d = os.path.dirname(path)
    if d:
        _ensure_dir(d)
    with open(path, "wb") as f:
        f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))


@dataclass
class CooldownState:
    last_publish_ts: Dict[str, float]


def load_state(state_file: str) -> CooldownState:
    obj = read_json(state_file, {"last_publish_ts": {}})
    return CooldownState(last_publish_ts=dict(obj.get("last_publish_ts", {}) or {}))


def save_state(state_file: str, st: CooldownState) -> None:
    write_json(state_file, {"last_publish_ts": st.last_publish_ts, "updated_at": time.time()})
