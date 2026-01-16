# pipeline/futures_runner_v2.py
"""
Production-Grade Binance Futures Trading Runner

Integrates:
- Trade ledger (audit trail)
- State reconciliation (recovery)
- Order executor (lifecycle management)
- Metrics & alerts (observability)
- Continuous risk monitoring
- Symbol batch processing
- Strategy decision logic
- Full paper/testnet/live support
"""

from __future__ import annotations

import os
import sys
import time
import json
import random
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def ensure_alert_manager_compat(alerts) -> None:
    """
    兼容补丁：如果 AlertManager 实例上缺少新版 runner 需要的高层方法，
    在这里按旧接口封装一层挂上去，避免 AttributeError。
    """
    # 系统启动
    if not hasattr(alerts, "alert_system_startup"):
        def _alert_system_startup(trading_mode: str, run_id: str) -> None:
            text = (
                "[INFO] 交易系统已启动\n\n"
                f"运行模式：{trading_mode}\n"
                f"运行ID： {run_id}"
            )
            # 老版本至少有 info()
            if hasattr(alerts, "info"):
                alerts.info(text)
        alerts.alert_system_startup = _alert_system_startup  # type: ignore[attr-defined]

    # 当日额度用完
    if not hasattr(alerts, "alert_quota_exhausted"):
        def _alert_quota_exhausted(symbol: str, remaining: int) -> None:
            text = (
                "[WARNING] Quota Exhausted\n\n"
                f"Daily quota exhausted for {symbol}\n"
                f"Remaining quota (report)：{remaining}"
            )
            if hasattr(alerts, "warning"):
                alerts.warning(text)
        alerts.alert_quota_exhausted = _alert_quota_exhausted  # type: ignore[attr-defined]

    # 下单成功
    if not hasattr(alerts, "alert_order_placed"):
        def _alert_order_placed(
            symbol: str,
            side: str,
            size_usd: float,
            entry_price: float,
            trading_mode: str,
        ) -> None:
            text = (
                "[ORDER] 新订单已提交\n\n"
                f"模式：{trading_mode}\n"
                f"品种：{symbol}\n"
                f"方向：{side}\n"
                f"名义金额：{size_usd:.2f} USDT\n"
                f"入场价：{entry_price}"
            )
            if hasattr(alerts, "info"):
                alerts.info(text)
        alerts.alert_order_placed = _alert_order_placed  # type: ignore[attr-defined]

    # 致命错误
    if not hasattr(alerts, "alert_fatal_error"):
        def _alert_fatal_error(message: str) -> None:
            text = f"[FATAL] {message}"
            if hasattr(alerts, "error"):
                alerts.error(text)
        alerts.alert_fatal_error = _alert_fatal_error  # type: ignore[attr-defined]



def fetch_okx_klines_and_features(symbol: str, interval: str) -> dict:
    """
    Fetch klines from OKX and compute features
    OKX bar examples:
      1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, ...
    """
    inst = symbol.replace("USDT", "-USDT")
    url = "https://www.okx.com/api/v5/market/candles"

    # 简单映射：内部用 15m / 45m / 1h / 3h
    bar_map = {
        "15m": "15m",
        "45m": "45m",   # OKX 支持 45m
        "1h": "1H",
        "3h": "3H",
    }
    bar = bar_map.get(interval, "15m")

    params = {
        "instId": inst,
        "bar": bar,
        "limit": "50",
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if data.get("code") != "0":
            return {}

        candles = data.get("data", [])
        if len(candles) < 2:
            return {}

        # OKX candle format:
        # [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        prev = candles[-2]
        curr = candles[-1]

        open_p = float(curr[1])
        high = float(curr[2])
        low = float(curr[3])
        close = float(curr[4])

        prev_close = float(prev[4])

        price_change = (close - prev_close) / max(prev_close, 1e-9)
        volatility = (high - low) / max(open_p, 1e-9)

        return {
            "price_change": price_change,
            "volatility": volatility,
            "close": close,

            # 为策略 / ML 提供“潜在 edge 线索”
            "raw_edge_hint": price_change,   # 或你后面算的 signal
        }
    except Exception as e:
        print(f"[OKX_KLINE] Error fetching {symbol} {interval}: {e}")
        return {}


# Path bootstrap
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure .env is loaded
from core.config.env_loader import load_env
load_env(str(ROOT / ".env"), override=False)

# Core infrastructure
from core.ledger.trade_ledger import TradeLedger, Order, Position, Trade, BOT_PROFILE_NAME
from core.ledger.reconciliation import StateReconciliation, ReconciliationMode
from core.execution.order_executor import OrderExecutor
from core.observability.metrics import MetricsCollector
from core.observability.alerts import AlertManager, AlertLevel
from core.utils.time import now_shanghai, format_dt_shanghai, shanghai_local_date
from risk.edge_gate import edge_cost_gate
from risk.edge_gate_v2 import EdgeGateV2, create_default_edge_gate_v2
from risk.edge_stats import EdgeStats, create_default_edge_stats
from risk.edge_gate_diagnostics import EdgeGateDiagnostics, create_default_diagnostics
# Futures adapters
from execution.adapters.binance_um_futures import BinanceUMFuturesAdapter
from execution.adapters.binance_cm_futures import BinanceCMFuturesAdapter
from market.adapters.binance_futures_kline import (
    BinanceFuturesKlineFetcher,
    fetch_futures_price,
)
from risk.implementations.futures_risk import FuturesRiskManager

# ============================================
# Configuration
# ============================================

# Trading mode
TRADING_MODE: Literal["paper", "testnet", "live"] = (
    os.getenv("TRADING_MODE", "paper").lower()
)
if TRADING_MODE not in ("paper", "testnet", "live"):
    TRADING_MODE = "paper"

# Market type
FUTURES_MARKET_TYPE: Literal["UM", "CM"] = (
    os.getenv("FUTURES_MARKET_TYPE", "UM").upper()
)
if FUTURES_MARKET_TYPE not in ("UM", "CM"):
    FUTURES_MARKET_TYPE = "UM"


def _parse_symbols(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return ["BTCUSDT"] if FUTURES_MARKET_TYPE == "UM" else ["BTCUSD_PERP"]
    if raw.startswith("["):
        try:
            arr = json.loads(raw)
            return [str(x).strip().upper() for x in arr if str(x).strip()]
        except Exception:
            pass
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


SYMBOLS = _parse_symbols(os.getenv("SYMBOLS", ""))

# EdgeGate v2 constants for insufficient samples fallback
EDGEGATE_V2_INSUFFICIENT_SAMPLES_PERCENTILE = 0.60  # Force minimum percentile to avoid BLOCK
EDGEGATE_V2_INSUFFICIENT_SAMPLES_MIN_EDGE = 0.0001  # Minimum positive edge for PROBE

# Interval
INTERVAL = os.getenv("INTERVAL", "15m")
SUPPORTED_INTERVALS = ["15m", "45m", "1h", "3h"]
if INTERVAL not in SUPPORTED_INTERVALS:
    print(f"[WARN] Unsupported interval {INTERVAL}, using 15m")
    INTERVAL = "15m"

# Leverage and margin
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "2"))
MARGIN_TYPE: Literal["ISOLATED", "CROSSED"] = (
    os.getenv("MARGIN_TYPE", "ISOLATED").upper()
)

