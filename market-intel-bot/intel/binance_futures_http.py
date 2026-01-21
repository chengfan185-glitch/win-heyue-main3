import os, time, math
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

FAPI_BASE = os.getenv("BINANCE_FAPI_BASE", "https://fapi.binance.com")

def _session():
    s = requests.Session()
    retries = Retry(
        total=int(os.getenv("HTTP_RETRY_TOTAL", "5")),
        backoff_factor=float(os.getenv("HTTP_RETRY_BACKOFF", "0.5")),
        status_forcelist=(418, 429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

_SESS = _session()
_CACHE = {}
_CACHE_TTL = int(os.getenv("EXCHANGEINFO_CACHE_TTL_SEC", "3600"))

def get_exchange_info():
    now = time.time()
    hit = _CACHE.get("exchangeInfo")
    if hit and now - hit["ts"] < _CACHE_TTL:
        return hit["data"]
    url = f"{FAPI_BASE}/fapi/v1/exchangeInfo"
    r = _SESS.get(url, timeout=float(os.getenv("HTTP_TIMEOUT", "10")))
    r.raise_for_status()
    data = r.json()
    _CACHE["exchangeInfo"] = {"ts": now, "data": data}
    return data

def fetch_klines(symbol: str, interval="15m", limit=120):
    url = f"{FAPI_BASE}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = _SESS.get(url, params=params, timeout=float(os.getenv("HTTP_TIMEOUT", "10")))
    r.raise_for_status()
    return r.json()
