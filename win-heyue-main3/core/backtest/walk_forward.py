# core/backtest/walk_forward.py
"""
Walk-Forward Validation

Performs walk-forward analysis to validate strategy robustness across different time periods.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime, timezone
import time
import json
from pathlib import Path

from .backtest_engine import BacktestEngine, BacktestResult


@dataclass
class WalkForwardWindow:
    """Single window in walk-forward analysis"""
    window_id: int
    
    # Data ranges
    train_start: float
    train_end: float
    test_start: float
    test_end: float
    
    # Results
    train_result: Optional[BacktestResult] = None
    test_result: Optional[BacktestResult] = None
    
    # Performance comparison
    train_pnl: float = 0.0
    test_pnl: float = 0.0
    train_win_rate: float = 0.0
    test_win_rate: float = 0.0
    
    # Overfitting detection
    performance_degradation: float = 0.0  # (train_pnl - test_pnl) / train_pnl
    passed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'window_id': self.window_id,
            'train_start': self.train_start,
            'train_start_iso': datetime.fromtimestamp(self.train_start, tz=timezone.utc).isoformat(),
            'train_end': self.train_end,
            'train_end_iso': datetime.fromtimestamp(self.train_end, tz=timezone.utc).isoformat(),
            'test_start': self.test_start,
            'test_start_iso': datetime.fromtimestamp(self.test_start, tz=timezone.utc).isoformat(),
            'test_end': self.test_end,
            'test_end_iso': datetime.fromtimestamp(self.test_end, tz=timezone.utc).isoformat(),
            'train_pnl': self.train_pnl,
            'test_pnl': self.test_pnl,
            'train_win_rate': self.train_win_rate,
            'test_win_rate': self.test_win_rate,
            'performance_degradation': self.performance_degradation,
            'passed': self.passed
        }


@dataclass
class WalkForwardResult:
    """Results from walk-forward analysis"""
    strategy_id: str
    version: str
    
    # Windows
    windows: List[WalkForwardWindow] = field(default_factory=list)
    total_windows: int = 0
    passed_windows: int = 0
    
    # Aggregate metrics
    avg_train_pnl: float = 0.0
    avg_test_pnl: float = 0.0
    avg_degradation: float = 0.0
    consistency_score: float = 0.0  # % of windows passed
    
    # Overall pass/fail
    passed: bool = False
    
    # Metadata
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'strategy_id': self.strategy_id,
            'version': self.version,
            'windows': [w.to_dict() for w in self.windows],
            'total_windows': self.total_windows,
            'passed_windows': self.passed_windows,
            'avg_train_pnl': self.avg_train_pnl,
            'avg_test_pnl': self.avg_test_pnl,
            'avg_degradation': self.avg_degradation,
            'consistency_score': self.consistency_score,
            'passed': self.passed,
            'config': self.config,
            'created_at': self.created_at,
            'created_at_iso': datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat()
        }
    
    def save(self, output_dir: str):
        """Save walk-forward result to file"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"walkforward_{self.strategy_id}_{self.version}_{int(self.created_at)}.json"
        filepath = output_path / filename
        
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        
        print(f"[WalkForwardResult] Saved to {filepath}")


