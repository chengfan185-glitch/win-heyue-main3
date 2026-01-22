# core/filters/__init__.py
"""
Trading Filters for Win Rate Improvement

Modules for improving trade quality through:
- Signal consistency filtering
- Failure mode blacklisting
- Trade quality scoring
- Time-based filtering
- Market-aware exits
- Expected value optimization
"""

from .signal_consistency import SignalConsistencyFilter
from .failure_blacklist import FailureModeBlacklist
from .trade_quality import TradeQualityScorer
from .time_filter import TimeFilter
from .market_aware_exits import MarketAwareExits

__all__ = [
    'SignalConsistencyFilter',
    'FailureModeBlacklist',
    'TradeQualityScorer',
    'TimeFilter',
    'MarketAwareExits'
]
