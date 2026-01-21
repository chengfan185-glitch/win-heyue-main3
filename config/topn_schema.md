# TopN payload schema (stable contract)

The intel-bot writes `store/topn/latest.json` with the following schema:

```json
{
  "ts": 1730000000.123,
  "time": "2026-01-18T21:38:11",
  "timeframe": "15m",
  "universe_size": 80,
  "weights": {
    "w_trend": 1.0,
    "w_vol": 0.6,
    "w_breakout": 0.8,
    "w_noise": 0.7
  },
  "topn": [
    {
      "symbol": "SOLUSDT",
      "trend": 0.0012,
      "vol": 0.00045,
      "breakout": 0.60,
      "noise": 1.80,
      "score": 0.42
    }
  ]
}
```

## Tool-bot consumption
- **Pull** mode: tool-bot reads this file; you can map `topn[i].symbol` into your execution engine.
- **Push** mode: intel-bot POSTs the same JSON to `PUBLISH_WEBHOOK_URL`.
