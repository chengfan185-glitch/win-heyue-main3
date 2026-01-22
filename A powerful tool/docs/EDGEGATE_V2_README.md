# EdgeGate v2 - PROBE Position Mechanism

## Overview

EdgeGate v2 implements a 3-state gating system (BLOCK/PROBE/FULL) to solve the "20 hours without placing an order" problem by allowing "weak positive expectation" trades with small positions while maintaining the Edge baseline (prohibiting negative expectation trades).

## Problem Statement

Users reported that the system runs for 20 hours without placing any orders, indicating overly strict admission criteria. The traditional binary gate (allow/block) was too conservative, rejecting potentially profitable trades with modest positive expectation.

## Solution

EdgeGate v2 introduces a graduated approach:

- **BLOCK** (0x): Negative expectation or insufficient confidence → No trade
- **PROBE** (0.10x or 0.25x): Weak positive expectation → Small position for controlled trial
- **FULL** (1.0x): Strong positive expectation → Full position size

## Architecture

### Components

1. **EdgeGateV2** (`risk/edge_gate_v2.py`): Core decision logic
2. **EdgeStats** (`risk/edge_stats.py`): Historical edge percentile tracking
3. **EdgeGateDiagnostics** (`risk/edge_gate_diagnostics.py`): Decision tracking and diagnostics

### Decision Flow

```
Signal → Calculate net_edge → Get edge_percentile → EdgeGateV2.evaluate() → 
  → (state, position_multiplier, reason) → Adjust position size → Execute trade
```

## Decision Rules

### Blocking Conditions (Priority Order)

1. `net_edge <= 0` → BLOCK (negative expectation)
2. `confidence < 0.55` → BLOCK (insufficient confidence)
3. `edge_percentile < 0.60` → BLOCK (weak edge compared to history)

### Position Sizing

| Edge Percentile | State        | Position Multiplier |
|----------------|--------------|---------------------|
| < 0.60         | BLOCK        | 0.00                |
| [0.60, 0.75)   | PROBE small  | 0.10                |
| [0.75, 0.90)   | PROBE medium | 0.25                |
| >= 0.90        | FULL         | 1.00                |

### PROBE State Restrictions

When in PROBE state, the following additional risk controls apply:

- **Tighter stop loss**: 0.7x of base stop loss distance
- **No pyramiding**: Cannot add to existing positions
- **Shorter max hold time**: 0.5x of base hold time (future enhancement)
- **Daily loss limits**: Separate tracking for PROBE trades (future enhancement)

## EdgeStats: Historical Percentile Tracking

### Key Features

1. **Symbol/Direction/Timeframe Separation**: 
   - Each (symbol, direction, timeframe) tuple tracked independently
   - Ensures apples-to-apples comparison (BTCUSDT LONG 15m vs BTCUSDT LONG 15m)

2. **Minimum Sample Enforcement**:
   - Requires minimum 50 samples before returning valid percentile
   - Returns `None` when insufficient samples
   - System forces conservative PROBE (0.10x) when `None`

3. **Rolling Window**:
   - Default 1000 most recent edges per key
   - Prevents stale data pollution
   - Adapts to changing market conditions

4. **No Future Function Bias**:
   - Edges recorded BEFORE trade outcome is known
   - Preserves statistical integrity

### Data Structure

```python
EdgeStatsKey = (symbol, direction, timeframe)
# Example: ("BTCUSDT", "LONG", "15m")

EdgeStatsValue = {
    "edge_history": [sorted list of net_edge values],
    "max_window": 1000,
    "min_sample": 50
}
```

### Percentile Calculation

```python
edge_percentile = edge_stats.get_edge_percentile(
    net_edge=0.001,
    symbol="BTCUSDT",
    direction="LONG",
    timeframe="15m"
)
# Returns: 0.75 (this edge is at 75th percentile of BTCUSDT LONG 15m history)
# Returns: None (if < 50 samples for this key)
```

## Configuration