# Position sizing
AMOUNT_USDT = float(os.getenv("AMOUNT_USDT", "20"))

# Real trading
ENABLE_REAL_TRADING = os.getenv("ENABLE_REAL_TRADING", "false").lower() == "true"

# Daily quota
DAILY_ORDER_QUOTA = int(os.getenv("DAILY_ORDER_QUOTA", "3"))

# Kill switch
KILL_SWITCH = os.getenv("KILL_SWITCH", "false").lower() == "true"

# Batch settings
BATCH_FETCH_CONCURRENT = (
    os.getenv("BATCH_FETCH_CONCURRENT", "true").lower() == "true"
)
BATCH_MAX_WORKERS = int(os.getenv("BATCH_MAX_WORKERS", "10"))
BATCH_SHUFFLE_SYMBOLS = os.getenv("BATCH_SHUFFLE_SYMBOLS", "true").lower() == "true"
BATCH_SLEEP_CHOICES = os.getenv("BATCH_SLEEP_CHOICES", "5,8,10,12,15").strip()
# >>> 新增：启动冷静期（分钟） <<<
STARTUP_WARMUP_MINUTES = int(os.getenv("STARTUP_WARMUP_MINUTES", "0"))


def _parse_sleep_choices(raw: str) -> List[int]:
    raw = (raw or "").strip()
    if not raw:
        return [5, 8, 10, 12, 15]
    items: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            v = int(float(part))
            if v > 0:
                items.append(v)
        except Exception:
            continue
    return items if items else [5, 8, 10, 12, 15]


_SLEEP_CHOICES = _parse_sleep_choices(BATCH_SLEEP_CHOICES)


def next_round_sleep_sec() -> int:
    return int(random.choice(_SLEEP_CHOICES))


# ============================================
# Quota Management
# ============================================

QUOTA_FILE = Path("logs/daily_quota.json")


def _quota_today_key() -> str:
    """Get today's date key in Shanghai timezone for quota tracking"""
    return shanghai_local_date()


def get_remaining_quota() -> int:
    """Get remaining daily quota"""
    if not QUOTA_FILE.exists():
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {"date": _quota_today_key(), "remaining": DAILY_ORDER_QUOTA}
        QUOTA_FILE.write_text(json.dumps(state))
        return DAILY_ORDER_QUOTA

    try:
        state = json.loads(QUOTA_FILE.read_text())
        if state.get("date") != _quota_today_key():
            state = {"date": _quota_today_key(), "remaining": DAILY_ORDER_QUOTA}
            QUOTA_FILE.write_text(json.dumps(state))
        return max(0, int(state.get("remaining", 0)))
    except Exception:
        return 0


def dec_quota() -> int:
    """Decrement quota after successful order"""
    if not QUOTA_FILE.exists():
        return 0

    try:
        state = json.loads(QUOTA_FILE.read_text())
        remaining = max(0, int(state.get("remaining", 0)) - 1)
        state["remaining"] = remaining
        state["date"] = _quota_today_key()
        QUOTA_FILE.write_text(json.dumps(state))
        return remaining
    except Exception:
        return 0


# ============================================
# Helper Functions
# ============================================

def _fmt_ts(now_utc: datetime) -> str:
    """Format timestamp as Shanghai time with +08:00 offset"""
    try:
        return format_dt_shanghai(now_utc)
    except Exception:
        return now_utc.isoformat()


def _tpsl_dev_ok(entry: float, level: Optional[float], max_dev: float = 0.20) -> bool:
    """
    Sanity-check TP/SL absolute levels vs entry.
    max_dev=0.20 means allow within +/-20% of entry.
    """
    if level is None:
        return True
    if entry <= 0:
        return False
    try:
        return abs(level / entry - 1.0) <= max_dev
    except Exception:
        return False


# ============================================
# Features & Strategy
# ============================================

