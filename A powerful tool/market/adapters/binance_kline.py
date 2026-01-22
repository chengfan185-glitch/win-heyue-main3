# market/adapters/binance_kline.py

import requests
from typing import List, Dict


BINANCE_BASE = "https://api.binance.com"


class BinanceKlineFetcher:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol

    def fetch_klines(self, interval: str, limit: int = 100) -> List[Dict]:
        url = f"{BINANCE_BASE}/api/v3/klines"
        params = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": limit,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        klines = resp.json()

        result = []
        for k in klines:
            result.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
            })

        return result