class WalkForwardValidator:
    """
    Walk-Forward Validation for Strategy Robustness
    
    Splits data into multiple train/test windows and validates
    strategy performance consistency across different periods.
    """
    
    def __init__(
        self,
        train_window_size: int = 1000,  # bars
        test_window_size: int = 200,    # bars
        step_size: int = 200,           # bars to move forward
        initial_capital: float = 10000.0
    ):
        self.train_window_size = train_window_size
        self.test_window_size = test_window_size
        self.step_size = step_size
        self.initial_capital = initial_capital
    
    def validate(
        self,
        strategy_func: Callable,
        data: List[Dict[str, Any]],
        strategy_id: str,
        version: str,
        config: Optional[Dict[str, Any]] = None
    ) -> WalkForwardResult:
        """
        Perform walk-forward validation
        
        Args:
            strategy_func: Strategy function
            data: Historical data (bars/klines)
            strategy_id: Strategy identifier
            version: Strategy version
            config: Additional configuration
            
        Returns:
            WalkForwardResult with analysis across all windows
        """
        print(f"[WalkForward] Starting walk-forward validation for {strategy_id} v{version}")
        print(f"[WalkForward] Data: {len(data)} bars")
        print(f"[WalkForward] Train window: {self.train_window_size}, Test window: {self.test_window_size}")
        
        result = WalkForwardResult(
            strategy_id=strategy_id,
            version=version,
            config=config or {}
        )
        
        if len(data) < self.train_window_size + self.test_window_size:
            print(f"[WalkForward] ❌ Insufficient data: need at least {self.train_window_size + self.test_window_size} bars")
            return result
        
        # Create windows
        windows = self._create_windows(data)
        print(f"[WalkForward] Created {len(windows)} windows")
        
        # Run backtest for each window
        for window in windows:
            print(f"\n[WalkForward] Window {window.window_id + 1}/{len(windows)}")
            
            # Train phase
            train_data = data[window.window_id * self.step_size:
                            window.window_id * self.step_size + self.train_window_size]
            
            engine = BacktestEngine(initial_capital=self.initial_capital)
            train_result = engine.run(
                strategy_func=strategy_func,
                data=train_data,
                strategy_id=strategy_id,
                version=version,
                config={'phase': 'train', 'window': window.window_id}
            )
            
            window.train_result = train_result
            window.train_pnl = train_result.total_pnl
            window.train_win_rate = train_result.win_rate
            
            # Test phase
            test_start_idx = window.window_id * self.step_size + self.train_window_size
            test_end_idx = test_start_idx + self.test_window_size
            test_data = data[test_start_idx:test_end_idx]
            
            engine = BacktestEngine(initial_capital=self.initial_capital)
            test_result = engine.run(
                strategy_func=strategy_func,
                data=test_data,
                strategy_id=strategy_id,
                version=version,
                config={'phase': 'test', 'window': window.window_id}
            )
            
            window.test_result = test_result
            window.test_pnl = test_result.total_pnl
            window.test_win_rate = test_result.win_rate
            
            # Calculate degradation
            if window.train_pnl != 0:
                window.performance_degradation = (window.train_pnl - window.test_pnl) / abs(window.train_pnl)
            else:
                window.performance_degradation = 0.0
            
            # Evaluation: Window passes if test performance is not too much worse than train
            # Allow up to 50% degradation, and test must be profitable
            window.passed = (
                window.test_pnl > 0 and
                window.performance_degradation < 0.50 and
                test_result.win_rate >= 0.40
            )
            
            print(f"[WalkForward] Train PnL: {window.train_pnl:+.2f}, Test PnL: {window.test_pnl:+.2f}")
            print(f"[WalkForward] Degradation: {window.performance_degradation*100:+.1f}%")
            print(f"[WalkForward] Window result: {'✅ PASSED' if window.passed else '❌ FAILED'}")
            
            result.windows.append(window)
        
        # Calculate aggregate metrics
        result.total_windows = len(windows)
        result.passed_windows = sum(1 for w in windows if w.passed)
        
        if windows:
            result.avg_train_pnl = sum(w.train_pnl for w in windows) / len(windows)
            result.avg_test_pnl = sum(w.test_pnl for w in windows) / len(windows)
            result.avg_degradation = sum(w.performance_degradation for w in windows) / len(windows)
        
        result.consistency_score = result.passed_windows / result.total_windows if result.total_windows > 0 else 0.0
        
        # Overall pass: At least 70% of windows must pass
        result.passed = result.consistency_score >= 0.70
        
        print(f"\n[WalkForward] ═══════════════════════════════════════")
        print(f"[WalkForward] WALK-FORWARD VALIDATION COMPLETE")
        print(f"[WalkForward] ═══════════════════════════════════════")
        print(f"[WalkForward] Windows passed: {result.passed_windows}/{result.total_windows} ({result.consistency_score*100:.1f}%)")
        print(f"[WalkForward] Avg train PnL: {result.avg_train_pnl:+.2f}")
        print(f"[WalkForward] Avg test PnL: {result.avg_test_pnl:+.2f}")
        print(f"[WalkForward] Avg degradation: {result.avg_degradation*100:+.1f}%")
        print(f"[WalkForward] Overall result: {'✅ PASSED' if result.passed else '❌ FAILED'}")
        
        return result
    
    def _create_windows(self, data: List[Dict[str, Any]]) -> List[WalkForwardWindow]:
        """Create train/test windows"""
        windows = []
        window_id = 0
        
        while True:
            train_start_idx = window_id * self.step_size
            train_end_idx = train_start_idx + self.train_window_size
            test_start_idx = train_end_idx
            test_end_idx = test_start_idx + self.test_window_size
            
            # Check if we have enough data for this window
            if test_end_idx > len(data):
                break
            
            window = WalkForwardWindow(
                window_id=window_id,
                train_start=float(data[train_start_idx].get('timestamp', 0)),
                train_end=float(data[train_end_idx - 1].get('timestamp', 0)),
                test_start=float(data[test_start_idx].get('timestamp', 0)),
                test_end=float(data[test_end_idx - 1].get('timestamp', 0))
            )
            
            windows.append(window)
            window_id += 1
        
        return windows
    
    def generate_report(self, result: WalkForwardResult) -> str:
        """Generate detailed text report"""
        lines = []
        lines.append("=" * 80)
        lines.append(f"WALK-FORWARD VALIDATION REPORT")
        lines.append("=" * 80)
        lines.append(f"Strategy: {result.strategy_id} v{result.version}")
        lines.append(f"Windows: {result.total_windows}")
        lines.append(f"Passed: {result.passed_windows} ({result.consistency_score*100:.1f}%)")
        lines.append(f"Overall Status: {'✅ PASSED' if result.passed else '❌ FAILED'}")
        lines.append("")
        lines.append(f"Average Train PnL: {result.avg_train_pnl:+.2f}")
        lines.append(f"Average Test PnL: {result.avg_test_pnl:+.2f}")
        lines.append(f"Average Degradation: {result.avg_degradation*100:+.1f}%")
        lines.append("")
        lines.append("-" * 80)
        lines.append("Window Details:")
        lines.append("-" * 80)
        
        for window in result.windows:
            status = "✅" if window.passed else "❌"
            lines.append(f"\nWindow {window.window_id + 1}: {status}")
            lines.append(f"  Train: {datetime.fromtimestamp(window.train_start, tz=timezone.utc).strftime('%Y-%m-%d')} to "
                        f"{datetime.fromtimestamp(window.train_end, tz=timezone.utc).strftime('%Y-%m-%d')}")
            lines.append(f"  Test:  {datetime.fromtimestamp(window.test_start, tz=timezone.utc).strftime('%Y-%m-%d')} to "
                        f"{datetime.fromtimestamp(window.test_end, tz=timezone.utc).strftime('%Y-%m-%d')}")
            lines.append(f"  Train PnL: {window.train_pnl:+.2f} (Win rate: {window.train_win_rate:.2%})")
            lines.append(f"  Test PnL:  {window.test_pnl:+.2f} (Win rate: {window.test_win_rate:.2%})")
            lines.append(f"  Degradation: {window.performance_degradation*100:+.1f}%")
        
        lines.append("")
        lines.append("=" * 80)
        
        return '\n'.join(lines)