def fetch_futures_klines_and_features(symbol: str) -> Dict[str, Any]:
    """Fetch Binance futures klines and compute features"""
    if not symbol or symbol == "symbol":
        raise ValueError(f"[KLINE] Invalid symbol: {symbol}")

    fetcher = BinanceFuturesKlineFetcher(symbol, FUTURES_MARKET_TYPE)

    try:
        klines = fetcher.fetch_klines(INTERVAL, 50)

        if not klines or len(klines) < 2:
            return {}

        prev = klines[-2]
        curr = klines[-1]

        price_change = (curr["close"] - prev["close"]) / max(prev["close"], 1e-9)
        volume_change = (curr["volume"] - prev["volume"]) / max(prev["volume"], 1e-9)
        volatility = (curr["high"] - curr["low"]) / max(curr["open"], 1e-9)

        return {
            "price_change": float(price_change),
            "volume_change": float(volume_change),
            "volatility": float(volatility),
            "close": float(curr["close"]),
            "volume": float(curr["volume"]),
        }

    except Exception as e:
        print(f"[KLINE] Error fetching features for {symbol}: {e}")
        return {}


def decide_action(features: Dict[str, Any]) -> Tuple[str, float]:
    """
    Simple rule-based strategy
    Returns: (action, confidence)
    """
    if not features:
        return "HOLD", 0.0

    price_change = features.get("price_change", 0.0)
    volatility = features.get("volatility", 0.0)

    MIN_PC = float(os.getenv("RULE_PC_MIN", "0.001"))
    MAX_VOL = float(os.getenv("RULE_VOL_MAX", "0.01"))

    if abs(price_change) < MIN_PC:
        return "HOLD", 0.0

    if volatility > MAX_VOL:
        return "HOLD", 0.0

    if price_change > 0:
        confidence = min(abs(price_change) / MIN_PC * 0.5, 0.8)
        return "LONG", confidence
    else:
        confidence = min(abs(price_change) / MIN_PC * 0.5, 0.8)
        return "SHORT", confidence


def _prefetch_symbol_pack(symbol: str) -> Dict[str, Any]:
    """Prefetch price and features for a symbol"""
    pack: Dict[str, Any] = {"symbol": symbol, "ok": False}

    try:
        pack["price"] = fetch_futures_price(symbol, FUTURES_MARKET_TYPE)
    except Exception as e:
        pack["error_price"] = str(e)
        return pack

    try:
        # 预取特征用 Binance K 线，跑不通时再在主逻辑里走 OKX
        pack["features"] = fetch_futures_klines_and_features(symbol)
    except Exception as e:
        pack["error_features"] = str(e)

    pack["ok"] = True
    return pack


# ============================================
# Trading Logic
# ============================================

