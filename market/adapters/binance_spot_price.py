import requests
import time

BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"

def fetch_price(symbol: str = "BTCUSDT") -> float:
    resp = requests.get(
        BINANCE_PRICE_URL,
        params={"symbol": symbol},
        timeout=5
    )
    resp.raise_for_status()
    data = resp.json()
    return float(data["price"])
