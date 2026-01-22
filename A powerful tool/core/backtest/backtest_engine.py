# core/backtest/backtest_engine.py
"""
Backtesting Engine for Strategy Validation

Simulates strategy performance on historical data before live deployment.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
import time
import json
from pathlib import Path


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    strategy_id: str
    version: str
    
    # Data range
    start_time: float
    end_time: float
    total_bars: int
    
    # Performance
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    
    # Trade details
    trades: List[Dict[str, Any]] = field(default_factory=list)
    
    # Equity curve
    equity_curve: List[float] = field(default_factory=list)
    
    # Status
    passed: bool = False
    
    # Metadata
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'strategy_id': self.strategy_id,
            'version': self.version,
            'start_time': self.start_time,
            'start_time_iso': datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            'end_time': self.end_time,
            'end_time_iso': datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat(),
            'total_bars': self.total_bars,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_pnl': self.total_pnl,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'trades': self.trades,
            'equity_curve': self.equity_curve,
            'passed': self.passed,
            'config': self.config,
            'created_at': self.created_at,
            'created_at_iso': datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat()
        }
    
    def save(self, output_dir: str):
        """Save backtest result to file"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"backtest_{self.strategy_id}_{self.version}_{int(self.created_at)}.json"
        filepath = output_path / filename
        
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        
        print(f"[BacktestResult] Saved to {filepath}")


