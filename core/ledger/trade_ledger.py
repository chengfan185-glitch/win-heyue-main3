# core/ledger/trade_ledger.py
"""
Production-Grade Trading Ledger

Single Source of Truth for all trading activities with:
- Order/Fill/Position/Trade entity relationships
- JSONL persistence with atomic writes
- Query capabilities for audit and reconciliation
- Run versioning and parameter snapshots
"""

from __future__ import annotations

import json
import os
BOT_PROFILE_NAME = os.getenv("BOT_PROFILE_NAME", "unknown_profile")
import time
import uuid
import hashlib
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
from enum import Enum


class OrderStatus(Enum):
    """Order lifecycle statuses"""
    PENDING = "PENDING"          # Created but not sent
    SUBMITTED = "SUBMITTED"      # Sent to exchange
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"


class PositionSide(Enum):
    """Position direction"""
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"  # One-way mode


@dataclass
class Order:
    """Order entity - represents intent to trade"""
    order_id: str  # UUID generated locally
    exchange_order_id: Optional[str] = None  # ID from exchange
    
    symbol: str = ""
    side: str = ""  # BUY/SELL
    position_side: str = "BOTH"  # LONG/SHORT/BOTH
    order_type: str = "MARKET"
    
    quantity: float = 0.0
    quote_quantity: Optional[float] = None
    price: Optional[float] = None
    stop_price: Optional[float] = None
    
    status: str = "PENDING"
    
    # Execution details
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    commission_asset: str = ""
    
    # Context
    timestamp: float = field(default_factory=lambda: time.time())
    run_id: Optional[str] = None
    strategy_version: Optional[str] = None
    signal_context: Optional[Dict[str, Any]] = None
    
    # Error tracking
    error_message: Optional[str] = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization"""
        d = asdict(self)
        d['timestamp_iso'] = datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Order:
        """Create from dict"""
        # Remove computed fields
        d.pop('timestamp_iso', None)
        return cls(**d)


@dataclass
class Fill:
    """Fill entity - represents actual execution"""
    fill_id: str  # UUID
    order_id: str  # Reference to Order
    exchange_trade_id: Optional[str] = None
    
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    
    commission: float = 0.0
    commission_asset: str = ""
    
    timestamp: float = field(default_factory=lambda: time.time())
    is_maker: bool = False
    
    # Slippage tracking
    expected_price: Optional[float] = None
    slippage_bps: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['timestamp_iso'] = datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()
        if self.expected_price and self.price:
            d['slippage_bps'] = abs((self.price - self.expected_price) / self.expected_price) * 10000
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Fill:
        d.pop('timestamp_iso', None)
        d.pop('slippage_bps', None)  # Computed field
        return cls(**d)


@dataclass
class Position:
    """Position entity - represents current holdings"""
    position_id: str  # UUID
    symbol: str = ""
    side: str = "LONG"  # LONG/SHORT
    
    quantity: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    
    leverage: int = 1
    margin_type: str = "ISOLATED"
    
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    # Risk parameters
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    highest_price_since_entry: Optional[float] = None
    
    # Lifecycle
    opened_at: float = field(default_factory=lambda: time.time())
    closed_at: Optional[float] = None
    status: str = "OPEN"  # OPEN/CLOSED
    
    # Traceability
    open_order_id: Optional[str] = None
    close_order_id: Optional[str] = None
    run_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['opened_at_iso'] = datetime.fromtimestamp(self.opened_at, tz=timezone.utc).isoformat()
        if self.closed_at:
            d['closed_at_iso'] = datetime.fromtimestamp(self.closed_at, tz=timezone.utc).isoformat()
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Position:
        d.pop('opened_at_iso', None)
        d.pop('closed_at_iso', None)
        return cls(**d)


@dataclass
class Trade:
    """Trade entity - complete round trip (open + close)"""
    trade_id: str  # UUID
    symbol: str = ""
    side: str = "LONG"
    
    bot_profile: str = "" 

    # Entry
    entry_quantity: float = 0.0
    entry_price: float = 0.0
    entry_timestamp: float = field(default_factory=lambda: time.time())
    entry_order_id: Optional[str] = None
    
    # Exit
    exit_quantity: float = 0.0
    exit_price: float = 0.0
    exit_timestamp: Optional[float] = None
    exit_order_id: Optional[str] = None
    exit_reason: Optional[str] = None  # TP/SL/TRAILING/MANUAL/TIMEOUT
    
    # P&L
    gross_pnl: float = 0.0
    commission_total: float = 0.0
    net_pnl: float = 0.0
    pnl_pct: float = 0.0
    
    # Duration
    hold_duration_sec: Optional[float] = None
    
    # Context
    leverage: int = 1
    run_id: Optional[str] = None
    strategy_version: Optional[str] = None
    entry_features: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['entry_timestamp_iso'] = datetime.fromtimestamp(self.entry_timestamp, tz=timezone.utc).isoformat()
        if self.exit_timestamp:
            d['exit_timestamp_iso'] = datetime.fromtimestamp(self.exit_timestamp, tz=timezone.utc).isoformat()
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Trade:
        d.pop('entry_timestamp_iso', None)
        d.pop('exit_timestamp_iso', None)
        return cls(**d)


class TradeLedger:
    """
    Production-grade trading ledger with ACID properties
    
    Features:
    - JSONL append-only storage (one line per event)
    - Atomic writes with file rotation
    - Entity relationships (order_id/fill_id/position_id/trade_id)
    - Query interface for reconciliation
    - Run versioning
    """
    
    def __init__(self, base_dir: str = "logs/ledger"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Separate files for each entity type
        self.orders_file = self.base_dir / "orders.jsonl"
        self.fills_file = self.base_dir / "fills.jsonl"
        self.positions_file = self.base_dir / "positions.jsonl"
        self.trades_file = self.base_dir / "trades.jsonl"
        
        # Runtime state (in-memory for fast access)
        self._open_positions: Dict[str, Position] = {}
        self._pending_orders: Dict[str, Order] = {}
        
        # Run tracking
        self.run_id = self._generate_run_id()
        self._init_run_manifest()
    
    def _generate_run_id(self) -> str:
        """Generate unique run ID"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        return f"run_{timestamp}_{random_suffix}"
    
    def _init_run_manifest(self):
        """Save run configuration snapshot"""
        manifest_file = self.base_dir / f"{self.run_id}_manifest.json"
        
        # Capture environment configuration
        config_snapshot = {
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "config": {
                "TRADING_MODE": os.getenv("TRADING_MODE", ""),
                "FUTURES_MARKET_TYPE": os.getenv("FUTURES_MARKET_TYPE", ""),
                "SYMBOLS": os.getenv("SYMBOLS", ""),
                "INTERVAL": os.getenv("INTERVAL", ""),
                "MAX_LEVERAGE": os.getenv("MAX_LEVERAGE", ""),
                "MARGIN_TYPE": os.getenv("MARGIN_TYPE", ""),
                "STOP_LOSS_PCT": os.getenv("STOP_LOSS_PCT", ""),
                "TAKE_PROFIT_PCT": os.getenv("TAKE_PROFIT_PCT", ""),
                "ENABLE_ANTI_FLIP": os.getenv("ENABLE_ANTI_FLIP", ""),
                "DAILY_ORDER_QUOTA": os.getenv("DAILY_ORDER_QUOTA", ""),
                "BOT_PROFILE_NAME": BOT_PROFILE_NAME,
            },
            "config_hash": self._hash_config()
        }
        
        with open(manifest_file, 'w') as f:
            json.dump(config_snapshot, f, indent=2)
    
    def _hash_config(self) -> str:
        """Generate hash of current configuration"""
        config_str = json.dumps({
            k: os.getenv(k, "") for k in [
                "TRADING_MODE", "FUTURES_MARKET_TYPE", "SYMBOLS", "INTERVAL",
                "MAX_LEVERAGE", "STOP_LOSS_PCT", "TAKE_PROFIT_PCT"
            ]
        }, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]
    
    def _append_jsonl(self, filepath: Path, entity: Any):
        """Atomic append to JSONL file"""
        line = json.dumps(entity.to_dict(), ensure_ascii=False) + "\n"
        
        # Atomic write: write to temp file, then rename
        temp_file = filepath.with_suffix('.jsonl.tmp')
        try:
            with open(temp_file, 'a', encoding='utf-8') as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            # Append to main file
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            
            # Clean up temp
            temp_file.unlink()
        except Exception as e:
            print(f"[LEDGER ERROR] Failed to write {filepath}: {e}")
            raise
    
    # ===== Order Management =====
    
    def record_order(self, order: Order) -> str:
        """Record a new order"""
        if not order.order_id:
            order.order_id = f"ord_{uuid.uuid4().hex}"
        
        if not order.run_id:
            order.run_id = self.run_id
        
        order.timestamp = time.time()
        
        self._append_jsonl(self.orders_file, order)
        self._pending_orders[order.order_id] = order
        
        return order.order_id
    
    def update_order_status(self, order_id: str, status: str, 
                           exchange_order_id: Optional[str] = None,
                           filled_quantity: float = 0.0,
                           avg_fill_price: float = 0.0,
                           error_message: Optional[str] = None):
        """Update order status"""
        if order_id not in self._pending_orders:
            print(f"[LEDGER WARN] Order {order_id} not found in pending orders")
            return
        
        order = self._pending_orders[order_id]
        order.status = status
        if exchange_order_id:
            order.exchange_order_id = exchange_order_id
        if filled_quantity > 0:
            order.filled_quantity = filled_quantity
        if avg_fill_price > 0:
            order.avg_fill_price = avg_fill_price
        if error_message:
            order.error_message = error_message
        
        # Re-record with updated status
        self._append_jsonl(self.orders_file, order)
        
        # Clean up if terminal state
        if status in ("FILLED", "CANCELED", "REJECTED", "FAILED"):
            self._pending_orders.pop(order_id, None)
    
    # ===== Fill Management =====
    
    def record_fill(self, fill: Fill) -> str:
        """Record a fill"""
        if not fill.fill_id:
            fill.fill_id = f"fill_{uuid.uuid4().hex}"
        
        fill.timestamp = time.time()
        
        self._append_jsonl(self.fills_file, fill)
        
        return fill.fill_id
    
    # ===== Position Management =====
    
    def open_position(self, position: Position) -> str:
        """Open a new position"""
        if not position.position_id:
            position.position_id = f"pos_{uuid.uuid4().hex}"
        
        if not position.run_id:
            position.run_id = self.run_id
        
        position.opened_at = time.time()
        position.status = "OPEN"
        
        self._append_jsonl(self.positions_file, position)
        self._open_positions[position.symbol] = position
        
        return position.position_id
    
    def update_position(self, symbol: str, current_price: float,
                       unrealized_pnl: Optional[float] = None):
        """Update position with current price"""
        if symbol not in self._open_positions:
            return
        
        pos = self._open_positions[symbol]
        pos.current_price = current_price
        
        if unrealized_pnl is not None:
            pos.unrealized_pnl = unrealized_pnl
        else:
            # Calculate unrealized PnL
            if pos.side == "LONG":
                pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - current_price) * pos.quantity
        
        # Update trailing stop peak if applicable
        if pos.side == "LONG" and pos.trailing_stop_pct:
            if pos.highest_price_since_entry is None or current_price > pos.highest_price_since_entry:
                pos.highest_price_since_entry = current_price
        elif pos.side == "SHORT" and pos.trailing_stop_pct:
            if pos.highest_price_since_entry is None or current_price < pos.highest_price_since_entry:
                pos.highest_price_since_entry = current_price
    
    def close_position(self, symbol: str, close_price: float, 
                      close_order_id: Optional[str] = None,
                      realized_pnl: Optional[float] = None) -> Optional[Position]:
        """Close an existing position"""
        if symbol not in self._open_positions:
            print(f"[LEDGER WARN] No open position for {symbol}")
            return None
        
        pos = self._open_positions.pop(symbol)
        pos.current_price = close_price
        pos.closed_at = time.time()
        pos.status = "CLOSED"
        pos.close_order_id = close_order_id
        
        if realized_pnl is not None:
            pos.realized_pnl = realized_pnl
        else:
            # Calculate realized PnL
            if pos.side == "LONG":
                pos.realized_pnl = (close_price - pos.entry_price) * pos.quantity
            else:
                pos.realized_pnl = (pos.entry_price - close_price) * pos.quantity
        
        self._append_jsonl(self.positions_file, pos)
        
        return pos
    
    def get_open_position(self, symbol: str) -> Optional[Position]:
        """Get current open position for symbol"""
        return self._open_positions.get(symbol)
    
    def get_all_open_positions(self) -> Dict[str, Position]:
        """Get all open positions"""
        return self._open_positions.copy()
    
    # ===== Trade Management (Round Trip) =====
    
    def record_trade(self, trade: Trade) -> str:
        """Record a completed trade"""
        if not trade.trade_id:
            trade.trade_id = f"trade_{uuid.uuid4().hex}"
        
        if not trade.run_id:
            trade.run_id = self.run_id
        
        # Calculate derived fields
        if trade.exit_timestamp and trade.entry_timestamp:
            trade.hold_duration_sec = trade.exit_timestamp - trade.entry_timestamp
        
        if trade.entry_quantity > 0 and trade.entry_price > 0:
            trade.gross_pnl = trade.net_pnl + trade.commission_total
            trade.pnl_pct = trade.net_pnl / (trade.entry_price * trade.entry_quantity)
        
        self._append_jsonl(self.trades_file, trade)
        
        return trade.trade_id
    
    # ===== Query Interface =====
    
    def load_all_positions(self) -> List[Position]:
        """Load all positions from file (for recovery)"""
        positions = []
        if not self.positions_file.exists():
            return positions
        
        with open(self.positions_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        pos = Position.from_dict(json.loads(line))
                        positions.append(pos)
                    except Exception as e:
                        print(f"[LEDGER ERROR] Failed to parse position: {e}")
        
        return positions
    
    def reconcile_positions(self, exchange_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Reconcile local positions with exchange
        
        Returns:
            dict with 'matches', 'local_only', 'exchange_only', 'discrepancies'
        """
        # Load latest local positions (only OPEN)
        local_positions = {pos.symbol: pos for pos in self.load_all_positions() 
                          if pos.status == "OPEN"}
        
        exchange_map = {pos['symbol']: pos for pos in exchange_positions}
        
        matches = []
        discrepancies = []
        local_only = []
        exchange_only = []
        
        # Check local positions
        for symbol, local_pos in local_positions.items():
            if symbol in exchange_map:
                exch_pos = exchange_map[symbol]
                # Compare quantities
                local_qty = abs(local_pos.quantity)
                exch_qty = abs(float(exch_pos.get('positionAmt', 0)))
                
                if abs(local_qty - exch_qty) < 0.001:  # Tolerance
                    matches.append(symbol)
                else:
                    discrepancies.append({
                        'symbol': symbol,
                        'local_qty': local_qty,
                        'exchange_qty': exch_qty,
                        'diff': local_qty - exch_qty
                    })
            else:
                local_only.append(symbol)
        
        # Check exchange positions
        for symbol in exchange_map:
            if symbol not in local_positions:
                exchange_only.append(symbol)
        
        return {
            'matches': matches,
            'local_only': local_only,
            'exchange_only': exchange_only,
            'discrepancies': discrepancies,
            'is_consistent': len(local_only) == 0 and len(exchange_only) == 0 and len(discrepancies) == 0
        }


class LedgerQuery:
    """Query interface for ledger analysis"""
    
    def __init__(self, ledger_dir: str = "logs/ledger"):
        self.ledger_dir = Path(ledger_dir)
    
    def get_trades_by_date(self, start_date: str, end_date: str) -> List[Trade]:
        """Get trades within date range"""
        # Implementation for analysis
        pass
    
    def get_performance_summary(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Get performance metrics for a run"""
        # Implementation for reporting
        pass
    
    def get_order_fill_rate(self, hours: int = 24) -> float:
        """Calculate order fill rate"""
        # Implementation for monitoring
        pass
