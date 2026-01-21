# core/filters/market_aware_exits.py
"""
Market-State Aware Exit Logic

Adjusts TP/SL dynamically based on market regime.
Not fixed ratios - adaptive to conditions.

Key insight: Optimal TP/SL varies by market state.
"""

from __future__ import annotations
from typing import Dict, Any, Tuple, Optional


class MarketAwareExits:
    """
    Dynamic TP/SL adjustment based on market conditions
    
    Examples:
    - TRENDING: Wider TP, tighter SL (let winners run)
    - RANGING: Tighter TP, quick SL (take profits fast)
    - VOLATILE: Either avoid or use very tight stops
    
    This doesn't necessarily improve win rate, but significantly improves net profit.
    """
    
    def __init__(self):
        # Base multipliers for different regimes
        # Format: (TP_multiplier, SL_multiplier)
        self.regime_multipliers = {
            'TRENDING_UP': {
                'tp_multiplier': 1.5,   # Larger TP
                'sl_multiplier': 0.8,   # Tighter SL
                'use_trailing': True,
                'trailing_distance': 0.015
            },
            'TRENDING_DOWN': {
                'tp_multiplier': 1.5,
                'sl_multiplier': 0.8,
                'use_trailing': True,
                'trailing_distance': 0.015
            },
            'RANGING': {
                'tp_multiplier': 0.7,   # Smaller TP (take profits quickly)
                'sl_multiplier': 1.0,   # Standard SL
                'use_trailing': False,
                'trailing_distance': 0.01
            },
            'VOLATILE': {
                'tp_multiplier': 0.6,   # Very tight TP
                'sl_multiplier': 0.7,   # Very tight SL
                'use_trailing': False,
                'trailing_distance': 0.02
            },
            'QUIET': {
                'tp_multiplier': 1.0,
                'sl_multiplier': 1.2,   # Wider SL (less noise)
                'use_trailing': True,
                'trailing_distance': 0.01
            },
            'UNKNOWN': {
                'tp_multiplier': 1.0,
                'sl_multiplier': 1.0,
                'use_trailing': False,
                'trailing_distance': 0.015
            }
        }
    
    def calculate_exit_levels(
        self,
        entry_price: float,
        side: str,
        market_regime: str,
        base_tp_pct: float = 0.04,
        base_sl_pct: float = 0.02,
        volatility: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate adaptive TP/SL levels
        
        Args:
            entry_price: Entry price
            side: Trade side (LONG/SHORT)
            market_regime: Current market regime
            base_tp_pct: Base take profit percentage (e.g., 0.04 = 4%)
            base_sl_pct: Base stop loss percentage (e.g., 0.02 = 2%)
            volatility: Current volatility (optional, for further adjustment)
            
        Returns:
            Dict with tp_price, sl_price, use_trailing, trailing_distance
        """
        # Get regime-specific multipliers
        params = self.regime_multipliers.get(
            market_regime,
            self.regime_multipliers['UNKNOWN']
        )
        
        # Apply regime multipliers
        adjusted_tp_pct = base_tp_pct * params['tp_multiplier']
        adjusted_sl_pct = base_sl_pct * params['sl_multiplier']
        
        # Further adjust for volatility if provided
        if volatility is not None:
            # In high volatility, widen stops slightly
            if volatility > 0.03:
                volatility_factor = min(1.5, 1.0 + (volatility - 0.03) * 10)
                adjusted_sl_pct *= volatility_factor
        
        # Calculate actual prices
        if side == "LONG":
            tp_price = entry_price * (1 + adjusted_tp_pct)
            sl_price = entry_price * (1 - adjusted_sl_pct)
        else:  # SHORT
            tp_price = entry_price * (1 - adjusted_tp_pct)
            sl_price = entry_price * (1 + adjusted_sl_pct)
        
        return {
            'tp_price': tp_price,
            'sl_price': sl_price,
            'tp_pct': adjusted_tp_pct,
            'sl_pct': adjusted_sl_pct,
            'use_trailing': params['use_trailing'],
            'trailing_distance': params['trailing_distance'],
            'risk_reward_ratio': adjusted_tp_pct / adjusted_sl_pct if adjusted_sl_pct > 0 else 0,
            'market_regime': market_regime,
            'params_used': params
        }
    
    def should_adjust_exits(
        self,
        current_regime: str,
        original_regime: str,
        position_duration: float
    ) -> bool:
        """
        Check if exits should be adjusted due to regime change
        
        Args:
            current_regime: Current market regime
            original_regime: Regime when position was opened
            position_duration: Time since position opened (seconds)
            
        Returns:
            True if exits should be readjusted
        """
        # Don't adjust too frequently
        if position_duration < 3600:  # Less than 1 hour
            return False
        
        # Adjust if regime significantly changed
        significant_changes = [
            (current_regime != original_regime),
            (original_regime == 'TRENDING_UP' and current_regime == 'VOLATILE'),
            (original_regime == 'TRENDING_DOWN' and current_regime == 'VOLATILE'),
            (original_regime == 'QUIET' and current_regime == 'VOLATILE')
        ]
        
        return any(significant_changes)
    
    def get_regime_description(self, regime: str) -> str:
        """Get human-readable description of regime exit strategy"""
        descriptions = {
            'TRENDING_UP': "Wider TP (let winners run), tighter SL, use trailing stop",
            'TRENDING_DOWN': "Wider TP (let winners run), tighter SL, use trailing stop",
            'RANGING': "Quick TP (take profits fast), standard SL, no trailing",
            'VOLATILE': "Very tight TP/SL, no trailing (or avoid trading)",
            'QUIET': "Standard TP, wider SL (reduce noise), use trailing",
            'UNKNOWN': "Standard TP/SL, no trailing"
        }
        return descriptions.get(regime, "Standard exit strategy")
    
    def calculate_expected_value(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        tp_pct: float,
        sl_pct: float
    ) -> float:
        """
        Calculate expected value for a setup
        
        Args:
            win_rate: Historical win rate
            avg_win: Average winning trade size
            avg_loss: Average losing trade size
            tp_pct: Take profit percentage
            sl_pct: Stop loss percentage
            
        Returns:
            Expected value per trade
        """
        # Expected win
        expected_win = win_rate * avg_win * (tp_pct / 0.04)  # Normalized to 4% base
        
        # Expected loss
        expected_loss = (1 - win_rate) * avg_loss * (sl_pct / 0.02)  # Normalized to 2% base
        
        return expected_win - expected_loss
    
    def get_regime_stats_summary(self) -> str:
        """Generate summary of regime-based exit strategies"""
        lines = []
        lines.append("=" * 60)
        lines.append("MARKET-AWARE EXIT STRATEGIES")
        lines.append("=" * 60)
        lines.append("")
        
        for regime, params in self.regime_multipliers.items():
            lines.append(f"{regime}:")
            lines.append(f"  TP Multiplier: {params['tp_multiplier']:.1f}x")
            lines.append(f"  SL Multiplier: {params['sl_multiplier']:.1f}x")
            lines.append(f"  Trailing Stop: {'✅ Yes' if params['use_trailing'] else '❌ No'}")
            if params['use_trailing']:
                lines.append(f"  Trailing Distance: {params['trailing_distance']:.1%}")
            lines.append(f"  Strategy: {self.get_regime_description(regime)}")
            
            # Calculate example R:R
            example_tp = 0.04 * params['tp_multiplier']
            example_sl = 0.02 * params['sl_multiplier']
            example_rr = example_tp / example_sl if example_sl > 0 else 0
            lines.append(f"  Example R:R: {example_rr:.2f}:1 (TP {example_tp:.1%}, SL {example_sl:.1%})")
            lines.append("")
        
        return '\n'.join(lines)
