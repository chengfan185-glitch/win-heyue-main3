from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_exponential


class BinancePublic:
    def __init__(self, base_url: str, timeout: int = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Any:
        url = self.base_url + path
        r = self.s.get(url, params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def klines(self, symbol: str, interval: str, limit: int = 200) -> List[List[Any]]:
        return list(self._get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": int(limit)}))

    def top_symbols_by_quote_volume(self, universe_size: int = 80) -> List[str]:
        # Use 24hr ticker stats, filter USDT pairs
        data = list(self._get("/fapi/v1/ticker/24hr"))
        usdt = [d for d in data if str(d.get("symbol", "")).endswith("USDT")]
        # Sort by quoteVolume desc
        usdt.sort(key=lambda x: float(x.get("quoteVolume") or 0.0), reverse=True)
        out: List[str] = []
        for d in usdt:
            sym = str(d.get("symbol"))
            # Exclude stable-stable or weird symbols if any
            if sym in ("BUSDUSDT", "USDCUSDT", "TUSDUSDT"):
                continue
            out.append(sym)
            if len(out) >= universe_size:
                break
        return out
