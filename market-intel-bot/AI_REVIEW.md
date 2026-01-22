# AI Review Integration - Market Intel Bot

## Overview

The market-intel-bot now includes periodic AI review functionality that analyzes market conditions and can trigger a global hold when risk is detected.

## Features

### Periodic AI Review
- Runs every 30 minutes by default (configurable)
- Analyzes market snapshot with top candidates
- Publishes AI results alongside market intelligence data
- Automatically sets global hold flags when risk detected

### Global Hold Mechanism
When the AI reviewer detects a `risk_off` market state, the system automatically sets:
- `global_hold: true` - Main hold flag
- `intel_global_hold: true` - Legacy compatibility flag

This triggers the executor/tool-bot to stop trading automatically.

## Configuration

Configure via environment variables:

```bash
# Enable/disable AI review (default: true)
ENABLE_MARKET_INTEL_AI=true

# Review interval in seconds (default: 1800 = 30 minutes)
MARKET_INTEL_AI_REVIEW_SECONDS=1800

# Output file for AI results (default: store/ai_intel/latest.json)
MARKET_INTEL_AI_OUTPUT_FILE=store/ai_intel/latest.json
```

## Output Format

### TopN Payload with AI Intel
```json
{
  "ts": 1234567890.123,
  "time": "2024-01-01T12:00:00",
  "timeframe": "15m",
  "universe_size": 80,
  "topn": [...],
  "weights": {...},
  "ai_intel": {
    "market_state": "trend",
    "strong_sectors": ["BTC", "ETH"],
    "meta": {
      "model": "openai",
      "generated_at": "2024-01-01T12:00:00Z"
    }
  }
}
```

### With Global Hold (Risk Off)
```json
{
  "ts": 1234567890.123,
  "time": "2024-01-01T12:00:00",
  "timeframe": "15m",
  "universe_size": 80,
  "topn": [...],
  "weights": {...},
  "ai_intel": {
    "market_state": "risk_off",
    "strong_sectors": [],
    "meta": {
      "model": "openai",
      "generated_at": "2024-01-01T12:00:00Z"
    }
  },
  "global_hold": true,
  "intel_global_hold": true
}
```

## AI Result File

The AI results are also persisted separately to the configured output file:

```json
{
  "ts": 1234567890.123,
  "ai": {
    "market_state": "risk_off",
    "strong_sectors": [],
    "meta": {
      "model": "openai",
      "generated_at": "2024-01-01T12:00:00Z"
    }
  }
}
```

## Risk Detection

The system checks for risk_off in multiple field names for robustness:
- `market_state`
- `state`
- `status`

Any of these containing `"risk_off"`, `"risk-off"`, or `"risk off"` (case-insensitive) will trigger the global hold.

## Error Handling

- AI review failures are logged but don't prevent normal publishing
- All AI operations wrapped in try/except for robustness
- If AI call fails, the bot continues with normal TopN publishing

## Testing

Run the integration tests to verify functionality:

```bash
cd market-intel-bot
python3 scripts/test_ai_review_integration.py
python3 scripts/test_ai_review_flow.py
```

## Architecture

The implementation uses:
- Existing `market_intel_ai.run_market_intel()` function
- Module-level timestamp tracker for review intervals
- Minimal changes to preserve existing behavior
- Dual compatibility flags (global_hold + intel_global_hold)

## Compatibility

- No breaking changes to existing behavior
- Works with existing executor/tool-bot implementations
- Backward compatible with systems that don't check AI fields
- Both hold flags ensure maximum compatibility with different executor versions
