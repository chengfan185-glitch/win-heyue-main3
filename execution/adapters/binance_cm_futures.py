# execution/adapters/binance_cm_futures.py
"""
Binance COIN-M Futures Adapter

Provides interface for coin-margined perpetual futures trading on Binance.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Literal, List
from dataclasses import dataclass


@dataclass
class OrderResult:
    """Result of an order execution"""
    success: bool
    order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    qty: float = 0.0
    avg_price: float = 0.0
    error: Optional[str] = None


@dataclass
class PositionInfo:
    """Position information from exchange"""
    symbol: str
    position_amt: float
    entry_price: float
    position_side: str  # LONG/SHORT/BOTH


class BinanceCMFuturesAdapter:
    """
    Adapter for Binance COIN-M Futures
    
    Supports:
    - Paper mode (simulated)
    - Testnet mode (testnet.binancefuture.com)
    - Live mode (dapi.binance.com)
    """
    
    def __init__(self, trading_mode: Literal["paper", "testnet", "live"] = "paper"):
        self.trading_mode = trading_mode
        self.api_key = None
        self.api_secret = None
        
        if trading_mode in ("testnet", "live"):
            import os
            self.api_key = os.getenv("BINANCE_API_KEY", "")
            self.api_secret = os.getenv("BINANCE_API_SECRET", "")
            
            if not self.api_key or not self.api_secret:
                print(f"[WARN] No API keys found for {trading_mode} mode")
    
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        position_side: str = "BOTH",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False
    ) -> OrderResult:
        """Place a market order"""
        
        if self.trading_mode == "paper":
            # Paper mode - simulate success
            # For CM futures, quantity is in contracts (integer)
            qty = int(quantity) if quantity else 1
            
            return OrderResult(
                success=True,
                order_id=f"paper_{symbol}_{side}",
                exchange_order_id=None,
                qty=float(qty),
                avg_price=50000.0,  # Mock price
                error=None
            )
        
        # For testnet/live, would need actual Binance API integration
        print(f"[WARN] Real trading not implemented for {self.trading_mode} mode")
        return OrderResult(
            success=False,
            error="Real trading not implemented"
        )
    
    def close_position(self, symbol: str) -> bool:
        """Close an open position"""
        
        if self.trading_mode == "paper":
            # Paper mode - simulate success
            return True
        
        # For testnet/live, would need actual API integration
        print(f"[WARN] Real trading not implemented for {self.trading_mode} mode")
        return False
    
    def get_position(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """Get position information"""
        
        if self.trading_mode == "paper":
            # Paper mode - no positions on exchange
            return []
        
        # For testnet/live, would query actual positions
        print(f"[WARN] Real trading not implemented for {self.trading_mode} mode")
        return []
    
    def get_account_balance(self) -> Dict[str, Any]:
        """Get account balance"""
        
        if self.trading_mode == "paper":
            # Paper mode - mock balance (in BTC for CM)
            return {
                "totalWalletBalance": "1.0",
                "availableBalance": "1.0"
            }
        
        # For testnet/live, would query actual balance
        print(f"[WARN] Real trading not implemented for {self.trading_mode} mode")
        return {
            "totalWalletBalance": "0.0",
            "availableBalance": "0.0"
        }
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol"""
        
        if self.trading_mode == "paper":
            # Paper mode - simulate success
            return True
        
        print(f"[WARN] Real trading not implemented for {self.trading_mode} mode")
        return False
    
    def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        """Set margin type (ISOLATED/CROSSED)"""
        
        if self.trading_mode == "paper":
            # Paper mode - simulate success
            return True
        
        print(f"[WARN] Real trading not implemented for {self.trading_mode} mode")
        return False
