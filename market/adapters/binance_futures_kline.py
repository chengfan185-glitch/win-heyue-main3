# market/adapters/binance_futures_kline.py
"""
Binance Futures Kline (Candlestick) Data Fetcher
Supports both USDT-M and Coin-M futures markets
"""

import requests
from typing import List, Dict, Literal
import os


class BinanceFuturesKlineFetcher:
    """
    Fetch kline data from Binance Futures API
    Supports: 15m, 45m (custom), 1h, 3h intervals
    """

    def __init__(
        self, 
        symbol: str = "BTCUSDT",
        market_type: Literal["UM", "CM"] = "UM"
    ):
        self.symbol = symbol
        self.market_type = market_type
        
        # Set base URL based on market type
        if market_type == "UM":
            self.base_url = "https://fapi.binance.com"
        else:  # CM
            self.base_url = "https://dapi.binance.com"

    def fetch_klines(self, interval: str, limit: int = 100) -> List[Dict]:
        """
        Fetch kline data from Binance Futures
        
        Args:
            interval: Kline interval (1m, 5m, 15m, 1h, 3h, 4h, etc.)
            limit: Number of klines to fetch (max 1500)
        
        Returns:
            List of kline dictionaries with OHLCV data
        """
        # Handle custom 45m interval
        if interval == "45m":
            return self._fetch_custom_45m(limit)
        
        # Map interval to API format
        api_interval = self._map_interval(interval)
        
        url = f"{self.base_url}/fapi/v1/klines" if self.market_type == "UM" else f"{self.base_url}/dapi/v1/klines"
        
        params = {
            "symbol": self.symbol,
            "interval": api_interval,
            "limit": min(limit, 1500)
        }
        
        try:
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
                    "quote_volume": float(k[7]),
                    "trades": int(k[8]),
                    "taker_buy_base": float(k[9]),
                    "taker_buy_quote": float(k[10]),
                })
            
            return result
        
        except Exception as e:
            print(f"[FUTURES_KLINE] Error fetching {self.symbol} {interval}: {e}")
            return []

    def _fetch_custom_45m(self, limit: int) -> List[Dict]:
        """
        Fetch 45m klines by aggregating 15m klines
        45m = 3 * 15m
        """
        # Fetch 3x the limit to have enough 15m candles
        klines_15m = self.fetch_klines("15m", limit * 3)
        
        if not klines_15m or len(klines_15m) < 3:
            return []
        
        # Aggregate every 3 candles into one 45m candle
        result = []
        for i in range(0, len(klines_15m) - 2, 3):
            candles = klines_15m[i:i+3]
            
            agg_candle = {
                "open_time": candles[0]["open_time"],
                "open": candles[0]["open"],
                "high": max(c["high"] for c in candles),
                "low": min(c["low"] for c in candles),
                "close": candles[-1]["close"],
                "volume": sum(c["volume"] for c in candles),
                "close_time": candles[-1]["close_time"],
                "quote_volume": sum(c.get("quote_volume", 0) for c in candles),
                "trades": sum(c.get("trades", 0) for c in candles),
                "taker_buy_base": sum(c.get("taker_buy_base", 0) for c in candles),
                "taker_buy_quote": sum(c.get("taker_buy_quote", 0) for c in candles),
            }
            
            result.append(agg_candle)
            
            if len(result) >= limit:
                break
        
        return result[:limit]

    def _map_interval(self, interval: str) -> str:
        """Map interval to Binance API format"""
        # Binance supports: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "3h": "3h",
            "4h": "4h",
            "1d": "1d",
        }
        
        return interval_map.get(interval, interval)

    def fetch_mark_price(self) -> float:
        """Fetch current mark price for the symbol"""
        url = f"{self.base_url}/fapi/v1/premiumIndex" if self.market_type == "UM" else f"{self.base_url}/dapi/v1/premiumIndex"
        
        params = {"symbol": self.symbol}
        
        try:
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return float(data["markPrice"])
        except Exception as e:
            print(f"[FUTURES_PRICE] Error fetching mark price for {self.symbol}: {e}")
            # Fallback to last price from ticker
            return self.fetch_last_price()

    def fetch_last_price(self) -> float:
        """Fetch last traded price for the symbol"""
        url = f"{self.base_url}/fapi/v1/ticker/price" if self.market_type == "UM" else f"{self.base_url}/dapi/v1/ticker/price"
        
        params = {"symbol": self.symbol}
        
        try:
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return float(data["price"])
        except Exception as e:
            print(f"[FUTURES_PRICE] Error fetching last price for {self.symbol}: {e}")
            raise


def fetch_futures_price(
    symbol: str = "BTCUSDT", 
    market_type: Literal["UM", "CM"] = "UM"
) -> float:
    """
    Convenience function to fetch futures price
    Uses mark price (more stable for liquidation/margin calculations)
    """
    fetcher = BinanceFuturesKlineFetcher(symbol, market_type)
    return fetcher.fetch_mark_price()
