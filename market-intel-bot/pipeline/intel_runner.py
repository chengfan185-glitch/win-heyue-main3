from __future__ import annotations

import os
import random
import time
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv
from rich.console import Console

from feeds.binance import BinancePublic
from features.baseline import compute_features
from features.regime_gate import classify_regime_4h
from pipeline.ranker import rank
from src.settings import load_settings
from src.store import CooldownState, load_state, save_state, write_json
from ops.publisher import publish_file, publish_webhook


console = Console()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _should_publish_symbol(st: CooldownState, symbol: str, cooldown_seconds: int) -> bool:
    last = float(st.last_publish_ts.get(symbol, 0.0) or 0.0)
    return (time.time() - last) >= cooldown_seconds


def main() -> None:
    load_dotenv()
    cfg = load_settings()

    os.makedirs(cfg.store_dir, exist_ok=True)
    os.makedirs(os.path.dirname(cfg.topn_file), exist_ok=True)

    state = load_state(cfg.state_file)

    feed = BinancePublic(base_url="https://fapi.binance.com")

    universe: List[str] = []
    universe_last_refresh = 0.0


    # HTF regime cache (symbol -> {ts, payload})
    regime_cache: Dict[str, Any] = {}

    console.print(f"[bold]market-intel-bot[/bold] start | timeframe={cfg.timeframe} universe_size={cfg.universe_size} topn={cfg.topn_output}")

    while True:
        # Refresh universe
        if cfg.symbols:
            universe = list(cfg.symbols)
        else:
            if (time.time() - universe_last_refresh) > (cfg.topn_refresh_minutes * 60):
                console.print(f"[{_now_iso()}] refreshing universe...")
                universe = feed.top_symbols_by_quote_volume(cfg.universe_size)
                universe_last_refresh = time.time()

        if cfg.batch_shuffle_symbols:
            random.shuffle(universe)

        # Fetch & feature
        feats = []
        for i, sym in enumerate(universe[: cfg.universe_size]):
            try:
                ks = feed.klines(sym, cfg.timeframe, cfg.lookback_bars)
                feats.append(compute_features(sym, ks))
            except Exception as e:
                console.print(f"[{_now_iso()}] [red]fetch failed[/red] {sym}: {e}")
                continue

            # Higher-timeframe (4h) regime gate
            if cfg.enable_regime_gate:
                now_ts = time.time()
                cached = regime_cache.get(sym) or {}
                cached_ts = float(cached.get("ts") or 0.0)
                if (now_ts - cached_ts) < float(cfg.regime_cache_seconds):
                    rg = cached.get("rg") or {}
                else:
                    try:
                        ks4h = feed.klines(sym, cfg.regime_timeframe, cfg.regime_lookback_bars)
                        rgo = classify_regime_4h(
                            ks4h,
                            ema_fast_period=int(cfg.regime_ema_fast),
                            ema_slow_period=int(cfg.regime_ema_slow),
                            swing_lookback_bars=int(cfg.regime_swing_bars),
                        )
                        rg = {
                            "regime": rgo.regime,
                            "allowed_actions": rgo.allowed_actions,
                            "ema_fast": rgo.ema_fast,
                            "ema_slow": rgo.ema_slow,
                            "close": rgo.close,
                            "debug": rgo.debug,
                        }
                    except Exception as e:
                        rg = {
                            "regime": "RANGE",
                            "allowed_actions": [],
                            "ema_fast": 0.0,
                            "ema_slow": 0.0,
                            "close": 0.0,
                            "debug": {"reason": "fetch_failed", "err": repr(e)},
                        }
                    regime_cache[sym] = {"ts": now_ts, "rg": rg}

                # Attach regime to cache only; it will be merged into rows after ranking
            
        weights = {
            "w_trend": cfg.w_trend,
            "w_vol": cfg.w_vol,
            "w_breakout": cfg.w_breakout,
            "w_noise": cfg.w_noise,
        }

        top_rows = rank(feats, weights, cfg.topn_output)

        # Merge HTF regime gate info into ranked rows
        if cfg.enable_regime_gate:
            for r in top_rows:
                sym = str(r.get("symbol"))
                cached = regime_cache.get(sym) or {}
                rg = cached.get("rg") or {}
                r["htf_regime"] = rg.get("regime", "RANGE")
                r["allowed_actions"] = rg.get("allowed_actions", [])
                r["htf_ema_fast"] = rg.get("ema_fast", 0.0)
                r["htf_ema_slow"] = rg.get("ema_slow", 0.0)
                r["htf_close"] = rg.get("close", 0.0)

        # Apply cooldown + min score
        filtered = []
        for r in top_rows:
            if float(r.get("score") or 0.0) < cfg.min_score_to_publish:
                continue

            if cfg.trend_only and cfg.enable_regime_gate:
                # Trend-only mode: publish only symbols with explicit HTF permission (LONG/SHORT)
                if not (r.get("allowed_actions") or []):
                    continue
            sym = str(r.get("symbol"))
            if not _should_publish_symbol(state, sym, cfg.cooldown_seconds):
                continue
            filtered.append(r)

        payload: Dict[str, Any] = {
            "ts": time.time(),
            "time": _now_iso(),
            "timeframe": cfg.timeframe,
            "universe_size": len(universe),
            "topn": filtered,
            "weights": weights,
        }

        # Persist
        publish_file(cfg.topn_file, payload)

        # Persist HTF regime snapshot (for executor / debugging)
        if cfg.enable_regime_gate and cfg.regime_output_file:
            try:
                os.makedirs(os.path.dirname(cfg.regime_output_file), exist_ok=True)
                regime_payload = {
                    "ts": time.time(),
                    "time": _now_iso(),
                    "timeframe": cfg.regime_timeframe,
                    "universe_size": len(universe),
                    "regimes": [
                        {
                            "symbol": str(s),
                            **((regime_cache.get(str(s)) or {}).get("rg") or {}),
                        }
                        for s in universe[: cfg.universe_size]
                    ],
                }
                write_json(cfg.regime_output_file, regime_payload)
            except Exception as e:
                console.print(f"[{_now_iso()}] [yellow]regime write failed[/yellow]: {e}")

        # Snapshot
        day = datetime.now().strftime("%Y%m%d")
        snap_dir = os.path.join(cfg.snapshot_dir, day)
        os.makedirs(snap_dir, exist_ok=True)
        snap_file = os.path.join(snap_dir, datetime.now().strftime("%H%M%S") + "_topn.json")
        write_json(snap_file, payload)

        # Webhook
        try:
            if cfg.publish_webhook_url:
                publish_webhook(cfg.publish_webhook_url, cfg.publish_webhook_bearer, payload)
        except Exception as e:
            console.print(f"[{_now_iso()}] [yellow]webhook failed[/yellow]: {e}")

        # Update cooldown state
        for r in filtered:
            state.last_publish_ts[str(r.get("symbol"))] = time.time()
        save_state(cfg.state_file, state)

        console.print(f"[{_now_iso()}] published {len(filtered)} candidates -> {cfg.topn_file}")

        time.sleep(max(1, int(cfg.cycle_seconds)))


if __name__ == "__main__":
    main()
