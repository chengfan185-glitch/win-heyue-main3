# execution/adapters/binance_cm_futures.py
"""
Binance COIN-M Futures Adapter (SAFE VERSION)

- paper   : simulated
- testnet : real order on Binance COIN-M Testnet
- live    : FORBIDDEN
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Literal, List
from dataclasses import dataclass


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    qty: float = 0.0
    avg_price: float = 0.0
    error: Optional[str] = None


@dataclass
class PositionInfo:
    symbol: str
    position_amt: float
    entry_price: float
    position_side: str


class BinanceCMFuturesAdapter:
    def __init__(self, trading_mode: Literal["paper", "testnet", "live"] = "paper"):
        self.trading_mode = trading_mode

        if trading_mode == "live":
            raise RuntimeError(
                "❌ BinanceCMFuturesAdapter: live 模式尚未解锁，已强制禁止"
            )

        if trading_mode == "testnet":
            import os
            from binance.cm_futures import CMFutures

            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_API_SECRET")
            if not api_key or not api_secret:
                raise RuntimeError("❌ testnet 模式缺少 BINANCE_API_KEY / SECRET")

            self.client = CMFutures(
                key=api_key,
                secret=api_secret,
                base_url="https://testnet.binancefuture.com",
            )
        else:
            self.client = None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        position_side: str = "BOTH",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
    ) -> OrderResult:

        if self.trading_mode == "paper":
            qty = int(quantity or 1)
            return OrderResult(
                success=True,
                order_id=f"paper_{symbol}_{side}",
                qty=float(qty),
                avg_price=50000.0,
            )

        try:
            resp = self.client.new_order(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=int(quantity),
                reduceOnly=reduce_only,
            )
            return OrderResult(
                success=True,
                exchange_order_id=str(resp.get("orderId")),
                qty=float(resp.get("executedQty", 0)),
                avg_price=float(resp.get("avgPrice", 0)),
            )
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    def get_position(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        if self.trading_mode == "paper":
            return []

        try:
            positions = self.client.position_risk()
            out: List[PositionInfo] = []
            for p in positions:
                if symbol and p["symbol"] != symbol:
                    continue
                amt = float(p["positionAmt"])
                if amt == 0:
                    continue
                out.append(
                    PositionInfo(
                        symbol=p["symbol"],
                        position_amt=amt,
                        entry_price=float(p["entryPrice"]),
                        position_side="LONG" if amt > 0 else "SHORT",
                    )
                )
            return out
        except Exception:
            return []

    def close_position(self, symbol: str) -> bool:
        positions = self.get_position(symbol)
        for p in positions:
            side = "SELL" if p.position_amt > 0 else "BUY"
            self.place_market_order(
                symbol=symbol,
                side=side,
                quantity=abs(p.position_amt),
                reduce_only=True,
            )
        return True

    def get_account_balance(self) -> Dict[str, Any]:
        if self.trading_mode == "paper":
            return {"totalWalletBalance": "1.0", "availableBalance": "1.0"}

        try:
            return self.client.balance()[0]
        except Exception:
            return {}
