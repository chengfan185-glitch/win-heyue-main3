# market/adapters/binance_futures_kline.py
"""
Binance futures kline & price fetcher (robust, with fallback)
- Exposes:
  - class BinanceFuturesKlineFetcher(symbol, market_type='UM', session=None)
      method: fetch_klines(interval, limit=50) -> List[Dict[str, Any]]
  - function fetch_futures_price(symbol, market_type='UM') -> float
- Behavior:
  - Prefer Binance public endpoints with retries
  - If Binance fails (network / 4xx / 5xx / connection reset), fall back to OKX public API
  - Kline rows are normalized to dicts: { "ts", "open", "high", "low", "close", "volume" }
"""

from typing import List, Dict, Any, Optional
import time
import requests

BINANCE_BASE = "https://fapi.binance.com"
BINANCE_KLINES_PATH = "/fapi/v1/klines"
BINANCE_MARK_PRICE = "/fapi/v1/premiumIndex"
OKX_CANDLES_URL = "https://www.okx.com/api/v5/market/candles"
OKX_TICKER_URL = "https://www.okx.com/api/v5/market/ticker"

_DEFAULT_TIMEOUT = 8
_DEFAULT_RETRIES = 3


class BinanceFuturesKlineFetcher:
    def __init__(self, symbol: str, market_type: str = "UM", session: Optional[requests.Session] = None):
        """
        symbol: e.g. 'BTCUSDT'
        market_type: 'UM' or 'CM' (kept for compatibility)
        session: optional requests.Session to reuse connections
        """
        self.symbol = symbol
        self.market_type = market_type
        self.session = session or requests.Session()

    def fetch_klines(self, interval: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch klines for given interval. Returns list of dicts:
          {"ts": int(ms), "open": float, "high": float, "low": float, "close": float, "volume": float}
        Tries Binance public klines first, with retries. On failure falls back to OKX candles.
        """
        params = {"symbol": self.symbol, "interval": interval, "limit": int(limit)}
        attempt = 0

        # Try Binance public API
        while attempt < _DEFAULT_RETRIES:
            attempt += 1
            try:
                url = BINANCE_BASE + BINANCE_KLINES_PATH
                resp = self.session.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
                resp.raise_for_status()
                raw = resp.json()
                klines = []
                for row in raw:
                    # Binance kline row: [ openTime, open, high, low, close, volume, ... ]
                    klines.append({
                        "ts": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    })
                return klines
            except requests.HTTPError as he:
                text = ""
                try:
                    text = he.response.text
                except Exception:
                    text = str(he)
                print(f"[BINANCE_KLINES] HTTPError attempt={attempt}: {text}")
                # If it's a 4xx (client) likely won't succeed on retry except timestamp — but retry a few times anyway
                if attempt < _DEFAULT_RETRIES:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                break
            except (requests.ConnectionError, requests.Timeout) as neterr:
                print(f"[BINANCE_KLINES] Network error attempt={attempt}: {neterr}")
                if attempt < _DEFAULT_RETRIES:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                break
            except Exception as e:
                print(f"[BINANCE_KLINES] Unexpected error attempt={attempt}: {e}")
                break

        # Fallback to OKX (best-effort)
        try:
            inst = self.symbol.replace("USDT", "-USDT")
            params_okx = {"instId": inst, "bar": interval if interval != "45m" else "45m", "limit": str(limit)}
            r = self.session.get(OKX_CANDLES_URL, params=params_okx, timeout=_DEFAULT_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            # OKX success indicated by code == "0"
            if data.get("code") == "0":
                candles = data.get("data", [])
                klines = []
                for c in candles:
                    # OKX candle: [ts, open, high, low, close, vol, ...]
                    klines.append({
                        "ts": int(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                    })
                print("[BINANCE_KLINES] Fallback to OKX succeeded")
                return klines
            else:
                print(f"[BINANCE_KLINES] OKX fallback returned non-zero code: {data.get('code')}")
        except Exception as e:
            print(f"[BINANCE_KLINES] OKX fallback failed: {e}")

        # If all fails return empty list
        return []


def fetch_futures_price(symbol: str, market_type: str = "UM") -> float:
    """
    Fetch a near-real-time price for futures symbol.
    Try Binance mark price endpoint first, with retries; fallback to OKX ticker.
    Returns float price or raises Exception if cannot fetch.
    """
    params = {"symbol": symbol}
    attempt = 0
    session = requests.Session()

    # Binance mark/premium endpoint
    while attempt < _DEFAULT_RETRIES:
        attempt += 1
        try:
            url = BINANCE_BASE + BINANCE_MARK_PRICE
            resp = session.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
            resp.raise_for_status()
            j = resp.json()
            # Binance premiumIndex returns fields: symbol, markPrice, indexPrice, lastFundingRate, etc.
            price = j.get("markPrice") or j.get("lastPrice") or j.get("price")
            if price is None:
                # sometimes API returns list — guard
                if isinstance(j, list) and j:
                    price = j[0].get("markPrice") or j[0].get("lastPrice")
            if price is None:
                raise RuntimeError(f"Binance mark price missing in response: {j}")
            return float(price)
        except requests.HTTPError as he:
            text = ""
            try:
                text = he.response.text
            except Exception:
                text = str(he)
            print(f"[BINANCE_PRICE] HTTPError attempt={attempt}: {text}")
            if attempt < _DEFAULT_RETRIES:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise
        except (requests.ConnectionError, requests.Timeout) as neterr:
            print(f"[BINANCE_PRICE] Network error attempt={attempt}: {neterr}")
            if attempt < _DEFAULT_RETRIES:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise
        except Exception as e:
            print(f"[BINANCE_PRICE] Unexpected error attempt={attempt}: {e}")
            if attempt < _DEFAULT_RETRIES:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise

    # Fallback to OKX ticker
    try:
        inst = symbol.replace("USDT", "-USDT")
        r = session.get(OKX_TICKER_URL, params={"instId": inst}, timeout=_DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("code") == "0":
            d = data.get("data", [])
            if d and isinstance(d, list):
                last = d[0].get("last")
                if last is None:
                    raise RuntimeError("OKX ticker missing 'last'")
                return float(last)
        raise RuntimeError(f"OKX returned unexpected payload: {data}")
    except Exception as e:
        print(f"[FALLBACK_PRICE] OKX fallback failed: {e}")
        raise