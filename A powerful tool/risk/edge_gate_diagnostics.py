

"""
EdgeGate v2 Diagnostic Logger

Tracks and reports reasons for BLOCK decisions to diagnose "no orders" issues.
"""

from __future__ import annotations
print("🔥 LOADED EdgeGate Diagnostics FROM:", __file__)
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import json
from collections import Counter, defaultdict


class EdgeGateDiagnostics:
    """
    Tracks EdgeGate v2 decision statistics for diagnostics
    
    Helps diagnose "20 hours without placing an order" issues by:
    - Recording all BLOCK/PROBE/FULL decisions
    - Tracking block reason distribution
    - Monitoring edge_percentile trends
    - Identifying threshold tuning opportunities
    """
    
    def __init__(self, log_dir: str = "logs/edge_gate_diagnostics"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory statistics
        self._decision_counts: Counter = Counter()
        self._block_reasons: Counter = Counter()
        self._probe_counts: Counter = Counter()
        
        # Track values for analysis
        self._recent_decisions: List[Dict[str, Any]] = []
        self._max_recent = 1000
        
        # Daily statistics
        self._current_date = ""
        self._daily_stats: Dict[str, Any] = defaultdict(int)
    
    def record_decision(
        self,
        state: str,
        reason: str,
        net_edge: float,
        confidence: float,
        edge_percentile: float,
        position_multiplier: float,
        symbol: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Record an EdgeGate v2 decision
        
        Args:
            state: Decision state (BLOCK/PROBE/FULL)
            reason: Explanation string
            net_edge: Net edge value
            confidence: Confidence value
            edge_percentile: Percentile rank
            position_multiplier: Applied multiplier
            symbol: Trading symbol
            timestamp: Decision timestamp (defaults to now)
        """
        timestamp = timestamp or datetime.now(timezone.utc)
        date_str = timestamp.strftime("%Y-%m-%d")
        
        # Update daily statistics if date changed
        if self._current_date != date_str:
            if self._current_date:
                self._save_daily_stats()
            self._current_date = date_str
            self._daily_stats = defaultdict(int)
        
        # Track decision counts
        self._decision_counts[state] += 1
        self._daily_stats[f"{state}_count"] += 1
        
        # Track block reasons
        if state == "BLOCK":
            self._block_reasons[reason] += 1
            self._daily_stats[f"block_{reason}"] += 1
        elif state == "PROBE":
            probe_type = f"probe_{position_multiplier}"
            self._probe_counts[probe_type] += 1
            self._daily_stats[f"probe_{position_multiplier}_count"] += 1
        
        # Store recent decisions for detailed analysis
        decision_record = {
            "timestamp": timestamp.isoformat(),
            "state": state,
            "reason": reason,
            "net_edge": net_edge,
            "confidence": confidence,
            "edge_percentile": edge_percentile,
            "position_multiplier": position_multiplier,
            "symbol": symbol,
        }
        
        self._recent_decisions.append(decision_record)
        
        # Trim if exceeds max
        if len(self._recent_decisions) > self._max_recent:
            self._recent_decisions = self._recent_decisions[-self._max_recent:]
        
        # Write to log file (append mode for streaming)
        log_file = self.log_dir / f"decisions_{date_str}.jsonl"
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(decision_record) + "\n")
        except Exception as e:
            print(f"[EdgeGateDiagnostics] Failed to write log: {e}")
    
    def get_block_reasons_distribution(self) -> Dict[str, int]:
        """Get distribution of block reasons"""
        return dict(self._block_reasons)
    
    def get_decision_summary(self) -> Dict[str, Any]:
        """Get summary of all decisions"""
        total = sum(self._decision_counts.values())
        
        return {
            "total_decisions": total,
            "decision_counts": dict(self._decision_counts),
            "block_reasons": dict(self._block_reasons),
            "probe_types": dict(self._probe_counts),
            "block_rate": self._decision_counts["BLOCK"] / total if total > 0 else 0,
            "probe_rate": self._decision_counts["PROBE"] / total if total > 0 else 0,
            "full_rate": self._decision_counts["FULL"] / total if total > 0 else 0,
        }
    
    def get_recent_blocks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent BLOCK decisions for analysis"""
        blocks = [d for d in self._recent_decisions if d["state"] == "BLOCK"]
        return blocks[-limit:] if blocks else []
    
    def analyze_edge_percentiles(self) -> Dict[str, Any]:
        """Analyze edge_percentile distribution to identify tuning opportunities"""
        if not self._recent_decisions:
            return {"message": "No decisions recorded yet"}
        
        percentiles = [d["edge_percentile"] for d in self._recent_decisions]
        percentiles.sort()
        
        n = len(percentiles)
        
        return {
            "count": n,
            "min": percentiles[0],
            "max": percentiles[-1],
            "p10": percentiles[int(n * 0.1)] if n > 0 else 0,
            "p25": percentiles[int(n * 0.25)] if n > 0 else 0,
            "p50": percentiles[int(n * 0.5)] if n > 0 else 0,
            "p75": percentiles[int(n * 0.75)] if n > 0 else 0,
            "p90": percentiles[int(n * 0.9)] if n > 0 else 0,
            "below_60": sum(1 for p in percentiles if p < 0.60),
            "60_to_75": sum(1 for p in percentiles if 0.60 <= p < 0.75),
            "75_to_90": sum(1 for p in percentiles if 0.75 <= p < 0.90),
            "above_90": sum(1 for p in percentiles if p >= 0.90),
        }
    
    def generate_diagnostic_report(self) -> str:
        """Generate a diagnostic report for troubleshooting"""
        summary = self.get_decision_summary()
        percentile_analysis = self.analyze_edge_percentiles()
        recent_blocks = self.get_recent_blocks(limit=5)
        
        lines = []
        lines.append("=" * 80)
        lines.append("EDGEGATE V2 DIAGNOSTIC REPORT")
        lines.append("=" * 80)
        lines.append("")
        
        lines.append("DECISION SUMMARY:")
        lines.append(f"  Total decisions: {summary['total_decisions']}")
        lines.append(f"  BLOCK rate: {summary['block_rate']:.1%}")
        lines.append(f"  PROBE rate: {summary['probe_rate']:.1%}")
        lines.append(f"  FULL rate: {summary['full_rate']:.1%}")
        lines.append("")
        
        lines.append("BLOCK REASONS DISTRIBUTION:")
        for reason, count in sorted(summary['block_reasons'].items(), key=lambda x: -x[1]):
            pct = count / summary['total_decisions'] * 100 if summary['total_decisions'] > 0 else 0
            lines.append(f"  {reason}: {count} ({pct:.1f}%)")
        lines.append("")
        
        lines.append("EDGE PERCENTILE ANALYSIS:")
        lines.append(f"  Below 0.60 (BLOCKED): {percentile_analysis.get('below_60', 0)}")
        lines.append(f"  0.60-0.75 (PROBE small): {percentile_analysis.get('60_to_75', 0)}")
        lines.append(f"  0.75-0.90 (PROBE medium): {percentile_analysis.get('75_to_90', 0)}")
        lines.append(f"  Above 0.90 (FULL): {percentile_analysis.get('above_90', 0)}")
        lines.append(f"  P50: {percentile_analysis.get('p50', 0):.3f}")
        lines.append(f"  P90: {percentile_analysis.get('p90', 0):.3f}")
        lines.append("")
        
        lines.append("RECENT BLOCKS (last 5):")
        if recent_blocks:
            for block in recent_blocks:
                lines.append(f"  {block['timestamp'][:19]} {block['symbol']} - {block['reason']}")
                lines.append(f"    net_edge={block['net_edge']:.6f} conf={block['confidence']:.3f} pct={block['edge_percentile']:.3f}")
        else:
            lines.append("  No blocks recorded")
        lines.append("")
        
        lines.append("=" * 80)
        lines.append("RECOMMENDATIONS:")
        lines.append("=" * 80)
        
        # Provide recommendations based on statistics
        if summary['block_rate'] > 0.90:
            lines.append("  ⚠️  VERY HIGH BLOCK RATE (>90%)")
            lines.append("     → Consider lowering percentile thresholds")
            lines.append("     → Check if edge_stats has sufficient history")
        
        if percentile_analysis.get('below_60', 0) > percentile_analysis.get('count', 1) * 0.8:
            lines.append("  ⚠️  Most signals below 60th percentile")
            lines.append("     → Consider lowering percentile_probe_small threshold")
            lines.append("     → Verify net_edge calculation is correct")
        
        top_block_reason = max(summary['block_reasons'].items(), key=lambda x: x[1])[0] if summary['block_reasons'] else None
        if top_block_reason:
            lines.append(f"  ℹ️  Top block reason: {top_block_reason}")
            if "confidence" in top_block_reason:
                lines.append("     → Consider lowering min_confidence threshold")
            elif "percentile" in top_block_reason:
                lines.append("     → Consider lowering percentile thresholds")
            elif "net_edge" in top_block_reason:
                lines.append("     → Verify edge calculation includes correct fees/slippage")
        
        lines.append("")
        
        return "\n".join(lines)
    
    def _save_daily_stats(self) -> None:
        """Save daily statistics to file"""
        if not self._current_date:
            return
        
        stats_file = self.log_dir / f"daily_stats_{self._current_date}.json"
        
        try:
            with open(stats_file, "w") as f:
                json.dump(dict(self._daily_stats), f, indent=2)
        except Exception as e:
            print(f"[EdgeGateDiagnostics] Failed to save daily stats: {e}")


def create_default_diagnostics() -> EdgeGateDiagnostics:
    """Create EdgeGateDiagnostics with default configuration"""
    return EdgeGateDiagnostics()