### Environment Variables

```bash
# EdgeGate v2 Configuration
EDGE_GATE_V2_MIN_CONFIDENCE=0.55          # Minimum confidence threshold
EDGE_GATE_V2_PERCENTILE_PROBE_SMALL=0.60  # Percentile for small probe (0.10x)
EDGE_GATE_V2_PERCENTILE_PROBE_MEDIUM=0.75 # Percentile for medium probe (0.25x)
EDGE_GATE_V2_PERCENTILE_FULL=0.90         # Percentile for full position (1.0x)
EDGE_GATE_V2_PROBE_SMALL_MULT=0.10        # Small probe multiplier
EDGE_GATE_V2_PROBE_MEDIUM_MULT=0.25       # Medium probe multiplier
EDGE_GATE_V2_FULL_MULT=1.0                # Full position multiplier
```

### Defaults

All thresholds have sensible defaults if environment variables are not set:

- `min_confidence`: 0.55
- `percentile_probe_small`: 0.60
- `percentile_probe_medium`: 0.75
- `percentile_full`: 0.90
- Position multipliers: 0.10, 0.25, 1.0

## Usage Example

### In Trading Pipeline

```python
from risk.edge_gate_v2 import EdgeGateV2, create_default_edge_gate_v2
from risk.edge_stats import EdgeStats, create_default_edge_stats
from risk.edge_gate_diagnostics import EdgeGateDiagnostics, create_default_diagnostics

# Initialize components
edge_gate_v2 = create_default_edge_gate_v2()
edge_stats = create_default_edge_stats()
edge_diagnostics = create_default_diagnostics()

# For each trading signal
net_edge = 0.0015  # After fees/slippage
confidence = 0.72
symbol = "BTCUSDT"
direction = "LONG"  # or "SHORT"
timeframe = "15m"

# Get percentile from history
edge_percentile = edge_stats.get_edge_percentile(
    net_edge=net_edge,
    symbol=symbol,
    direction=direction,
    timeframe=timeframe
)

# Handle insufficient samples
if edge_percentile is None:
    print("Insufficient samples - forcing conservative PROBE")
    edge_percentile = 0.60
    # Force PROBE small (0.10x)

# Evaluate with EdgeGate v2
result = edge_gate_v2.evaluate(
    net_edge=net_edge,
    confidence=confidence,
    edge_percentile=edge_percentile
)

# Log for diagnostics
edge_diagnostics.record_decision(
    state=result.state,
    reason=result.reason,
    net_edge=net_edge,
    confidence=confidence,
    edge_percentile=edge_percentile,
    position_multiplier=result.position_multiplier,
    symbol=symbol
)

# Apply decision
if result.state == "BLOCK":
    print(f"Trade blocked: {result.reason}")
    return

# Calculate adjusted position size
base_size = 100.0  # USDT
adjusted_size = base_size * result.position_multiplier

print(f"Trade approved: {result.state} ({result.position_multiplier:.2f}x)")
print(f"Position size: {adjusted_size:.2f} USDT")

# Execute trade with adjusted size...

# Record edge for future percentile calculations
# CRITICAL: Do this BEFORE trade outcome is known
edge_stats.record_edge(
    net_edge=net_edge,
    symbol=symbol,
    direction=direction,
    timeframe=timeframe,
    signal_type=f"ml_{direction.lower()}",
    metadata={"confidence": confidence, "state": result.state}
)
```

## Diagnostics

### View Decision Statistics

```python
# Get summary
summary = edge_diagnostics.get_decision_summary()
print(f"Total decisions: {summary['total_decisions']}")
print(f"Block rate: {summary['block_rate']:.1%}")
print(f"Probe rate: {summary['probe_rate']:.1%}")
print(f"Full rate: {summary['full_rate']:.1%}")

# View block reasons
for reason, count in summary['block_reasons'].items():
    print(f"{reason}: {count}")

# Generate full report
report = edge_diagnostics.generate_diagnostic_report()
print(report)
```

