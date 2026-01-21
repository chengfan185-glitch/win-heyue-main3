from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


def _getenv(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _getbool(name: str, default: str = "false") -> bool:
    return _getenv(name, default).strip().lower() in ("1", "true", "yes", "y")


def _getint(name: str, default: str) -> int:
    try:
        return int(_getenv(name, default))
    except Exception:
        return int(default)


def _getfloat(name: str, default: str) -> float:
    try:
        return float(_getenv(name, default))
    except Exception:
        return float(default)


def _parse_csv(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@dataclass
class Settings:
    env: str
    log_level: str
    timezone: str

    symbols: List[str]
    universe_size: int
    universe_source: str
    topn_refresh_minutes: int

    timeframe: str
    lookback_bars: int

    # Regime Gate (Higher Timeframe Trend Filter)
    enable_regime_gate: bool
    regime_timeframe: str
    regime_lookback_bars: int
    regime_ema_fast: int
    regime_ema_slow: int
    regime_swing_bars: int
    regime_cache_seconds: int
    trend_only: bool
    regime_output_file: str

    cycle_seconds: int
    batch_max_workers: int
    batch_shuffle_symbols: bool

    w_trend: float
    w_vol: float
    w_breakout: float
    w_noise: float

    topn_output: int
    min_score_to_publish: float
    cooldown_seconds: int

    store_dir: str
    state_file: str
    snapshot_dir: str
    topn_file: str

    publish_webhook_url: str
    publish_webhook_bearer: str

    enable_openai: bool
    openai_api_key: str
    openai_model: str
    openai_max_tokens: int
    openai_daily_budget_usd: float
    openai_cooldown_seconds: int

    dry_run: bool


def load_settings() -> Settings:
    return Settings(
        env=_getenv("ENV", "prod"),
        log_level=_getenv("LOG_LEVEL", "INFO"),
        timezone=_getenv("TIMEZONE", "Asia/Shanghai"),

        symbols=_parse_csv(_getenv("SYMBOLS", "")),
        universe_size=_getint("UNIVERSE_SIZE", "80"),
        universe_source=_getenv("UNIVERSE_SOURCE", "binance_um_usdt"),
        topn_refresh_minutes=_getint("TOPN_REFRESH_MINUTES", "60"),

        timeframe=_getenv("TIMEFRAME", "15m"),
        lookback_bars=_getint("LOOKBACK_BARS", "200"),

        enable_regime_gate=_getbool("ENABLE_REGIME_GATE", "true"),
        regime_timeframe=_getenv("REGIME_TIMEFRAME", "4h"),
        regime_lookback_bars=_getint("REGIME_LOOKBACK_BARS", "200"),
        regime_ema_fast=_getint("REGIME_EMA_FAST", "20"),
        regime_ema_slow=_getint("REGIME_EMA_SLOW", "60"),
        regime_swing_bars=_getint("REGIME_SWING_BARS", "3"),
        regime_cache_seconds=_getint("REGIME_CACHE_SECONDS", "900"),
        trend_only=_getbool("TREND_ONLY", "true"),
        regime_output_file=_getenv("REGIME_OUTPUT_FILE", "store/regime/latest.json"),

        cycle_seconds=_getint("CYCLE_SECONDS", "60"),
        batch_max_workers=_getint("BATCH_MAX_WORKERS", "12"),
        batch_shuffle_symbols=_getbool("BATCH_SHUFFLE_SYMBOLS", "true"),

        w_trend=_getfloat("W_TREND", "1.0"),
        w_vol=_getfloat("W_VOL", "0.6"),
        w_breakout=_getfloat("W_BREAKOUT", "0.8"),
        w_noise=_getfloat("W_NOISE", "0.7"),

        topn_output=_getint("TOPN_OUTPUT", "10"),
        min_score_to_publish=_getfloat("MIN_SCORE_TO_PUBLISH", "0.15"),
        cooldown_seconds=_getint("COOLDOWN_SECONDS", "300"),

        store_dir=_getenv("STORE_DIR", "store"),
        state_file=_getenv("STATE_FILE", "store/state.json"),
        snapshot_dir=_getenv("SNAPSHOT_DIR", "store/snapshots"),
        topn_file=_getenv("TOPN_FILE", "store/topn/latest.json"),

        publish_webhook_url=_getenv("PUBLISH_WEBHOOK_URL", ""),
        publish_webhook_bearer=_getenv("PUBLISH_WEBHOOK_BEARER", ""),

        enable_openai=_getbool("ENABLE_OPENAI", "false"),
        openai_api_key=_getenv("OPENAI_API_KEY", ""),
        openai_model=_getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_max_tokens=_getint("OPENAI_MAX_TOKENS", "400"),
        openai_daily_budget_usd=_getfloat("OPENAI_DAILY_BUDGET_USD", "2.0"),
        openai_cooldown_seconds=_getint("OPENAI_COOLDOWN_SECONDS", "600"),

        dry_run=_getbool("DRY_RUN", "true"),
    )
