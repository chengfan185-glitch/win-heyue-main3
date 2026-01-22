# core/backtest/strategy_registry.py
"""
Strategy Registry and Performance Tracking

Manages strategy IDs, versions, and performance metrics for live deployment gating.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import json
import time


@dataclass
class StrategyMetrics:
    """Performance metrics for a strategy"""
    strategy_id: str
    version: str
    
    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    
    # Risk metrics
    avg_trade_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Timing
    avg_trade_duration: float = 0.0  # seconds
    
    # Market conditions
    favorable_regime_performance: Dict[str, float] = field(default_factory=dict)
    
    # Status
    backtest_passed: bool = False
    walkforward_passed: bool = False
    live_approved: bool = False
    live_enabled: bool = False
    
    # Timestamps
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    approved_at: Optional[float] = None
    
    def update_metrics(self, trades: List[Dict[str, Any]]):
        """Update metrics from a list of trades"""
        if not trades:
            return
        
        self.total_trades = len(trades)
        self.winning_trades = sum(1 for t in trades if t.get('pnl', 0) > 0)
        self.losing_trades = sum(1 for t in trades if t.get('pnl', 0) < 0)
        
        # PnL
        self.total_pnl = sum(t.get('pnl', 0) for t in trades)
        wins = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
        losses = [abs(t['pnl']) for t in trades if t.get('pnl', 0) < 0]
        
        # Win rate
        self.win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0
        
        # Profit factor
        total_wins = sum(wins) if wins else 0.0
        total_losses = sum(losses) if losses else 0.0
        self.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Averages
        self.avg_trade_pnl = self.total_pnl / self.total_trades if self.total_trades > 0 else 0.0
        self.avg_win = sum(wins) / len(wins) if wins else 0.0
        self.avg_loss = sum(losses) / len(losses) if losses else 0.0
        self.largest_win = max(wins) if wins else 0.0
        self.largest_loss = max(losses) if losses else 0.0
        
        # Drawdown (simplified)
        cumulative_pnl = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            cumulative_pnl += t.get('pnl', 0)
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = peak - cumulative_pnl
            if dd > max_dd:
                max_dd = dd
        self.max_drawdown = max_dd
        
        # Sharpe ratio (simplified - daily returns)
        if len(trades) > 1:
            returns = [t.get('pnl', 0) for t in trades]
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            self.sharpe_ratio = (mean_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0.0
        
        self.updated_at = time.time()
    
    def meets_live_requirements(self, requirements: Dict[str, float]) -> bool:
        """
        Check if strategy meets requirements for live trading
        
        Args:
            requirements: Dict with thresholds like:
                {'min_trades': 30, 'min_win_rate': 0.55, 'min_sharpe': 1.0, ...}
        """
        checks = []
        
        # Minimum trades
        if 'min_trades' in requirements:
            checks.append(self.total_trades >= requirements['min_trades'])
        
        # Win rate
        if 'min_win_rate' in requirements:
            checks.append(self.win_rate >= requirements['min_win_rate'])
        
        # Profit factor
        if 'min_profit_factor' in requirements:
            checks.append(self.profit_factor >= requirements['min_profit_factor'])
        
        # Sharpe ratio
        if 'min_sharpe' in requirements:
            checks.append(self.sharpe_ratio >= requirements['min_sharpe'])
        
        # Max drawdown
        if 'max_drawdown' in requirements:
            checks.append(self.max_drawdown <= requirements['max_drawdown'])
        
        # Positive PnL
        if 'min_total_pnl' in requirements:
            checks.append(self.total_pnl >= requirements['min_total_pnl'])
        
        return all(checks) if checks else False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'strategy_id': self.strategy_id,
            'version': self.version,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_pnl': self.total_pnl,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'avg_trade_pnl': self.avg_trade_pnl,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'avg_trade_duration': self.avg_trade_duration,
            'favorable_regime_performance': self.favorable_regime_performance,
            'backtest_passed': self.backtest_passed,
            'walkforward_passed': self.walkforward_passed,
            'live_approved': self.live_approved,
            'live_enabled': self.live_enabled,
            'created_at': self.created_at,
            'created_at_iso': datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            'updated_at': self.updated_at,
            'updated_at_iso': datetime.fromtimestamp(self.updated_at, tz=timezone.utc).isoformat(),
            'approved_at': self.approved_at,
            'approved_at_iso': datetime.fromtimestamp(self.approved_at, tz=timezone.utc).isoformat() if self.approved_at else None
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StrategyMetrics:
        """Create from dictionary"""
        d = d.copy()
        d.pop('created_at_iso', None)
        d.pop('updated_at_iso', None)
        d.pop('approved_at_iso', None)
        return cls(**d)


class StrategyRegistry:
    """
    Registry for managing strategies and their performance
    
    Provides gating mechanism for paper -> live transitions.
    """
    
    def __init__(self, registry_dir: str = "logs/strategy_registry"):
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        
        self.strategies: Dict[str, StrategyMetrics] = {}
        self.registry_file = self.registry_dir / "registry.json"
        
        self._load()
    
    def _load(self):
        """Load registry from disk"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, 'r') as f:
                    data = json.load(f)
                    for strat_data in data.get('strategies', []):
                        metrics = StrategyMetrics.from_dict(strat_data)
                        key = f"{metrics.strategy_id}_{metrics.version}"
                        self.strategies[key] = metrics
                print(f"[StrategyRegistry] Loaded {len(self.strategies)} strategies")
            except Exception as e:
                print(f"[StrategyRegistry] Error loading registry: {e}")
    
    def _save(self):
        """Save registry to disk"""
        try:
            data = {
                'updated_at': time.time(),
                'strategies': [m.to_dict() for m in self.strategies.values()]
            }
            
            # Atomic write
            temp_file = self.registry_file.with_suffix('.json.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.registry_file)
            
        except Exception as e:
            print(f"[StrategyRegistry] Error saving registry: {e}")
    
    def register_strategy(self, strategy_id: str, version: str) -> StrategyMetrics:
        """Register a new strategy or get existing"""
        key = f"{strategy_id}_{version}"
        
        if key not in self.strategies:
            metrics = StrategyMetrics(
                strategy_id=strategy_id,
                version=version
            )
            self.strategies[key] = metrics
            self._save()
            print(f"[StrategyRegistry] Registered new strategy: {key}")
        
        return self.strategies[key]
    
    def update_strategy_metrics(self, strategy_id: str, version: str, trades: List[Dict[str, Any]]):
        """Update strategy metrics from trades"""
        key = f"{strategy_id}_{version}"
        
        if key not in self.strategies:
            self.register_strategy(strategy_id, version)
        
        metrics = self.strategies[key]
        metrics.update_metrics(trades)
        self._save()
        
        print(f"[StrategyRegistry] Updated metrics for {key}: "
              f"{metrics.total_trades} trades, "
              f"win_rate={metrics.win_rate:.2%}, "
              f"pnl={metrics.total_pnl:.2f}")
    
    def approve_for_live(self, strategy_id: str, version: str, requirements: Optional[Dict[str, float]] = None):
        """
        Approve a strategy for live trading after validation
        
        Args:
            strategy_id: Strategy identifier
            version: Strategy version
            requirements: Performance requirements (optional, uses defaults if None)
        """
        key = f"{strategy_id}_{version}"
        
        if key not in self.strategies:
            raise ValueError(f"Strategy {key} not found in registry")
        
        metrics = self.strategies[key]
        
        # Default requirements
        if requirements is None:
            requirements = {
                'min_trades': 30,
                'min_win_rate': 0.52,
                'min_profit_factor': 1.2,
                'min_sharpe': 0.5,
                'min_total_pnl': 0.0
            }
        
        if metrics.meets_live_requirements(requirements):
            metrics.live_approved = True
            metrics.approved_at = time.time()
            self._save()
            print(f"[StrategyRegistry] ✅ Approved {key} for live trading")
            return True
        else:
            print(f"[StrategyRegistry] ❌ {key} does not meet live requirements")
            return False
    
    def enable_live_trading(self, strategy_id: str, version: str):
        """Enable live trading for an approved strategy"""
        key = f"{strategy_id}_{version}"
        
        if key not in self.strategies:
            raise ValueError(f"Strategy {key} not found in registry")
        
        metrics = self.strategies[key]
        
        if not metrics.live_approved:
            raise ValueError(f"Strategy {key} not approved for live trading")
        
        metrics.live_enabled = True
        self._save()
        print(f"[StrategyRegistry] ✅ Enabled live trading for {key}")
    
    def disable_live_trading(self, strategy_id: str, version: str, reason: str = ""):
        """Disable live trading for a strategy"""
        key = f"{strategy_id}_{version}"
        
        if key in self.strategies:
            self.strategies[key].live_enabled = False
            self._save()
            print(f"[StrategyRegistry] ⛔ Disabled live trading for {key}: {reason}")
    
    def is_live_enabled(self, strategy_id: str, version: str) -> bool:
        """Check if a strategy is enabled for live trading"""
        key = f"{strategy_id}_{version}"
        return self.strategies.get(key, StrategyMetrics(strategy_id, version)).live_enabled
    
    def get_metrics(self, strategy_id: str, version: str) -> Optional[StrategyMetrics]:
        """Get metrics for a strategy"""
        key = f"{strategy_id}_{version}"
        return self.strategies.get(key)
    
    def list_strategies(self, live_only: bool = False) -> List[StrategyMetrics]:
        """List all strategies or only live-enabled ones"""
        strategies = list(self.strategies.values())
        if live_only:
            strategies = [s for s in strategies if s.live_enabled]
        return sorted(strategies, key=lambda x: x.updated_at, reverse=True)
    
    def generate_report(self) -> str:
        """Generate a text report of all strategies"""
        lines = []
        lines.append("=" * 80)
        lines.append("STRATEGY REGISTRY REPORT")
        lines.append("=" * 80)
        lines.append(f"Total strategies: {len(self.strategies)}")
        lines.append("")
        
        for metrics in sorted(self.strategies.values(), key=lambda x: x.total_pnl, reverse=True):
            lines.append(f"Strategy: {metrics.strategy_id} v{metrics.version}")
            lines.append(f"  Status: {'🟢 LIVE' if metrics.live_enabled else '🟡 PAPER' if metrics.live_approved else '⚪ TESTING'}")
            lines.append(f"  Trades: {metrics.total_trades} (W:{metrics.winning_trades} L:{metrics.losing_trades})")
            lines.append(f"  Win Rate: {metrics.win_rate:.2%}")
            lines.append(f"  Total PnL: {metrics.total_pnl:+.2f}")
            lines.append(f"  Profit Factor: {metrics.profit_factor:.2f}")
            lines.append(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
            lines.append(f"  Max Drawdown: {metrics.max_drawdown:.2f}")
            lines.append(f"  Updated: {datetime.fromtimestamp(metrics.updated_at, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            lines.append("")
        
        return '\n'.join(lines)
