# market-intel-bot

A closed-loop **market intelligence bot** that continuously fetches market data for a large universe (e.g., Top 80 USDT-margined futures symbols), computes lightweight features on a primary timeframe (15m), ranks symbols, and publishes **TopN** candidates for your execution “tool-bot” to consume.

## What you get
- Auto-universe (TopN by quoteVolume) or manual `SYMBOLS=` list
- 15m baseline features: trend, volatility, breakout, noise
- Deterministic scoring & ranking
- Cooldown so you don’t spam the same symbol
- Persistent state in `store/`
- Optional OpenAI summarizer with **budget + cooldown** guardrails
- Two integration modes:
  1) **File-based**: tool-bot reads `store/topn/latest.json`
  2) **Webhook-based**: intel-bot posts TopN to your tool-bot endpoint

## Quick start (Windows PowerShell)
```powershell
cd market-intel-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env
python -m pipeline.intel_runner
```

## Output
- `store/topn/latest.json` (always overwritten)
- `store/snapshots/YYYYMMDD/HHMMSS_topn.json` (history)

## Tool-bot consumption
### Option A: file polling (simplest on same machine)
Tool-bot reads `store/topn/latest.json` every `X` seconds. The file format is stable.

### Option B: webhook push
Set `PUBLISH_WEBHOOK_URL` and `PUBLISH_WEBHOOK_BEARER`. The intel-bot will POST the same JSON payload to the URL.

## Notes
- This repo is **intel-only**. No trading, no keys required.
- If you enable OpenAI summaries, the bot enforces a daily budget.

## Expose TopN to your tool-bot (HTTP)

In one terminal:

```powershell
python -m scripts.serve_topn
```

Then your tool-bot can fetch:

- `GET http://127.0.0.1:8787/topn`


## Expose TopN to the trading tool-bot

The intel-bot writes:
- `store/topn/latest.json`
- `store/topn/latest.json`

Run a minimal local API server:

```powershell
.\.venv\Scripts\Activate.ps1
.\scripts\run_api.ps1
```

Then the tool-bot can read:
- `http://127.0.0.1:8787/topn`

If you deploy intel-bot on a VPS, bind `INTEL_API_HOST=0.0.0.0` and open the port.


## Regime Gate (4h Trend Filter)

This release adds a Higher-Timeframe (HTF) **Regime Gate** used for trend-only operation.

- HTF defaults to **4h**.
- When `ENABLE_REGIME_GATE=true` and `TREND_ONLY=true`, the bot will publish only symbols where the HTF gate explicitly allows **LONG** or **SHORT**.
- The latest HTF snapshot is written to `store/regime/latest.json` (configurable via `REGIME_OUTPUT_FILE`).

Key env vars:
- `ENABLE_REGIME_GATE` (default: true)
- `TREND_ONLY` (default: true)
- `REGIME_TIMEFRAME` (default: 4h)
- `REGIME_LOOKBACK_BARS` (default: 200)
- `REGIME_EMA_FAST` / `REGIME_EMA_SLOW` (default: 20 / 60)
- `REGIME_SWING_BARS` (default: 3)
- `REGIME_CACHE_SECONDS` (default: 900)
- `REGIME_OUTPUT_FILE` (default: store/regime/latest.json)
