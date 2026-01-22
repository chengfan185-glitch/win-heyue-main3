# shared/intel_reader.py
import json
import os
import time
from typing import Any, Dict, List, Optional


def _safe_load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def load_topn_symbols(path: str) -> Optional[List[str]]:
    """
    Reads shared/topn.json and returns the symbol list.

    Compatible with:
      - {"symbols":[...]}
      - fallback: {"topn":[{"symbol":"BTCUSDT"}, ...]}
    """
    d = _safe_load_json(path)
    if not d:
        return None

    syms = d.get("symbols")
    if isinstance(syms, list) and len(syms) > 0:
        out = [str(x).strip().upper() for x in syms if str(x).strip()]
        return out if out else None

    topn = d.get("topn")
    if isinstance(topn, list) and len(topn) > 0:
        out = []
        for item in topn:
            if isinstance(item, dict) and item.get("symbol"):
                out.append(str(item["symbol"]).strip().upper())
        return out if out else None

    return None


def load_ai_intel(path: str) -> Optional[Dict[str, Any]]:
    return _safe_load_json(path)


def get_file_age_seconds(path: str) -> float:
    """
    Freshness based on file modified time (mtime).
    This avoids relying on payload ts which may be wrong.
    """
    now = time.time()
    try:
        mtime = os.path.getmtime(path)  # epoch seconds
        return max(0.0, now - float(mtime))
    except Exception:
        return 1e18