def run_once_for_symbol(
    symbol: str,
    ledger: TradeLedger,
    adapter: Any,
    risk_manager: FuturesRiskManager,
    alerts: AlertManager,
    metrics: MetricsCollector,
    edge_gate_v2: EdgeGateV2,
    edge_stats: EdgeStats,
    edge_diagnostics: EdgeGateDiagnostics,
    *,
    now_ts: Optional[datetime] = None,
    prefetch: Optional[Dict[str, Any]] = None,
    batch_id: Optional[int] = None,
    can_open_new: bool = True, in_warmup: bool = False,
):
    """Execute one trading cycle for a symbol"""
    now_ts = now_ts or datetime.now(timezone.utc)
    print(f"\n🚀 run_once_for_symbol | {symbol} | batch={batch_id}")

    # --------------------------------------------------
    # 1. Real-time price
    # --------------------------------------------------
    try:
        if prefetch and prefetch.get("price") is not None:
            real_price = float(prefetch["price"])
        else:
            real_price = fetch_futures_price(symbol, FUTURES_MARKET_TYPE)
        print(f"[PRICE] {symbol} = {real_price}")
        metrics.record_api_call(success=True)
        global entry_price
        entry_price = real_price  # 保险变量，兼容遗留代码路径
    except Exception as e:
        print(f"[PRICE ERROR] {symbol}: {e}")
        metrics.record_api_call(success=False)
        metrics.record_network_error("price_fetch_failed")
        return

    # --------------------------------------------------
    # 2. Existing position? (先处理平仓)
    # --------------------------------------------------
    existing_pos = ledger.get_open_position(symbol)

    if existing_pos:
        print(
            f"[POSITION] {symbol} has open position: "
            f"{existing_pos.side} qty={existing_pos.quantity}"
        )

        # 更新账本里的 current_price
        ledger.update_position(symbol, real_price)

        # 同步给风控
        risk_manager.update_position(
            symbol=symbol,
            side=existing_pos.side,
            quantity=existing_pos.quantity,
            entry_price=existing_pos.entry_price,
            current_price=real_price,
            leverage=existing_pos.leverage,
            margin_type=existing_pos.margin_type,
            stop_loss_price=existing_pos.stop_loss_price,
            take_profit_price=existing_pos.take_profit_price,
        )

        # 判断是否需要平仓
        should_close, reason, close_params = risk_manager.check_stop_conditions(
            symbol, real_price
        )

        if should_close:
            print(f"[EXIT SIGNAL] {symbol} reason={reason}")

            # ===== 纸盘平仓 =====
            if TRADING_MODE == "paper":
                print(
                    f"[PAPER CLOSE-REASON] {symbol} "
                    f"reason={reason} entry={existing_pos.entry_price} exit={real_price}"
                )

                if existing_pos.side == "LONG":
                    realized_pnl = (
                        real_price - existing_pos.entry_price
                    ) * existing_pos.quantity
                else:
                    realized_pnl = (
                        existing_pos.entry_price - real_price
                    ) * existing_pos.quantity

                closed_pos = ledger.close_position(
                    symbol,
                    real_price,
                    realized_pnl=realized_pnl,
                )

                if closed_pos:
                    trade = Trade(
                        trade_id="",
                        symbol=symbol,
                        side=closed_pos.side,
                        entry_quantity=closed_pos.quantity,
                        entry_price=closed_pos.entry_price,
                        entry_timestamp=closed_pos.opened_at,
                        entry_order_id=closed_pos.open_order_id,
                        exit_quantity=closed_pos.quantity,
                        exit_price=real_price,
                        exit_timestamp=time.time(),
                        exit_reason=reason,
                        gross_pnl=realized_pnl,
                        commission_total=0.0,
                        net_pnl=realized_pnl,
                        leverage=closed_pos.leverage,
                        run_id=ledger.run_id,
                        bot_profile=BOT_PROFILE_NAME,
                    )
                    ledger.record_trade(trade)
                    metrics.record_position_closed(realized_pnl)

                    alerts.send_alert(
                        AlertLevel.INFO,
                        f"[PAPER CLOSE] {symbol}",
                        (
                            f"Reason: {reason}\n"
                            f"Entry: {existing_pos.entry_price}\n"
                            f"Exit: {real_price}\n"
                            f"PnL: {realized_pnl:.2f}"
                        ),
                    )

                risk_manager.close_position(symbol, real_price, realized_pnl, now_ts)

            # ===== 真盘 / 测试网平仓 =====
            elif ENABLE_REAL_TRADING:
                try:
                    result = adapter.close_position(symbol)
                    if result:
                        if existing_pos.side == "LONG":
                            realized_pnl = (
                                real_price - existing_pos.entry_price
                            ) * existing_pos.quantity
                        else:
                            realized_pnl = (
                                existing_pos.entry_price - real_price
                            ) * existing_pos.quantity

                        closed_pos = ledger.close_position(
                            symbol,
                            real_price,
                            realized_pnl=realized_pnl,
                        )

                        if closed_pos:
                            trade = Trade(
                                trade_id="",
                                symbol=symbol,
                                side=closed_pos.side,
                                entry_quantity=closed_pos.quantity,
                                entry_price=closed_pos.entry_price,
                                entry_timestamp=closed_pos.opened_at,
                                entry_order_id=closed_pos.open_order_id,
                                exit_quantity=closed_pos.quantity,
                                exit_price=real_price,
                                exit_timestamp=time.time(),
                                exit_reason=reason,
                                gross_pnl=realized_pnl,
                                commission_total=0.0,
                                net_pnl=realized_pnl,
                                leverage=closed_pos.leverage,
                                run_id=ledger.run_id,
                            )
                            ledger.record_trade(trade)
                            metrics.record_position_closed(realized_pnl)

                        risk_manager.close_position(
                            symbol, real_price, realized_pnl, now_ts
                        )

                        alerts.send_alert(
                            AlertLevel.INFO,
                            f"[CLOSE] {symbol}",
                            (
                                f"Reason: {reason}\n"
                                f"Entry: {existing_pos.entry_price}\n"
                                f"Exit: {real_price}\n"
                                f"PnL: {realized_pnl:.2f}"
                            ),
                        )

                        print(f"✅ Position closed: {symbol}")

                        if reason == "stop_loss":
                            metrics.record_stop_loss()
                        elif reason == "take_profit":
                            metrics.record_take_profit()
                        elif reason == "trailing_stop":
                            metrics.record_trailing_stop()

                except Exception as e:
                    print(f"[CLOSE ERROR] {symbol}: {e}")
                    alerts.alert_order_failed(symbol, f"Close error: {e}")
                    metrics.record_api_call(success=False)

        print("✅ run_once_for_symbol finished (position exists)")
        return

    # ---------------------------------------------
    # 3. No existing position - check if we can open new
    # ---------------------------------------------
    if not can_open_new:
        # 这里的 can_open_new 是主循环总闸：
        # can_open_new = (recon_mode == NORMAL) and (not in_warmup)
        # 所以被挡住可能是 warmup，也可能是对账进入 CLOSE_ONLY / EMERGENCY_STOP
        try:
            warmup_hint = ""
            if "in_warmup" in locals() and locals()["in_warmup"]:
                warmup_hint = "（冷静期 WARMUP 中）"
            print(f"[BLOCKED] 禁止开新仓 {warmup_hint}：等待放行（对账模式或冷静期未结束）")
        except Exception:
            print("[BLOCKED] 禁止开新仓：等待放行（对账模式或冷静期未结束）")
        return

    # --------------------------------------------------
    # 4. Fetch features (优先用预取，其次 OKX)
    # --------------------------------------------------
    try:
        if prefetch and prefetch.get("features"):
            features = prefetch["features"]
        else:
            features = fetch_okx_klines_and_features(symbol, INTERVAL)
        metrics.record_api_call(success=True)
    except Exception as e:
        print(f"[FEATURES ERROR] {symbol}: {e}")
        metrics.record_api_call(success=False)
        return

    # --------------------------------------------------
    # 5. Decide action
    # --------------------------------------------------
    action, confidence = decide_action(features)
    print(f"[DECISION] {symbol} action={action} confidence={confidence:.3f}")

    if action == "HOLD":
        print("✅ run_once_for_symbol finished (HOLD)")
        return

    # --------------------------------------------------
    # 5.5 EdgeGate v2 - PROBE Position Mechanism
    # --------------------------------------------------
    # Calculate net_edge using the old gate for consistency
    predicted_edge_pct = confidence * features.get("price_change", 0.0)
    gate_v1 = edge_cost_gate(predicted_edge_pct)
    net_edge = gate_v1["net_expected_edge"]

    # Calculate edge_percentile from historical data (symbol/direction/timeframe specific)
    edge_percentile = edge_stats.get_edge_percentile(
        net_edge=net_edge,
        symbol=symbol,
        direction=action,  # "LONG" or "SHORT"
        timeframe=INTERVAL,  # e.g., "15m"
    )

    # Handle insufficient samples case
    if edge_percentile is None:
        print(
            f"[EDGEGATE V2 WARN] {symbol} {action} - Insufficient samples for {INTERVAL}, "
            f"forcing PROBE mode (0.10x) for conservative trial"
        )
        # Force conservative PROBE with minimum multiplier when no history
        edge_percentile = EDGEGATE_V2_INSUFFICIENT_SAMPLES_PERCENTILE
        gate_v2_result = edge_gate_v2.evaluate(
            net_edge=max(net_edge, EDGEGATE_V2_INSUFFICIENT_SAMPLES_MIN_EDGE),
            confidence=confidence,
            edge_percentile=edge_percentile,
        )
        # Override to ensure PROBE small
        if gate_v2_result.state != "BLOCK":
            gate_v2_result.position_multiplier = 0.10
            gate_v2_result.state = "PROBE"
            gate_v2_result.reason = f"insufficient_samples_probe_trial (samples < 50)"
    else:
        # Evaluate using EdgeGate v2 with valid percentile
        gate_v2_result = edge_gate_v2.evaluate(
            net_edge=net_edge,
            confidence=confidence,
            edge_percentile=edge_percentile,
            fee_estimate=gate_v1.get("gross_edge_pct", 0) - net_edge if net_edge > 0 else 0,
        )

    # Log decision for diagnostics
    edge_diagnostics.record_decision(
        state=gate_v2_result.state,
        reason=gate_v2_result.reason,
        net_edge=net_edge,
        confidence=confidence,
        edge_percentile=edge_percentile if edge_percentile is not None else 0.0,
        position_multiplier=gate_v2_result.position_multiplier,
        symbol=symbol,
        timestamp=now_ts,
    )

    # Apply EdgeGate v2 decision
    if gate_v2_result.state == "BLOCK":
        print(
            f"[EDGEGATE V2 BLOCK] {symbol} "
            f"state={gate_v2_result.state} "
            f"reason={gate_v2_result.reason} "
            f"net_edge={net_edge:.6f} "
            f"confidence={confidence:.3f} "
            f"percentile={edge_percentile if edge_percentile is not None else 'N/A'}"
        )
        metrics.record_risk_block()
        return

    # Determine position size based on state
    position_multiplier = gate_v2_result.position_multiplier
    adjusted_amount_usdt = AMOUNT_USDT * position_multiplier

    print(
        f"[EDGEGATE V2] {symbol} "
        f"state={gate_v2_result.state} "
        f"multiplier={position_multiplier:.2f} "
        f"size={adjusted_amount_usdt:.2f} USDT "
        f"reason={gate_v2_result.reason}"
    )

    # Record this edge for future percentile calculations
    # CRITICAL: Record BEFORE trade outcome is known (no future function)
    edge_stats.record_edge(
        net_edge=net_edge,
        symbol=symbol,
        direction=action,  # "LONG" or "SHORT"
        timeframe=INTERVAL,
        signal_type=f"ml_{action.lower()}",
        metadata={
            "confidence": confidence,
            "state": gate_v2_result.state,
            "position_multiplier": position_multiplier,
        },
        timestamp=now_ts,
    )

    # --------------------------------------------------
    # 6. Check quota
    # --------------------------------------------------
    remaining_quota = get_remaining_quota()
    if remaining_quota <= 0:
        print(f"[QUOTA BLOCK] {symbol} remaining={remaining_quota}")
        alerts.send_alert(
            AlertLevel.WARNING,
            "Quota Exhausted",
            f"Daily quota exhausted for {symbol}",
        )
        metrics.record_risk_block()
        return

    # --------------------------------------------------
    # 7. Kill switch
    # --------------------------------------------------
    if KILL_SWITCH:
        print(f"[KILL SWITCH] {symbol} blocked")
        return

    # --------------------------------------------------
    # 8. Get account balance
    # --------------------------------------------------
    if TRADING_MODE == "paper":
        account_balance = 10000.0
    else:
        try:
            account = adapter.get_account_balance()
            account_balance = float(account.get("totalWalletBalance", 10000.0))
            metrics.record_api_call(success=True)
        except Exception:
            account_balance = 10000.0
            metrics.record_api_call(success=False)
            
    # 用当前 real_price 作为风控计算 TP/SL 的入场参考价（paper/live 都可用）
    entry_price_local = real_price

    # --------------------------------------------------
    # 9. Risk check (using adjusted position size from EdgeGate v2)
    # --------------------------------------------------
   
    can_open, reason, adjusted_params = risk_manager.check_can_open_position(
        symbol=symbol,
        side=action,
        size_usd=adjusted_amount_usdt,
        account_balance=account_balance,
        leverage=MAX_LEVERAGE,
        
        current_time=now_ts,
    )


    if not can_open:
        print(f"[RISK BLOCK] {symbol} reason={reason}")
        metrics.record_risk_block()
        return

    # --------------------------------------------------
    # 9.5. TP/SL fallback - ensure stop_loss_price and take_profit_price are not None
    # --------------------------------------------------
    try:
        sl = adjusted_params.get("stop_loss_price") if adjusted_params else None
        tp = adjusted_params.get("take_profit_price") if adjusted_params else None
        
        if sl is None or tp is None:
            # Get stop loss and take profit percentages
            sl_pct = adjusted_params.get("stop_loss_pct") if adjusted_params else None
            tp_pct = adjusted_params.get("take_profit_pct") if adjusted_params else None
            
            # Fall back to environment variables if not in adjusted_params
            if sl_pct is None:
                sl_pct = os.getenv("STOP_LOSS_PCT")
            if tp_pct is None:
                tp_pct = os.getenv("TAKE_PROFIT_PCT")
            
            # Convert to float with defaults
            try:
                sl_pct = float(sl_pct) if sl_pct is not None else 0.01
            except Exception:
                sl_pct = 0.01
            try:
                tp_pct = float(tp_pct) if tp_pct is not None else 0.01
            except Exception:
                tp_pct = 0.01
            
            # Calculate based on direction
            if action.upper() == "LONG":
                sl_calc = entry_price_local * (1 - sl_pct)
                tp_calc = entry_price_local * (1 + tp_pct)
            else:  # SHORT
                sl_calc = entry_price_local * (1 + sl_pct)
                tp_calc = entry_price_local * (1 - tp_pct)
            
            # Update adjusted_params with calculated values
            if adjusted_params is None:
                adjusted_params = {}
            if sl is None:
                adjusted_params["stop_loss_price"] = sl_calc
            if tp is None:
                adjusted_params["take_profit_price"] = tp_calc
            
            print(
                f"[TP/SL Fallback] symbol={symbol} side={action} entry_price={entry_price_local} "
                f"sl={adjusted_params.get('stop_loss_price')} tp={adjusted_params.get('take_profit_price')} "
                f"(sl_pct={sl_pct} tp_pct={tp_pct})"
            )
    except Exception as e:
        print(f"[TP/SL Fallback ERROR] {symbol}: {e}")
        import traceback
        traceback.print_exc()

    # --------------------------------------------------
    # 10. Execute order (with EdgeGate v2 position sizing)
    # --------------------------------------------------
    if TRADING_MODE == "paper":
        # ---------- Paper mode ----------
        entry_price_local = real_price
        print(
            f"[PAPER ORDER] {symbol} {action} "
            f"size_usd={adjusted_amount_usdt:.2f} (base={AMOUNT_USDT}, mult={position_multiplier:.2f}) "
            f"price={entry_price_local}"
        )

        quantity = adjusted_amount_usdt / entry_price_local
        stop_loss = adjusted_params.get("stop_loss_price") if adjusted_params else None
        take_profit = adjusted_params.get("take_profit_price") if adjusted_params else None

        print(
            f"[DEBUG adjusted_params RAW] symbol={symbol} side={action} entry={entry_price_local} "
            f"STOP_LOSS_PCT_ENV={os.getenv('STOP_LOSS_PCT')} TAKE_PROFIT_PCT_ENV={os.getenv('TAKE_PROFIT_PCT')} "
            f"adjusted_params={adjusted_params!r}"
        )

        # --- FATAL sanity guard: block insane TP/SL levels (paper debugging safety) ---
        if (stop_loss is not None and not _tpsl_dev_ok(entry_price_local, stop_loss, max_dev=0.20)) or (
            take_profit is not None and not _tpsl_dev_ok(entry_price_local, take_profit, max_dev=0.20)
        ):
            print(
                f"[FATAL TP/SL] symbol={symbol} side={action} entry={entry_price_local} "
                f"sl={stop_loss} tp={take_profit} adjusted_params={adjusted_params!r}"
            )
            metrics.record_risk_block()
            return

        # Optional: print actual dev (helps acceptance test)
        try:
            if stop_loss is not None and entry_price_local:
                sl_dev = abs(stop_loss / entry_price_local - 1.0)
            else:
                sl_dev = None
            if take_profit is not None and entry_price_local:
                tp_dev = abs(take_profit / entry_price_local - 1.0)
            else:
                tp_dev = None
            print(f"[DEBUG TP/SL DEV] sl={stop_loss} dev_sl={sl_dev} tp={take_profit} dev_tp={tp_dev}")
        except Exception as _e:
            pass

        # Apply stricter stop loss for PROBE positions
        if gate_v2_result.state == "PROBE" and stop_loss is not None:
            # Tighten stop loss by 30% for PROBE positions
            if action == "LONG":
                stop_loss_distance = entry_price_local - stop_loss
                stop_loss = entry_price_local - (stop_loss_distance * 0.7)
            else:  # SHORT
                stop_loss_distance = stop_loss - entry_price_local
                stop_loss = entry_price_local + (stop_loss_distance * 0.7)
            print(f"[PROBE RISK] Tightened stop loss to {stop_loss} for PROBE position")

        position = Position(
            position_id="",
            symbol=symbol,
            side=action,
            quantity=quantity,
            entry_price=entry_price_local,
            current_price=entry_price_local,
            leverage=MAX_LEVERAGE,
            margin_type=MARGIN_TYPE,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            run_id=ledger.run_id,
        )
        ledger.open_position(position)

        risk_manager.update_position(
            symbol=symbol,
            side=action,
            quantity=quantity,
            entry_price=entry_price_local,
            current_price=entry_price_local,
            leverage=MAX_LEVERAGE,
            margin_type=MARGIN_TYPE,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
        )

        remaining = dec_quota()

        metrics.record_order_submitted()
        metrics.record_order_filled()
        metrics.record_position_opened()

        alerts.send_alert(
            AlertLevel.INFO,
            f"[PAPER OPEN {gate_v2_result.state}] {symbol}",
            (
                f"Side: {action}\n"
                f"Qty: {quantity:.4f}\n"
                f"Price: {entry_price_local}\n"
                f"Size: {adjusted_amount_usdt:.2f} USDT (base={AMOUNT_USDT}, mult={position_multiplier:.2f}x)\n"
                f"EdgeGate State: {gate_v2_result.state}\n"
                f"Reason: {gate_v2_result.reason}\n"
                f"Quota remaining: {remaining}"
            ),
        )

        print(f"✅ Paper order placed: {symbol} {action}")

    elif ENABLE_REAL_TRADING:
        # ---------- Real / testnet mode ----------
        try:
            try:
                adapter.set_leverage(symbol, MAX_LEVERAGE)
                adapter.set_margin_type(symbol, MARGIN_TYPE)
                metrics.record_api_call(success=True)
            except Exception as e:
                print(f"[SETUP WARN] {symbol}: {e}")

            quantity_est = AMOUNT_USDT / real_price

            stop_loss = adjusted_params.get("stop_loss_price") if adjusted_params else None
            take_profit = adjusted_params.get("take_profit_price") if adjusted_params else None

            side = "BUY" if action == "LONG" else "SELL"

            if FUTURES_MARKET_TYPE == "UM":
                result = adapter.place_market_order(
                    symbol=symbol,
                    side=side,
                    quote_quantity=AMOUNT_USDT,
                    position_side="BOTH",
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
                entry_price_actual = float(getattr(result, "avg_price", real_price))
                qty_actual = float(getattr(result, "qty", quantity_est))
            else:
                contracts = int(quantity_est)
                result = adapter.place_market_order(
                    symbol=symbol,
                    side=side,
                    quantity=contracts,
                    position_side="BOTH",
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
                entry_price_actual = float(getattr(result, "avg_price", real_price))
                qty_actual = float(getattr(result, "qty", contracts))

            position = Position(
                position_id="",
                symbol=symbol,
                side=action,
                quantity=qty_actual,
                entry_price=entry_price_actual,
                current_price=entry_price_actual,
                leverage=MAX_LEVERAGE,
                margin_type=MARGIN_TYPE,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                run_id=ledger.run_id,
            )
            ledger.open_position(position)

            risk_manager.update_position(
                symbol=symbol,
                side=action,
                quantity=qty_actual,
                entry_price=entry_price_actual,
                current_price=entry_price_actual,
                leverage=MAX_LEVERAGE,
                margin_type=MARGIN_TYPE,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
            )

            remaining = dec_quota()

            metrics.record_order_submitted()
            metrics.record_order_filled()
            metrics.record_position_opened()
            metrics.record_api_call(success=True)

            alerts.send_alert(
                AlertLevel.INFO,
                f"[OPEN] {symbol}",
                (
                    f"Side: {action}\n"
                    f"Qty: {qty_actual}\n"
                    f"Price: {entry_price_actual}\n"
                    f"Leverage: {MAX_LEVERAGE}x\n"
                    f"Margin: {MARGIN_TYPE}\n"
                    f"SL: {stop_loss}\n"
                    f"TP: {take_profit}\n"
                    f"Quota remaining: {remaining}"
                ),
            )

            print(f"✅ Order placed: {symbol} {action}")

        except Exception as e:
            print(f"[ORDER ERROR] {symbol}: {e}")
            alerts.alert_order_failed(symbol, str(e))
            metrics.record_order_submitted()
            metrics.record_order_failed()
            metrics.record_api_call(success=False)

    print("✅ run_once_for_symbol finished")


# ============================================
# Main Initialization and Trading Loop
# ============================================

def main():
    """Main trading loop"""
    print(
        """
╔═══════════════════════════════════════════════════════════════╗
║   Production Futures Trading Runner v3.0                      ║
║   With Ledger | Reconciliation | Metrics | Alerts             ║
╚═══════════════════════════════════════════════════════════════╝
"""
    )
    # >>> 记录启动时间 <<<
    startup_time = datetime.now(timezone.utc)
    print("=" * 60)
    print("Binance Futures Trading Runner V2")
    print("=" * 60)
    print(f"TRADING_MODE: {TRADING_MODE}")
    print(f"FUTURES_MARKET_TYPE: {FUTURES_MARKET_TYPE}")
    print(f"SYMBOLS: {SYMBOLS}")
    print(f"INTERVAL: {INTERVAL}")
    print(f"MAX_LEVERAGE: {MAX_LEVERAGE}x")
    print(f"MARGIN_TYPE: {MARGIN_TYPE}")
    print(f"ENABLE_REAL_TRADING: {ENABLE_REAL_TRADING}")
    print(f"DAILY_ORDER_QUOTA: {DAILY_ORDER_QUOTA}")
    print("=" * 60)

    print("\n📊 Initializing systems...")
    ledger = TradeLedger(base_dir="logs/ledger")
    print(f"✅ Ledger initialized (run_id: {ledger.run_id})")

    metrics = MetricsCollector(output_dir="logs/metrics")
    print("✅ Metrics collector initialized")

    alerts = AlertManager()
    
    print("✅ Alert manager initialized")
    # === 兼容层：确保实例上一定有 send_alert 方法 ===
    try:
        from types import MethodType
    except ImportError:
        MethodType = None  # 理论上不会发生

    if not hasattr(alerts, "send_alert") and MethodType is not None:
        def _send_alert(self, level, title, message, extra=None):
            """
            兼容旧接口：
            - level 可能是 AlertLevel 枚举，也可能是字符串
            - title / message 组合成一条纯文本
            """
            level_name = getattr(level, "name", str(level)).upper()
            prefix = f"[{level_name}] {title}".strip()
            text = prefix
            if message:
                text = f"{prefix}\n\n{message}"

            # 简单映射到 info / warning / error
            if "ERROR" in level_name or "FATAL" in level_name:
                self.error(text)
            elif "WARN" in level_name:
                self.warning(text)
            else:
                self.info(text)

        alerts.send_alert = MethodType(_send_alert, alerts)
        print("✅ AlertManager compatibility shim (send_alert) attached")
    if FUTURES_MARKET_TYPE == "UM":
        adapter = BinanceUMFuturesAdapter(trading_mode=TRADING_MODE)
    else:
        adapter = BinanceCMFuturesAdapter(trading_mode=TRADING_MODE)
    print(f"✅ {FUTURES_MARKET_TYPE} adapter initialized")

    executor = OrderExecutor(adapter, ledger)
    print("✅ Order executor initialized")

    risk_manager = FuturesRiskManager()
    print("✅ Risk manager initialized")

    # Initialize EdgeGate v2 with PROBE position mechanism
    edge_gate_v2 = create_default_edge_gate_v2()
    print("✅ EdgeGate v2 initialized")

    edge_stats = create_default_edge_stats()
    print(f"✅ EdgeStats initialized ({edge_stats.get_statistics()['count']} historical records)")

    edge_diagnostics = create_default_diagnostics()
    print("✅ EdgeGate diagnostics initialized")

    print("\n🔍 Performing state reconciliation...")
    reconciliation = StateReconciliation(ledger, adapter)
    recon_mode, recon_report = reconciliation.perform_reconciliation()

    print(f"Reconciliation mode: {recon_mode}")
    if recon_mode == ReconciliationMode.CLOSE_ONLY:
        alerts.alert_reconciliation_failed(recon_report)
        print("⚠️  System in CLOSE_ONLY mode - will only close positions")
    elif recon_mode == ReconciliationMode.EMERGENCY_STOP:
        print("🚨 EMERGENCY STOP - cannot proceed")
        alerts.send_alert(
            AlertLevel.CRITICAL, "Emergency Stop", "Critical reconciliation failure"
        )
        sys.exit(1)

    alerts.alert_system_startup(TRADING_MODE, ledger.run_id)

    print("\n✅ All systems ready!")
    print(f"📝 Ledger: {ledger.base_dir}")
    print(f"📊 Metrics: {metrics.output_dir}")
    print(f"🚀 Starting trading loop...\n")

    batch_id = 0

    try:
        while True:
            batch_id += 1
            batch_now = datetime.now(timezone.utc)

            symbols = SYMBOLS.copy()
            if BATCH_SHUFFLE_SYMBOLS:
                random.shuffle(symbols)

            print("\n" + "=" * 60)
            print(f"BATCH {batch_id}")
            print("=" * 60)
            print(f"Time: {_fmt_ts(batch_now)}")
            print(f"Symbols: {symbols}")
            print(f"Remaining quota: {get_remaining_quota()}")

            if batch_id > 0 and batch_id % 10 == 0:
                metrics.save_snapshot()
                print("\n" + metrics.get_summary())

            # Determine if we can open new positions
            elapsed_minutes = (batch_now - startup_time).total_seconds() / 60.0
            in_warmup = elapsed_minutes < STARTUP_WARMUP_MINUTES

            if in_warmup:
                print(
                    f"[WARMUP] Elapsed={elapsed_minutes:.1f}m "
                    f"< {STARTUP_WARMUP_MINUTES}m, monitoring only, no new positions."
                )

            # 只有：1) 对账模式是 NORMAL 且 2) 已经过了冷静期，才允许开新仓
            can_open_new = (recon_mode == ReconciliationMode.NORMAL) and (not in_warmup)

            prefetch_map: Dict[str, Dict[str, Any]] = {}

            if BATCH_FETCH_CONCURRENT and len(symbols) > 1:
                workers = max(1, min(BATCH_MAX_WORKERS, len(symbols)))
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    future_map = {
                        ex.submit(_prefetch_symbol_pack, s): s for s in symbols
                    }
                    for fut in as_completed(future_map):
                        s = future_map[fut]
                        try:
                            prefetch_map[s] = fut.result()
                        except Exception as e:
                            prefetch_map[s] = {
                                "symbol": s,
                                "ok": False,
                                "error": str(e),
                            }
            else:
                for s in symbols:
                    prefetch_map[s] = _prefetch_symbol_pack(s)

            for symbol in symbols:
                try:
                    run_once_for_symbol(
                        symbol,
                        ledger,
                        adapter,
                        risk_manager,
                        alerts,
                        metrics,
                        edge_gate_v2,
                        edge_stats,
                        edge_diagnostics,
                        now_ts=batch_now,
                        prefetch=prefetch_map.get(symbol),
                        batch_id=batch_id,
                        can_open_new=can_open_new,
                        in_warmup=in_warmup,
                    )
                except Exception as e:
                    print(f"[ERROR] {symbol}: {e}")
                    alerts.send_alert(
                        AlertLevel.ERROR,
                        f"Trading Error: {symbol}",
                        f"Batch {batch_id}\n{type(e).__name__}: {e}",
                    )

            sleep_sec = next_round_sleep_sec()
            print(f"\n[BATCH] Finished {batch_id}. Next round in {sleep_sec}s")
            time.sleep(sleep_sec)

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        alerts.alert_system_shutdown("User interrupt")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        alerts.send_alert(AlertLevel.ERROR, "System Error", str(e))
        raise
    finally:
        print("\n" + "=" * 60)
        print("FINAL METRICS")
        print("=" * 60)
        print(metrics.get_summary())
        metrics.save_snapshot()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user")
    except Exception as e:
        print(f"\n[FATAL ERROR] {type(e).__name__}: {e}")
        raise
