# core/backtest/market_state.py
"""
Market State Classification and Regime Detection

Provides tools to classify market conditions for strategy adaptation.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
import json


class MarketRegime(Enum):
    """Market regime classification"""
    TRENDING_UP = "TRENDING_UP"        # Strong uptrend
    TRENDING_DOWN = "TRENDING_DOWN"    # Strong downtrend
    RANGING = "RANGING"                # Sideways/consolidation
    VOLATILE = "VOLATILE"              # High volatility, no clear direction
    QUIET = "QUIET"                    # Low volatility
    UNKNOWN = "UNKNOWN"                # Insufficient data


@dataclass
class MarketState:
    """
    Comprehensive market state representation
    
    Captures current market conditions for strategy decision-making.
    """
    timestamp: float
    symbol: str
    
    # Price action
    price: float
    price_change_1h: float = 0.0
    price_change_4h: float = 0.0
    price_change_24h: float = 0.0
    
    # Volatility
    volatility_1h: float = 0.0
    volatility_24h: float = 0.0
    atr_14: float = 0.0  # Average True Range
    
    # Volume
    volume_24h: float = 0.0
    volume_ratio: float = 1.0  # Current volume vs 24h average
    
    # Trend indicators
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_50: Optional[float] = None
    rsi_14: Optional[float] = None
    
    # Market regime
    regime: MarketRegime = MarketRegime.UNKNOWN
    regime_confidence: float = 0.0
    
    # Additional metadata
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp,
            'timestamp_iso': datetime.fromtimestamp(self.timestamp).isoformat(),
            'symbol': self.symbol,
            'price': self.price,
            'price_change_1h': self.price_change_1h,
            'price_change_4h': self.price_change_4h,
            'price_change_24h': self.price_change_24h,
            'volatility_1h': self.volatility_1h,
            'volatility_24h': self.volatility_24h,
            'atr_14': self.atr_14,
            'volume_24h': self.volume_24h,
            'volume_ratio': self.volume_ratio,
            'ema_9': self.ema_9,
            'ema_21': self.ema_21,
            'ema_50': self.ema_50,
            'rsi_14': self.rsi_14,
            'regime': self.regime.value,
            'regime_confidence': self.regime_confidence,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> MarketState:
        """Create from dictionary"""
        d = d.copy()
        d.pop('timestamp_iso', None)
        if 'regime' in d and isinstance(d['regime'], str):
            d['regime'] = MarketRegime(d['regime'])
        return cls(**d)
    
    def classify_regime(self) -> MarketRegime:
        """
        Classify current market regime based on indicators
        
        Returns:
            MarketRegime with confidence level
        """
        # Need at least price changes and volatility
        if self.price_change_24h == 0 and self.volatility_24h == 0:
            self.regime = MarketRegime.UNKNOWN
            self.regime_confidence = 0.0
            return self.regime
        
        # Calculate trend strength
        trend_strength = abs(self.price_change_24h)
        
        # High volatility check
        if self.volatility_24h > 0.05:  # >5% volatility
            self.regime = MarketRegime.VOLATILE
            self.regime_confidence = min(self.volatility_24h / 0.10, 1.0)
            return self.regime
        
        # Low volatility check
        if self.volatility_24h < 0.01:  # <1% volatility
            self.regime = MarketRegime.QUIET
            self.regime_confidence = 1.0 - self.volatility_24h / 0.01
            return self.regime
        
        # Trending up
        if self.price_change_24h > 0.02:  # >2% up
            self.regime = MarketRegime.TRENDING_UP
            self.regime_confidence = min(self.price_change_24h / 0.05, 1.0)
            return self.regime
        
        # Trending down
        if self.price_change_24h < -0.02:  # >2% down
            self.regime = MarketRegime.TRENDING_DOWN
            self.regime_confidence = min(abs(self.price_change_24h) / 0.05, 1.0)
            return self.regime
        
        # Default to ranging
        self.regime = MarketRegime.RANGING
        self.regime_confidence = 1.0 - trend_strength / 0.02
        return self.regime
    
    def is_favorable_for_strategy(self, strategy_type: str) -> bool:
        """
        Check if current market state is favorable for a strategy type
        
        Args:
            strategy_type: 'trend_following', 'mean_reversion', 'breakout', etc.
            
        Returns:
            True if conditions are favorable
        """
        if self.regime == MarketRegime.UNKNOWN:
            return False
        
        if strategy_type == 'trend_following':
            return self.regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN)
        
        elif strategy_type == 'mean_reversion':
            return self.regime == MarketRegime.RANGING
        
        elif strategy_type == 'breakout':
            return self.regime in (MarketRegime.QUIET, MarketRegime.RANGING)
        
        elif strategy_type == 'volatility':
            return self.regime == MarketRegime.VOLATILE
        
        return True  # Generic strategies work in all regimes


class MarketStateAnalyzer:
    """Analyzes historical price data to determine market state"""
    
    def __init__(self):
        self.history: List[MarketState] = []
    
    def analyze(self, klines: List[Dict[str, Any]], symbol: str) -> MarketState:
        """
        Analyze kline data and produce market state
        
        Args:
            klines: List of kline dicts with OHLCV data
            symbol: Trading symbol
            
        Returns:
            MarketState object
        """
        if not klines or len(klines) < 2:
            return MarketState(
                timestamp=datetime.now().timestamp(),
                symbol=symbol,
                price=0.0,
                regime=MarketRegime.UNKNOWN
            )
        
        latest = klines[-1]
        price = float(latest.get('close', 0))
        
        # Calculate price changes
        price_change_1h = self._calc_price_change(klines, 4) if len(klines) >= 4 else 0.0  # 4x 15m
        price_change_4h = self._calc_price_change(klines, 16) if len(klines) >= 16 else 0.0
        price_change_24h = self._calc_price_change(klines, 96) if len(klines) >= 96 else 0.0
        
        # Calculate volatility
        volatility_1h = self._calc_volatility(klines[-4:]) if len(klines) >= 4 else 0.0
        volatility_24h = self._calc_volatility(klines[-96:]) if len(klines) >= 96 else 0.0
        
        # Volume metrics
        volume_24h = sum(float(k.get('volume', 0)) for k in klines[-96:]) if len(klines) >= 96 else 0.0
        avg_volume = volume_24h / 96 if volume_24h > 0 else 1.0
        current_volume = float(latest.get('volume', 0))
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Create market state
        state = MarketState(
            timestamp=datetime.now().timestamp(),
            symbol=symbol,
            price=price,
            price_change_1h=price_change_1h,
            price_change_4h=price_change_4h,
            price_change_24h=price_change_24h,
            volatility_1h=volatility_1h,
            volatility_24h=volatility_24h,
            volume_24h=volume_24h,
            volume_ratio=volume_ratio
        )
        
        # Classify regime
        state.classify_regime()
        
        # Store in history
        self.history.append(state)
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
        
        return state
    
    def _calc_price_change(self, klines: List[Dict], periods: int) -> float:
        """Calculate price change over N periods"""
        if len(klines) < periods + 1:
            return 0.0
        
        old_price = float(klines[-periods - 1].get('close', 0))
        new_price = float(klines[-1].get('close', 0))
        
        if old_price == 0:
            return 0.0
        
        return (new_price - old_price) / old_price
    
    def _calc_volatility(self, klines: List[Dict]) -> float:
        """Calculate volatility (std dev of returns)"""
        if len(klines) < 2:
            return 0.0
        
        returns = []
        for i in range(1, len(klines)):
            prev_close = float(klines[i-1].get('close', 0))
            curr_close = float(klines[i].get('close', 0))
            if prev_close > 0:
                returns.append((curr_close - prev_close) / prev_close)
        
        if not returns:
            return 0.0
        
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        return variance ** 0.5