### Analyze Edge Percentile Distribution

```python
analysis = edge_diagnostics.analyze_edge_percentiles()
print(f"Signals below 60th percentile: {analysis['below_60']}")
print(f"Signals 60-75th percentile: {analysis['60_to_75']}")
print(f"Signals 75-90th percentile: {analysis['75_to_90']}")
print(f"Signals above 90th percentile: {analysis['above_90']}")
```

### Log Files

Diagnostic logs are written to:
- `logs/edge_gate_diagnostics/decisions_YYYY-MM-DD.jsonl`: All decisions
- `logs/edge_gate_diagnostics/daily_stats_YYYY-MM-DD.json`: Daily statistics
- `logs/edge_stats/edge_history.json`: Historical edge data (persistent)

## Troubleshooting "No Orders" Issues

If the system is not placing orders:

1. **Check block reasons**:
   ```python
   report = edge_diagnostics.generate_diagnostic_report()
   print(report)
   ```

2. **Common Issues**:
   - **High `net_edge <= 0` blocks**: Fee/slippage estimates too high or signals have no real edge
   - **High `confidence_too_low` blocks**: Lower `min_confidence` threshold or improve model
   - **High `edge_percentile_too_low` blocks**: Signals consistently below 60th percentile
     - Check if EdgeStats has sufficient history
     - Consider lowering `percentile_probe_small` threshold
     - Verify net_edge calculation is correct

3. **EdgeStats Sample Size**:
   ```python
   stats = edge_stats.get_statistics(
       symbol="BTCUSDT",
       direction="LONG",
       timeframe="15m"
   )
   if not stats.get('sufficient_samples'):
       print("Insufficient samples - will force PROBE mode")
   ```

4. **Adjust Thresholds**:
   - If block rate > 90%, consider lowering thresholds
   - If most signals below 60th percentile, lower `percentile_probe_small`
   - If confidence consistently low, lower `min_confidence`

## Testing

Run comprehensive test suite:

```bash
# All EdgeGate v2 tests
python3 -m unittest tests.test_edge_gate_v2 -v

# All EdgeStats tests
python3 -m unittest tests.test_edge_stats -v

# All tests together
python3 -m unittest tests.test_edge_gate_v2 tests.test_edge_stats -v
```

## Production Safety

### No Future Function

EdgeStats records edges **BEFORE** trade outcomes are known. This ensures:
- No look-ahead bias
- Valid statistical inference
- Production-safe percentile calculations

### Sample Size Validation

EdgeStats enforces minimum 50 samples before returning percentiles:
- Prevents unreliable statistics from small samples
- Forces conservative PROBE mode when insufficient data
- Builds up sample size organically over time

### Rolling Windows

1000-record rolling windows per (symbol, direction, timeframe):
- Adapts to changing market conditions
- Prevents stale data pollution
- Maintains statistical relevance

## Philosophy

- **EdgeStats is the system's "statistical conscience"**
- **PROBE is the system's "rational exploration mechanism"**
- **FULL is the system's "attack mode"**

A system that:
- Never PROBEs → Never learns
- Only PROBEs → Never captures full opportunities
- Distinguishes PROBE from FULL → Can survive in real markets

## Future Enhancements

1. **PROBE Daily Loss Limits**: Separate loss tracking for PROBE trades
2. **Max Hold Time Enforcement**: Shorter hold times for PROBE positions
3. **Pyramiding Prevention**: Explicit check to prevent adding to PROBE positions
4. **State Transition Tracking**: Monitor PROBE → FULL transitions
5. **Multi-Symbol Correlation**: Consider cross-symbol edge correlation

## References

- Implementation: `risk/edge_gate_v2.py`, `risk/edge_stats.py`
- Integration: `pipeline/futures_runner_v2.py`
- Tests: `tests/test_edge_gate_v2.py`, `tests/test_edge_stats.py`
- Diagnostics: `risk/edge_gate_diagnostics.py`