class BacktestEngine:
    """
    Backtesting engine for validating strategies on historical data
    
    Simulates strategy execution and tracks performance metrics.
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        
        # Trade tracking
        self.trades: List[Dict[str, Any]] = []
        self.open_position: Optional[Dict[str, Any]] = None
        
        # Equity tracking
        self.equity_curve: List[float] = [initial_capital]
        
        # Performance metrics
        self.peak_equity = initial_capital
        self.max_drawdown = 0.0
    
    def reset(self):
        """Reset engine state"""
        self.capital = self.initial_capital
        self.trades = []
        self.open_position = None
        self.equity_curve = [self.initial_capital]
        self.peak_equity = self.initial_capital
        self.max_drawdown = 0.0
    
    def run(
        self,
        strategy_func: Callable,
        data: List[Dict[str, Any]],
        strategy_id: str,
        version: str,
        config: Optional[Dict[str, Any]] = None
    ) -> BacktestResult:
        """
        Run backtest on historical data
        
        Args:
            strategy_func: Function that takes (bar, market_state) and returns (action, params)
                          action: 'LONG', 'SHORT', 'CLOSE', 'HOLD'
                          params: dict with 'size', 'stop_loss', 'take_profit', etc.
            data: List of bars/klines with OHLCV data
            strategy_id: Strategy identifier
            version: Strategy version
            config: Additional configuration
            
        Returns:
            BacktestResult with performance metrics
        """
        print(f"[Backtest] Running backtest for {strategy_id} v{version}")
        print(f"[Backtest] Data: {len(data)} bars, Initial capital: {self.initial_capital}")
        
        self.reset()
        
        if not data:
            return BacktestResult(
                strategy_id=strategy_id,
                version=version,
                start_time=time.time(),
                end_time=time.time(),
                total_bars=0,
                config=config or {}
            )
        
        start_time = float(data[0].get('timestamp', time.time()))
        end_time = float(data[-1].get('timestamp', time.time()))
        
        # Simulate bar-by-bar
        for i, bar in enumerate(data):
            timestamp = float(bar.get('timestamp', time.time()))
            price = float(bar.get('close', 0))
            
            # Check open position for exit conditions
            if self.open_position:
                should_exit, exit_reason = self._check_exit_conditions(bar, self.open_position)
                
                if should_exit:
                    self._close_position(timestamp, price, exit_reason)
            
            # Get strategy signal (if no position or position just closed)
            if not self.open_position:
                try:
                    action, params = strategy_func(bar, i)
                    
                    if action in ('LONG', 'SHORT'):
                        self._open_position(timestamp, price, action, params)
                
                except Exception as e:
                    print(f"[Backtest] Strategy error at bar {i}: {e}")
            
            # Update equity curve
            current_equity = self.capital
            if self.open_position:
                pnl = self._calculate_unrealized_pnl(price, self.open_position)
                current_equity += pnl
            
            self.equity_curve.append(current_equity)
            
            # Track drawdown
            if current_equity > self.peak_equity:
                self.peak_equity = current_equity
            drawdown = self.peak_equity - current_equity
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
        
        # Close any remaining position
        if self.open_position:
            final_price = float(data[-1].get('close', 0))
            self._close_position(end_time, final_price, "backtest_end")
        
        # Calculate metrics
        result = self._calculate_results(
            strategy_id=strategy_id,
            version=version,
            start_time=start_time,
            end_time=end_time,
            total_bars=len(data),
            config=config or {}
        )
        
        # Evaluation criteria for pass/fail
        result.passed = self._evaluate_performance(result)
        
        print(f"[Backtest] Complete: {result.total_trades} trades, "
              f"PnL: {result.total_pnl:+.2f}, Win rate: {result.win_rate:.2%}")
        print(f"[Backtest] Result: {'✅ PASSED' if result.passed else '❌ FAILED'}")
        
        return result
    
    def _open_position(self, timestamp: float, price: float, side: str, params: Dict[str, Any]):
        """Open a new position"""
        size_usd = params.get('size_usd', self.capital * 0.02)  # Default 2% position
        quantity = size_usd / price
        
        self.open_position = {
            'side': side,
            'entry_price': price,
            'entry_time': timestamp,
            'quantity': quantity,
            'size_usd': size_usd,
            'stop_loss': params.get('stop_loss'),
            'take_profit': params.get('take_profit'),
            'trailing_stop_pct': params.get('trailing_stop_pct'),
            'highest_price': price if side == 'LONG' else None,
            'lowest_price': price if side == 'SHORT' else None
        }
        
        print(f"[Backtest] OPEN {side} @ {price:.2f}, size={size_usd:.2f}")
    
    def _close_position(self, timestamp: float, price: float, reason: str):
        """Close the open position"""
        if not self.open_position:
            return
        
        pos = self.open_position
        
        # Calculate PnL
        if pos['side'] == 'LONG':
            pnl = (price - pos['entry_price']) * pos['quantity']
        else:  # SHORT
            pnl = (pos['entry_price'] - price) * pos['quantity']
        
        # Record trade
        trade = {
            'entry_time': pos['entry_time'],
            'exit_time': timestamp,
            'side': pos['side'],
            'entry_price': pos['entry_price'],
            'exit_price': price,
            'quantity': pos['quantity'],
            'pnl': pnl,
            'pnl_pct': pnl / pos['size_usd'],
            'reason': reason,
            'duration': timestamp - pos['entry_time']
        }
        
        self.trades.append(trade)
        self.capital += pnl
        self.open_position = None
        
        print(f"[Backtest] CLOSE {pos['side']} @ {price:.2f}, PnL: {pnl:+.2f}, Reason: {reason}")
    
    def _check_exit_conditions(self, bar: Dict[str, Any], position: Dict[str, Any]) -> tuple[bool, str]:
        """Check if position should be exited"""
        price = float(bar.get('close', 0))
        high = float(bar.get('high', price))
        low = float(bar.get('low', price))
        
        side = position['side']
        
        # Update trailing stops
        if side == 'LONG':
            if high > (position.get('highest_price') or 0):
                position['highest_price'] = high
        else:  # SHORT
            if position.get('lowest_price') is None or low < position['lowest_price']:
                position['lowest_price'] = low
        
        # Check stop loss
        if position.get('stop_loss'):
            if side == 'LONG' and low <= position['stop_loss']:
                return True, "stop_loss"
            elif side == 'SHORT' and high >= position['stop_loss']:
                return True, "stop_loss"
        
        # Check take profit
        if position.get('take_profit'):
            if side == 'LONG' and high >= position['take_profit']:
                return True, "take_profit"
            elif side == 'SHORT' and low <= position['take_profit']:
                return True, "take_profit"
        
        # Check trailing stop
        if position.get('trailing_stop_pct'):
            trailing_pct = position['trailing_stop_pct']
            
            if side == 'LONG' and position.get('highest_price'):
                trailing_stop = position['highest_price'] * (1 - trailing_stop_pct)
                if price <= trailing_stop:
                    return True, "trailing_stop"
            
            elif side == 'SHORT' and position.get('lowest_price'):
                trailing_stop = position['lowest_price'] * (1 + trailing_stop_pct)
                if price >= trailing_stop:
                    return True, "trailing_stop"
        
        return False, ""
    
    def _calculate_unrealized_pnl(self, current_price: float, position: Dict[str, Any]) -> float:
        """Calculate unrealized PnL for open position"""
        if position['side'] == 'LONG':
            return (current_price - position['entry_price']) * position['quantity']
        else:  # SHORT
            return (position['entry_price'] - current_price) * position['quantity']
    
    def _calculate_results(
        self,
        strategy_id: str,
        version: str,
        start_time: float,
        end_time: float,
        total_bars: int,
        config: Dict[str, Any]
    ) -> BacktestResult:
        """Calculate final backtest results"""
        result = BacktestResult(
            strategy_id=strategy_id,
            version=version,
            start_time=start_time,
            end_time=end_time,
            total_bars=total_bars,
            config=config
        )
        
        if not self.trades:
            return result
        
        # Basic metrics
        result.trades = self.trades
        result.total_trades = len(self.trades)
        result.winning_trades = sum(1 for t in self.trades if t['pnl'] > 0)
        result.losing_trades = sum(1 for t in self.trades if t['pnl'] < 0)
        result.total_pnl = sum(t['pnl'] for t in self.trades)
        
        # Win rate
        result.win_rate = result.winning_trades / result.total_trades if result.total_trades > 0 else 0.0
        
        # Profit factor
        wins = sum(t['pnl'] for t in self.trades if t['pnl'] > 0)
        losses = abs(sum(t['pnl'] for t in self.trades if t['pnl'] < 0))
        result.profit_factor = wins / losses if losses > 0 else float('inf')
        
        # Sharpe ratio (simplified)
        if len(self.trades) > 1:
            returns = [t['pnl'] / self.initial_capital for t in self.trades]
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            result.sharpe_ratio = (mean_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0.0
        
        # Max drawdown
        result.max_drawdown = self.max_drawdown
        
        # Equity curve
        result.equity_curve = self.equity_curve
        
        return result
    
    def _evaluate_performance(self, result: BacktestResult) -> bool:
        """
        Evaluate if backtest performance meets minimum requirements
        
        Returns:
            True if strategy passed evaluation
        """
        # Minimum requirements for passing
        requirements = [
            result.total_trades >= 10,           # At least 10 trades
            result.win_rate >= 0.45,             # At least 45% win rate
            result.total_pnl > 0,                # Positive total PnL
            result.profit_factor >= 1.1,         # Profit factor > 1.1
            result.max_drawdown < self.initial_capital * 0.30  # Max 30% drawdown
        ]
        
        return all(requirements)
