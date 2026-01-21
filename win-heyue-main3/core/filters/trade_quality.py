# core/filters/trade_quality.py
"""
Trade Quality Scorer

Evaluates trade quality before execution based on multiple factors.
Only allows high-quality trades into live trading.

Key principle: Not "can we trade?" but "should we trade?"
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
import json
from pathlib import Path


class TradeQualityScorer:
    """
    Scores each potential trade on multiple dimensions
    
    Factors considered:
    - Signal strength
    - Market state match
    - Historical performance in similar conditions
    - Current environment similarity to backtest
    - Risk/reward ratio
    
    Only trades scoring above threshold proceed to execution.
    """
    
    def __init__(
        self,
        min_quality_score: float = 60.0,
        enable_scoring: bool = True
    ):
        """
        Args:
            min_quality_score: Minimum score to allow trade (0-100 scale)
            enable_scoring: Enable/disable quality scoring
        """
        self.min_quality_score = min_quality_score
        self.enable_scoring = enable_scoring
        
        # Weights for different components (must sum to 1.0)
        self.weights = {
            'signal_strength': 0.30,        # Confidence in signal
            'market_state_match': 0.25,     # Strategy suited for current market
            'historical_performance': 0.25,  # Past performance in similar conditions
            'risk_reward_ratio': 0.20       # Favorable risk/reward setup
        }
        
        # Statistics
        self.stats = {
            'total_scored': 0,
            'passed': 0,
            'blocked': 0,
            'avg_score': 0.0,
            'scores': []
        }
    
    def score_trade(
        self,
        signal_confidence: float,
        market_regime: str,
        strategy_type: str,
        historical_win_rate: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None,
        strategy_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, bool, Dict[str, float]]:
        """
        Calculate quality score for a potential trade
        
        QUANTITATIVE FORMULA:
        
        Total Score = Σ(Component_i × Weight_i) for i in [1,4]
        
        Component 1: Signal Strength Score (0-100)
        ─────────────────────────────────────────
        S₁ = signal_confidence × 100
        Weight₁ = 0.30
        
        Component 2: Market State Match Score (0-100)
        ──────────────────────────────────────────────
        S₂ = compatibility_matrix[strategy_type][market_regime]
        Weight₂ = 0.25
        
        Compatibility Matrix:
          trend_following:
            TRENDING_UP/DOWN: 90, RANGING: 30, VOLATILE: 50
          mean_reversion:
            TRENDING_UP/DOWN: 40, RANGING: 90, VOLATILE: 30
          breakout:
            TRENDING: 70, RANGING: 50, QUIET: 80
          volatility:
            VOLATILE: 95, others: 40-60
        
        Component 3: Historical Performance Score (0-100)
        ──────────────────────────────────────────────────
        If WR < 40%:  S₃ = 20
        If 40% ≤ WR < 50%:  S₃ = 40 + (WR - 0.40) × 200
        If 50% ≤ WR < 60%:  S₃ = 60 + (WR - 0.50) × 250
        If WR ≥ 60%:  S₃ = min(100, 85 + (WR - 0.60) × 150)
        Weight₃ = 0.25
        
        Component 4: Risk/Reward Score (0-100)
        ──────────────────────────────────────
        If R:R < 0.8:  S₄ = 20
        If 0.8 ≤ R:R < 1.2:  S₄ = 50
        If 1.2 ≤ R:R < 1.8:  S₄ = 70
        If 1.8 ≤ R:R < 2.5:  S₄ = 85
        If R:R ≥ 2.5:  S₄ = 95
        Weight₄ = 0.20
        
        FINAL SCORE:
        ───────────
        Total = S₁×0.30 + S₂×0.25 + S₃×0.25 + S₄×0.20
        
        DECISION:
        ────────
        Allowed = (Total ≥ min_quality_score)
        
        EXAMPLE:
        ───────
        Signal: 0.75 → S₁ = 75
        Market: TRENDING_UP, Strategy: trend_following → S₂ = 90
        Historical WR: 58% → S₃ = 80
        R:R: 2.1 → S₄ = 85
        
        Total = 75×0.30 + 90×0.25 + 80×0.25 + 85×0.20
              = 22.5 + 22.5 + 20.0 + 17.0
              = 82.0/100
        
        If min_quality_score = 60, then Allowed = True
        
        Args:
            signal_confidence: Signal strength (0.0-1.0)
            market_regime: Current market regime
            strategy_type: Type of strategy (trend_following, mean_reversion, etc.)
            historical_win_rate: Strategy's historical win rate (optional)
            risk_reward_ratio: Current trade R:R ratio (optional)
            strategy_metadata: Additional strategy info
            
        Returns:
            (total_score, allowed, component_scores) where:
            - total_score: 0-100 quality score
            - allowed: True if score >= threshold
            - component_scores: Breakdown by component
        """
        if not self.enable_scoring:
            return 100.0, True, {}
        
        component_scores = {}
        
        # 1. Signal Strength Score (0-100)
        signal_score = signal_confidence * 100
        component_scores['signal_strength'] = signal_score
        
        # 2. Market State Match Score (0-100)
        market_match_score = self._calculate_market_match_score(
            market_regime,
            strategy_type
        )
        component_scores['market_state_match'] = market_match_score
        
        # 3. Historical Performance Score (0-100)
        historical_score = self._calculate_historical_score(historical_win_rate)
        component_scores['historical_performance'] = historical_score
        
        # 4. Risk/Reward Score (0-100)
        rr_score = self._calculate_risk_reward_score(risk_reward_ratio)
        component_scores['risk_reward_ratio'] = rr_score
        
        # Calculate weighted total
        total_score = sum(
            component_scores[component] * self.weights[component]
            for component in self.weights.keys()
        )
        
        # Update statistics
        self.stats['total_scored'] += 1
        self.stats['scores'].append(total_score)
        
        # Keep only last 100 scores for avg calculation
        if len(self.stats['scores']) > 100:
            self.stats['scores'] = self.stats['scores'][-100:]
        
        self.stats['avg_score'] = sum(self.stats['scores']) / len(self.stats['scores'])
        
        allowed = total_score >= self.min_quality_score
        
        if allowed:
            self.stats['passed'] += 1
        else:
            self.stats['blocked'] += 1
        
        return total_score, allowed, component_scores
    
    def _calculate_market_match_score(
        self,
        market_regime: str,
        strategy_type: str
    ) -> float:
        """
        Score how well strategy matches current market conditions
        
        Returns: 0-100 score
        """
        # Define compatibility matrix
        compatibility = {
            'trend_following': {
                'TRENDING_UP': 90,
                'TRENDING_DOWN': 90,
                'RANGING': 30,
                'VOLATILE': 50,
                'QUIET': 40,
                'UNKNOWN': 50
            },
            'mean_reversion': {
                'TRENDING_UP': 40,
                'TRENDING_DOWN': 40,
                'RANGING': 90,
                'VOLATILE': 30,
                'QUIET': 70,
                'UNKNOWN': 50
            },
            'breakout': {
                'TRENDING_UP': 70,
                'TRENDING_DOWN': 70,
                'RANGING': 50,
                'VOLATILE': 40,
                'QUIET': 80,
                'UNKNOWN': 50
            },
            'volatility': {
                'TRENDING_UP': 50,
                'TRENDING_DOWN': 50,
                'RANGING': 40,
                'VOLATILE': 95,
                'QUIET': 20,
                'UNKNOWN': 50
            },
            'generic': {
                'TRENDING_UP': 70,
                'TRENDING_DOWN': 70,
                'RANGING': 70,
                'VOLATILE': 60,
                'QUIET': 60,
                'UNKNOWN': 50
            }
        }
        
        strategy_scores = compatibility.get(strategy_type, compatibility['generic'])
        return strategy_scores.get(market_regime, 50.0)
    
    def _calculate_historical_score(self, historical_win_rate: Optional[float]) -> float:
        """
        Score based on historical performance
        
        Returns: 0-100 score
        """
        if historical_win_rate is None:
            return 50.0  # Neutral score if unknown
        
        # Map win rate to score
        # 40% win rate = 40 score
        # 55% win rate = 75 score
        # 70% win rate = 100 score
        
        if historical_win_rate < 0.40:
            return 20.0
        elif historical_win_rate < 0.50:
            # 40-50% -> 40-60 score
            return 40 + (historical_win_rate - 0.40) * 200
        elif historical_win_rate < 0.60:
            # 50-60% -> 60-85 score
            return 60 + (historical_win_rate - 0.50) * 250
        else:
            # 60%+ -> 85-100 score
            return min(100, 85 + (historical_win_rate - 0.60) * 150)
    
    def _calculate_risk_reward_score(self, risk_reward_ratio: Optional[float]) -> float:
        """
        Score based on risk/reward ratio
        
        Returns: 0-100 score
        """
        if risk_reward_ratio is None:
            return 60.0  # Neutral score if unknown
        
        # Ideal R:R is 2:1 or better
        # Poor R:R is below 1:1
        
        if risk_reward_ratio < 0.8:
            return 20.0  # Poor R:R
        elif risk_reward_ratio < 1.2:
            return 50.0  # Acceptable
        elif risk_reward_ratio < 1.8:
            return 70.0  # Good
        elif risk_reward_ratio < 2.5:
            return 85.0  # Great
        else:
            return 95.0  # Excellent
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scorer statistics"""
        return {
            'enabled': self.enable_scoring,
            'min_quality_score': self.min_quality_score,
            'total_scored': self.stats['total_scored'],
            'passed': self.stats['passed'],
            'blocked': self.stats['blocked'],
            'avg_score': self.stats['avg_score'],
            'pass_rate': self.stats['passed'] / self.stats['total_scored'] if self.stats['total_scored'] > 0 else 0
        }
    
    def generate_report(self) -> str:
        """Generate quality scorer report"""
        stats = self.get_stats()
        
        lines = []
        lines.append("=" * 60)
        lines.append("TRADE QUALITY SCORER REPORT")
        lines.append("=" * 60)
        lines.append(f"Status: {'🟢 ENABLED' if stats['enabled'] else '🔴 DISABLED'}")
        lines.append(f"Min Quality Score: {stats['min_quality_score']:.1f}/100")
        lines.append("")
        lines.append(f"Total Scored: {stats['total_scored']}")
        lines.append(f"Passed: {stats['passed']} ({stats['pass_rate']:.1%})")
        lines.append(f"Blocked: {stats['blocked']}")
        lines.append(f"Avg Score: {stats['avg_score']:.1f}/100")
        lines.append("")
        lines.append("Score Component Weights:")
        for component, weight in self.weights.items():
            lines.append(f"  {component}: {weight:.0%}")
        
        return '\n'.join(lines)
