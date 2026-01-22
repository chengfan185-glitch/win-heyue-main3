# -*- coding: utf-8 -*-
"""execution/adapters/binance_um_futures.py (FIXED)

Clean, Pylance-friendly Binance USDT-Margined Futures (UM) adapter.

Key behavior
- success=True only when Binance returns a valid orderId
- Exposes Binance error payloads (code/msg) on HTTP 4xx
- Supports hedge mode (dualSidePosition=True) by sending positionSide automatically
- Fixes quantity precision: formats quantity to LOT_SIZE / MARKET_LOT_SIZE stepSize
- Correct reduceOnly + positionSide logic (no dead code / no None positionSide)

Important UM Futures note
- UM Futures MARKET orders use `quantity` (base asset).
  `quoteOrderQty` is not supported on many futures endpoints and can trigger HTTP 400.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.parse
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Literal, Optional, Tuple

import requests

PositionSide = Literal["LONG", "SHORT", "BOTH"]


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    qty: float = 0.0
    avg_price: float = 0.0
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class PositionInfo:
    """Normalized position object used by runner/reconciliation."""
    symbol: str
    position_amt: float
    entry_price: float = 0.0
    position_side: str = "BOTH"  # 'LONG'/'SHORT'/'BOTH'


class BinanceUMFuturesAdapter:
    """Binance UM Futures REST adapter."""

    def __init__(
        self,
        trading_mode: str = "paper",
        enable_real: bool = False,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        timeout: int = 15,
    ) -> None:
        self.trading_mode = str(trading_mode).lower().strip()
        self.enable_real = bool(enable_real)

        self.base_url = (
            base_url
            or os.getenv("BINANCE_FUTURES_BASE_URL")
            or "https://fapi.binance.com"
        ).rstrip("/")

        self.api_key = api_key or os.getenv("BINANCE_API_KEY") or ""
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET") or ""
        self.timeout = int(timeout)

        self._session = requests.Session()
        if self.api_key:
            self._session.headers.update({"X-MBX-APIKEY": self.api_key})

        self._time_offset_ms = 0
        self._last_time_sync = 0.0

        self._exchange_info_cache: Optional[Dict[str, Any]] = None
        self._exchange_info_ts = 0.0

        print(
            f"[BinanceUMFuturesAdapter] trading_mode={self.trading_mode} enable_real={self.enable_real} "
            f"base_url={self.base_url} api_key={(self.api_key[:4] + '...' + self.api_key[-4:]) if self.api_key else ''}"
        )

    # ------------------------
    # Helpers
    # ------------------------

    def _log(self, msg: str) -> None:
        if os.getenv("BINANCE_ADAPTER_DEBUG", "0").lower() in ("1", "true", "yes"):
            print(msg)

    def _now_ms(self) -> int:
        return int(time.time() * 1000) + int(self._time_offset_ms)

    def _sync_time(self, force: bool = False) -> None:
        """Sync local timestamp to Binance server time to avoid -1021 errors."""
        if self.trading_mode == "paper" or not self.enable_real:
            return
        if (not force) and (time.time() - self._last_time_sync < 60):
            return
        try:
            url = self.base_url + "/fapi/v1/time"
            r = self._session.get(url, timeout=self.timeout)
            r.raise_for_status()
            server_time = int(r.json().get("serverTime", 0))
            local_time = int(time.time() * 1000)
            self._time_offset_ms = server_time - local_time
            self._last_time_sync = time.time()
            self._log(f"[time_sync] offset_ms={self._time_offset_ms}")
        except Exception as e:
            self._log(f"[time_sync] failed: {e}")

    def _sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_secret:
            raise RuntimeError("BINANCE_API_SECRET missing")
        clean = {k: v for k, v in params.items() if v is not None}
        clean["timestamp"] = int(clean.get("timestamp") or self._now_ms())
        query = urllib.parse.urlencode(clean, doseq=True)
        sig = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        clean["signature"] = sig
        return clean

    @staticmethod
    def _parse_binance_error(resp: requests.Response) -> str:
        try:
            j = resp.json()
            code = j.get("code")
            msg = j.get("msg")
            if code is not None or msg is not None:
                return f"HTTP {resp.status_code} | code={code} | msg={msg}"
        except Exception:
            pass
        txt = (resp.text or "").strip()
        if len(txt) > 300:
            txt = txt[:300] + "..."
        return f"HTTP {resp.status_code} | body={txt}"

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True,
    ) -> Any:
        """Low-level request wrapper.

        signed=True: add timestamp/signature, requires API key/secret.
        """
        if self.trading_mode == "paper" or not self.enable_real:
            raise RuntimeError("Adapter is in paper mode or real trading disabled")

        params = params or {}
        method_u = method.upper().strip()

        if signed:
            self._sync_time(force=False)
            params = self._sign_params(params)

        url = self.base_url + path
        self._log(f"[request] {method_u} {url} params={params}")

        try:
            r = self._session.request(method_u, url, params=params, timeout=self.timeout)
            if r.status_code >= 400:
                raise RuntimeError(self._parse_binance_error(r))
            if not r.text:
                return {}
            return r.json()
        except Exception as e:
            s = str(e)
            if ("-1021" in s or "timestamp" in s.lower()) and signed:
                self._sync_time(force=True)
            raise

    # ------------------------
    # ExchangeInfo / Precision
    # ------------------------

    def get_exchange_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        if (not force_refresh) and self._exchange_info_cache and (time.time() - self._exchange_info_ts < 3600):
            return self._exchange_info_cache
        url = self.base_url + "/fapi/v1/exchangeInfo"
        r = self._session.get(url, timeout=self.timeout)
        r.raise_for_status()
        self._exchange_info_cache = r.json()
        self._exchange_info_ts = time.time()
        return self._exchange_info_cache

    def _lot_step_str(self, symbol: str) -> str:
        """Return stepSize string for quantity precision (UM futures). Prefer LOT_SIZE; fallback MARKET_LOT_SIZE."""
        ex = self.get_exchange_info()
        sym = None
        for s in ex.get("symbols", []):
            if s.get("symbol") == symbol:
                sym = s
                break
        if not sym:
            return "1"

        for f in sym.get("filters", []):
            if f.get("filterType") == "LOT_SIZE":
                return str(f.get("stepSize", "1"))

        for f in sym.get("filters", []):
            if f.get("filterType") == "MARKET_LOT_SIZE":
                return str(f.get("stepSize", "1"))

        return "1"

    def _format_qty_to_step(self, symbol: str, qty: float) -> str:
        """Floor qty to stepSize and output as clean decimal string."""
        step_str = self._lot_step_str(symbol)
        step = Decimal(step_str)
        q = Decimal(str(qty))

        if step != 0:
            q = (q / step).to_integral_value(rounding=ROUND_DOWN) * step

        q = q.quantize(step, rounding=ROUND_DOWN) if step < 1 else q.to_integral_value(rounding=ROUND_DOWN)
        s = format(q, "f").rstrip("0").rstrip(".")
        return s if s else "0"

    def _get_symbol_lot(self, symbol: str) -> Tuple[float, float]:
        """Return (stepSize, minQty) for the symbol."""
        info = self.get_exchange_info()
        sym = None
        for s in info.get("symbols", []):
            if s.get("symbol") == symbol:
                sym = s
                break
        if not sym:
            raise RuntimeError(f"Unknown symbol in exchangeInfo: {symbol}")

        step = 0.0
        min_qty = 0.0
        for f in sym.get("filters", []):
            if f.get("filterType") == "LOT_SIZE":
                step = float(f.get("stepSize", 0) or 0)
                min_qty = float(f.get("minQty", 0) or 0)
                break

        if step <= 0:
            step = 0.001
        return step, min_qty

    @staticmethod
    def _floor_to_step(x: float, step: float) -> float:
        if step <= 0:
            return x
        n = int(x / step)
        return float(n * step)

    # ------------------------
    # Market data
    # ------------------------

    def get_mark_price(self, symbol: str) -> float:
        url = self.base_url + "/fapi/v1/premiumIndex"
        r = self._session.get(url, params={"symbol": symbol}, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        return float(j.get("markPrice") or j.get("indexPrice") or 0.0)

    def notional_to_qty(self, symbol: str, notional_usdt: float, price: Optional[float] = None) -> float:
        px = float(price) if price is not None else self.get_mark_price(symbol)
        step, min_qty = self._get_symbol_lot(symbol)
        raw_qty = float(notional_usdt) / px if px > 0 else 0.0

        qty = self._floor_to_step(raw_qty, step)
        if min_qty > 0 and qty < min_qty:
            qty = min_qty
        qty = self._floor_to_step(qty, step)
        return qty

    # ------------------------
    # Account state
    # ------------------------

    def is_dual_side_enabled(self, force_refresh: bool = False) -> bool:
        _ = force_refresh
        res = self._request("GET", "/fapi/v1/positionSide/dual", {}, signed=True)
        return bool(res.get("dualSidePosition"))

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return list(self._request("GET", "/fapi/v1/openOrders", params, signed=True) or [])

    def get_all_orders(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        params = {"symbol": symbol, "limit": int(limit)}
        return list(self._request("GET", "/fapi/v1/allOrders", params, signed=True) or [])

    def get_user_trades(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        params = {"symbol": symbol, "limit": int(limit)}
        return list(self._request("GET", "/fapi/v1/userTrades", params, signed=True) or [])

    def get_position_risk(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        data = self._request("GET", "/fapi/v2/positionRisk", params, signed=True)
        return list(data or [])

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        try:
            leverage_i = int(leverage)
        except Exception:
            leverage_i = 1
        params = {"symbol": symbol, "leverage": leverage_i}
        try:
            self._request("POST", "/fapi/v1/leverage", params, signed=True)
            return True
        except Exception as e:
            self._log(f"[set_leverage] failed: {e}")
            return False

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> bool:
        mt = str(margin_type).upper().strip()
        if mt in ("CROSS", "CROSSED"):
            mt = "CROSSED"
        if mt not in ("ISOLATED", "CROSSED"):
            mt = "ISOLATED"
        params = {"symbol": symbol, "marginType": mt}
        try:
            self._request("POST", "/fapi/v1/marginType", params, signed=True)
            return True
        except Exception as e:
            msg = str(e)
            if "-4046" in msg:
                return True
            self._log(f"[set_margin_type] failed: {e}")
            return False

    def get_positions_raw(self, nonzero_only: bool = True) -> List[Dict[str, Any]]:
        if self.trading_mode == "paper" or not self.enable_real:
            return []
        data = self.get_position_risk(symbol=None)
        out: List[Dict[str, Any]] = []
        for p in data:
            try:
                amt = float(p.get("positionAmt", 0) or 0)
            except Exception:
                amt = 0.0
            if nonzero_only and amt == 0:
                continue
            out.append(p)
        return out
    def fetch_open_positions(self) -> List[Dict[str, Any]]:
        """
        Backward-compatible helper. Returns raw nonzero positions from Binance positionRisk.
        Each element is the raw dict containing keys such as: symbol, positionAmt, entryPrice, leverage, etc.
        """
        return self.get_positions_raw(nonzero_only=True)


    def get_positions(self) -> List[PositionInfo]:
        if self.trading_mode == "paper" or not self.enable_real:
            return []
        data = self.get_position_risk(symbol=None)
        out: List[PositionInfo] = []
        for p in (data or []):
            try:
                amt = float(p.get("positionAmt", 0) or 0)
            except Exception:
                amt = 0.0
            if amt == 0:
                continue

            sym = str(p.get("symbol", ""))
            try:
                entry = float(p.get("entryPrice", 0) or 0)
            except Exception:
                entry = 0.0

            pos_side = "LONG" if amt > 0 else "SHORT"
            out.append(PositionInfo(symbol=sym, position_amt=amt, entry_price=entry, position_side=pos_side))
        return out

    def get_position(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        positions = self.get_positions()
        if not symbol:
            return positions
        sym_u = str(symbol).upper()
        return [p for p in positions if str(p.symbol).upper() == sym_u]

    # ------------------------
    # Trading
    # ------------------------

    def place_market_order(
        self,
        symbol: str,
        side: str,  # BUY / SELL
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,  # alias for notional_usdt
        notional_usdt: Optional[float] = None,
        reduce_only: bool = False,
        position_side: Optional[PositionSide] = None,
        **kwargs: Any,
    ) -> OrderResult:
        _ = kwargs

        # Paper mode: do not hit Binance
        if self.trading_mode == "paper":
            qty = float(quantity or 0.0)
            if qty <= 0 and (notional_usdt is not None or quote_quantity is not None):
                # If caller only provided notional in paper, we keep qty=0 (runner usually doesn't rely on this)
                qty = 0.0
            return OrderResult(success=True, order_id=f"paper_{symbol}_{side}", qty=qty, avg_price=0.0)

        if not self.enable_real:
            return OrderResult(success=False, error="ENABLE_REAL_TRADING=false")

        side_u = str(side).upper().strip()
        if side_u not in ("BUY", "SELL"):
            return OrderResult(success=False, error=f"Invalid side={side}")

        # Normalize notional amount aliases
        if notional_usdt is None and quote_quantity is not None:
            notional_usdt = quote_quantity

        # Exactly one of quantity / notional_usdt
        if (quantity is None) == (notional_usdt is None):
            return OrderResult(success=False, error="Provide exactly one: quantity OR notional_usdt")

        try:
            if quantity is None:
                q = self.notional_to_qty(symbol, float(notional_usdt or 0.0))
            else:
                q = float(quantity)

            if q <= 0:
                return OrderResult(success=False, error=f"Invalid computed quantity={q}")

            # Detect hedge mode
            dual = False
            try:
                dual = bool(self.is_dual_side_enabled(force_refresh=True))
            except Exception:
                dual = False

            # IMPORTANT: format quantity to stepSize to avoid -1111 precision errors
            q_str = self._format_qty_to_step(symbol, float(q))
            if q_str in ("0", "0.0", "0.00"):
                return OrderResult(success=False, error=f"Quantity floored to zero by stepSize: raw={q}")

            params: Dict[str, Any] = {
                "symbol": symbol,
                "side": side_u,
                "type": "MARKET",
                "quantity": q_str,
                "recvWindow": 5000,
            }

            # Hedge mode: must include positionSide; do NOT send reduceOnly by default
            if dual:
                if position_side is None:
                    position_side = "LONG" if side_u == "BUY" else "SHORT"
                params["positionSide"] = position_side
            else:
                # One-way mode: allow reduceOnly
                if reduce_only:
                    params["reduceOnly"] = "true"

            # newClientOrderId
            params["newClientOrderId"] = f"{symbol}_{side_u}_{int(time.time() * 1000)}"

            res = self._request("POST", "/fapi/v1/order", params, signed=True)

            order_id = str(res.get("orderId") or "")
            if not order_id:
                return OrderResult(success=False, error=f"No orderId returned | response={res}", raw=res)

            executed_qty = float(res.get("executedQty", 0) or 0.0)
            avg_price = float(res.get("avgPrice", 0) or 0.0)

            # Backfill from userTrades if needed
            if executed_qty <= 0 or avg_price <= 0:
                try:
                    trades = self.get_user_trades(symbol, limit=50)
                    fills = [t for t in trades if str(t.get("orderId")) == order_id]
                    if fills:
                        qty_sum = sum(float(t.get("qty", 0) or 0) for t in fills)
                        quote_sum = sum(float(t.get("quoteQty", 0) or 0) for t in fills)
                        if qty_sum > 0:
                            executed_qty = qty_sum
                            avg_price = quote_sum / qty_sum
                except Exception:
                    pass

            return OrderResult(
                success=True,
                order_id=order_id,
                exchange_order_id=order_id,
                qty=float(executed_qty or float(q_str)),
                avg_price=float(avg_price or 0.0),
                error=None,
                raw=res,
            )

        except Exception as e:
            return OrderResult(success=False, error=str(e))

    def close_position(self, symbol: str, position_side: PositionSide = "LONG") -> OrderResult:
        """Close position. Hedge mode closes by opposite side with same positionSide; one-way uses reduceOnly."""
        try:
            dual = bool(self.is_dual_side_enabled(force_refresh=True))
        except Exception:
            dual = False

        prs = self.get_position_risk(symbol)
        amt = 0.0
        for p in prs:
            if dual:
                if str(p.get("positionSide")) == str(position_side):
                    amt = float(p.get("positionAmt", 0) or 0)
                    break
            else:
                amt = float(p.get("positionAmt", 0) or 0)
                break

        if amt == 0:
            return OrderResult(success=True, qty=0.0, avg_price=0.0)

        qty = abs(float(amt))
        if dual:
            side = "SELL" if position_side == "LONG" else "BUY"
            return self.place_market_order(
                symbol=symbol,
                side=side,
                quantity=qty,
                reduce_only=False,
                position_side=position_side,
            )
        else:
            side = "SELL" if amt > 0 else "BUY"
            return self.place_market_order(
                symbol=symbol,
                side=side,
                quantity=qty,
                reduce_only=True,
                position_side=None,
            )

    # ------------------------
    # Diagnostics
    # ------------------------

    def test_connection(self) -> bool:
        if self.trading_mode == "paper" or not self.enable_real:
            print("[test_connection] paper mode or real trading disabled - returning True")
            return True
        try:
            url = self.base_url + "/fapi/v1/ping"
            r = self._session.get(url, timeout=self.timeout)
            r.raise_for_status()
            self._sync_time(force=True)
            return True
        except Exception as e:
            print(f"[test_connection] failed: {e}")
            return False
