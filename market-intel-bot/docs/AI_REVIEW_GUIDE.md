# Periodic AI Review Feature - Usage Guide

## Overview

This implementation adds periodic AI review functionality to the market-intel-bot, implementing the "半旁路" (semi-bypass) plan. When the AI reviewer detects a `risk_off` market state, it automatically sets global hold flags to stop trading execution.

## Configuration

Configure the feature using environment variables:

```bash
# Enable/disable AI review (default: true)
ENABLE_MARKET_INTEL_AI=true

# Review interval in seconds (default: 1800 = 30 minutes)
MARKET_INTEL_AI_REVIEW_SECONDS=1800

# Output file path (default: store/ai_intel/latest.json)
MARKET_INTEL_AI_OUTPUT_FILE=store/ai_intel/latest.json
```

## How It Works

### 1. Periodic Review Trigger
- AI review runs every 30 minutes by default (configurable)
- Minimum interval is 60 seconds to prevent excessive API calls
- First run triggers immediately (when `_last_ai_review_ts == 0.0`)

### 2. AI Snapshot Creation
The bot creates a compact snapshot from the current payload:
```json
{
  "ts": 1234567890.123,
  "time": "2024-01-01T12:00:00",
  "timeframe": "15m",
  "topn": [...],
  "universe_size": 80
}
```

### 3. AI Analysis
Calls `market_intel_ai.run_market_intel(snapshot)` which returns:
```json
{
  "market_state": "risk_off",
  "recommendation": "...",
  "meta": {
    "model": "openai",
    "generated_at": "2024-01-01T12:00:00Z"
  }
}
```

### 4. Result Publishing
The AI result is attached to the TopN payload:
```json
{
  "ts": 1234567890.123,
  "time": "2024-01-01T12:00:00",
  "timeframe": "15m",
  "universe_size": 80,
  "topn": [...],
  "ai_intel": {
    "market_state": "risk_off",
    ...
  },
  "global_hold": true,
  "intel_global_hold": true
}
```

### 5. Persistence
AI results are saved to two locations:
1. **TopN file** (`store/topn/latest.json`) - includes AI intel in main payload
2. **AI output file** (`store/ai_intel/latest.json`) - standalone AI result

### 6. Risk-Off Detection
Checks fields: `market_state`, `state`, or `status`  
Accepts: `"risk_off"`, `"risk-off"`, `"risk off"` (case-insensitive)  
When detected: Sets both `global_hold` and `intel_global_hold` to `true`

### 7. Executor Integration
Executors read TopN file and check global_hold flags to stop trading.

## Error Handling

All errors are handled gracefully with proper logging:
- AI call fails → logged, publishing continues
- File write fails → logged, AI intel still attached
- State extraction fails → logged, no hold flags set

No AI error will block normal TopN publishing.

## Testing

Run the test suite:
```bash
cd market-intel-bot
python3 scripts/test_ai_review.py
```

## Security

✅ **CodeQL Check**: No vulnerabilities detected  
✅ Proper error handling prevents information leakage  
✅ File paths validated before writing  
✅ API calls properly wrapped in try/except

## Files Modified

1. `market-intel-bot/src/settings.py` - Added 3 configuration fields
2. `market-intel-bot/pipeline/intel_runner.py` - Added AI review logic
3. `.gitignore` - Exclude build artifacts
4. `market-intel-bot/scripts/test_ai_review.py` - Test suite
