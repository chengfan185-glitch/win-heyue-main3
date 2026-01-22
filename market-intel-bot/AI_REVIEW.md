# AI Selection Integration - Market Intel Bot

## Overview

The market-intel-bot now includes periodic AI selection functionality that picks 2-5 optimal targets from the Top10 candidates for execution.

## Features

### Periodic AI Selection
- Runs every 30 minutes by default (configurable)
- Analyzes market environment and risk assessment
- Selects 2-5 best targets from Top10 candidates
- Publishes AI selections alongside market intelligence data
- Executor/tool-bot trades ONLY the AI-recommended symbols

### AI-Powered Filtering
The AI evaluates:
- Current market environment (trend, volatility, risk)
- Each candidate's technical strength
- Risk level for each symbol
- Overall market conditions

Result: 2-5 carefully selected symbols with reasoning

## Configuration

Configure via environment variables:

```bash
# Enable/disable AI selection (default: true)
ENABLE_MARKET_INTEL_AI=true

# Review interval in seconds (default: 1800 = 30 minutes)
MARKET_INTEL_AI_REVIEW_SECONDS=1800

# Output file for AI results (default: store/ai_intel/latest.json)
MARKET_INTEL_AI_OUTPUT_FILE=store/ai_intel/latest.json
```

## Output Format

### TopN Payload with AI Selection
```json
{
  "ts": 1234567890.123,
  "time": "2024-01-01T12:00:00",
  "timeframe": "15m",
  "universe_size": 80,
  "topn": [
    {"symbol": "BTCUSDT", "score": 0.85, ...},
    {"symbol": "ETHUSDT", "score": 0.82, ...},
    {"symbol": "BNBUSDT", "score": 0.78, ...},
    ...10 candidates total
  ],
  "weights": {...},
  "ai_intel": {
    "market_environment": "Bullish trend with good volume",
    "recommended": [
      {
        "symbol": "BTCUSDT",
        "reason": "Strong breakout with volume confirmation",
        "risk_level": "low"
      },
      {
        "symbol": "ETHUSDT",
        "reason": "Following BTC momentum, good technical setup",
        "risk_level": "medium"
      }
    ],
    "excluded_symbols": [
      "BNBUSDT: Weak volume",
      "XRPUSDT: Too volatile for current conditions"
    ],
    "meta": {
      "model": "openai",
      "generated_at": "2024-01-01T12:00:00Z"
    }
  },
  "ai_recommended": [
    {
      "symbol": "BTCUSDT",
      "reason": "Strong breakout with volume confirmation",
      "risk_level": "low"
    },
    {
      "symbol": "ETHUSDT",
      "reason": "Following BTC momentum, good technical setup",
      "risk_level": "medium"
    }
  ]
}
```

### When No Recommendations (High Risk)
```json
{
  "ts": 1234567890.123,
  "time": "2024-01-01T12:00:00",
  "timeframe": "15m",
  "topn": [...],
  "ai_intel": {
    "market_environment": "High volatility, choppy conditions",
    "recommended": [],
    "excluded_symbols": [
      "All symbols excluded due to poor market conditions"
    ],
    "meta": {...}
  }
  // Note: No "ai_recommended" field when empty
}
```

## AI Result File

The AI results are also persisted separately to the configured output file:

```json
{
  "ts": 1234567890.123,
  "ai": {
    "market_environment": "Bullish trend with good volume",
    "recommended": [
      {
        "symbol": "BTCUSDT",
        "reason": "Strong breakout with volume confirmation",
        "risk_level": "low"
      }
    ],
    "excluded_symbols": [...],
    "meta": {...}
  }
}
```

## Executor Behavior

The executor/tool-bot should:
1. Read the published TopN payload
2. Check for `ai_recommended` field
3. **Trade ONLY the symbols in `ai_recommended`** (ignore other Top10)
4. If `ai_recommended` is absent or empty, skip trading for this cycle

## Selection Criteria

The AI considers:
- **Market Environment**: Overall trend, volatility, liquidity
- **Technical Strength**: Momentum, breakout quality, volume
- **Risk Assessment**: Volatility level, market structure
- **Diversification**: Avoid correlated assets if possible
- **Quantity**: Always 2-5 symbols (never more, sometimes less)

## Error Handling

- AI selection failures are logged but don't prevent normal publishing
- All AI operations wrapped in try/except for robustness
- If AI call fails, payload published without `ai_recommended` field
- TopN candidates always published regardless of AI status

## Testing

Run the integration tests to verify functionality:

```bash
cd market-intel-bot
python3 scripts/test_ai_review_integration.py
python3 scripts/test_ai_review_flow.py
```

## Architecture

The implementation uses:
- Existing `market_intel_ai.run_market_intel()` function with updated prompt
- Module-level timestamp tracker for review intervals
- Minimal changes to preserve existing behavior
- New `ai_recommended` field for executor consumption

## Compatibility

- No breaking changes to existing behavior
- TopN candidates unchanged - full list still available
- Backward compatible with systems that don't check AI fields
- Executor can choose to ignore AI recommendations if needed
