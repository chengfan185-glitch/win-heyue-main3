# core/backtest/__init__.py
"""
Backtesting and Walk-Forward Validation Module

Provides infrastructure for testing strategies before live deployment.
"""

from .backtest_engine import BacktestEngine, BacktestResult
from .walk_forward import WalkForwardValidator
from .strategy_registry import StrategyRegistry, StrategyMetrics
from .market_state import MarketState, MarketRegime

__all__ = [
    'BacktestEngine',
    'BacktestResult',
    'WalkForwardValidator',
    'StrategyRegistry',
    'StrategyMetrics',
    'MarketState',
    'MarketRegime'
]
