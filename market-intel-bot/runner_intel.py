# runner_intel.py
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Load .env (so os.getenv can see ENABLE_AI_INTEL / PROVIDER / KEY) ---
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()
except Exception:
    pass

import requests  # pip install requests

from intel.binance_futures_http import get_exchange_info, fetch_klines
from intel.ranker import score_symbol
from intel.features import atr_pct, noise_score, trend_strength


def universe_symbols(limit=120):
    info = get_exchange_info()
    out = []
    for s in info.get("symbols", []):
        if s.get("status") != "TRADING":
            continue
        if s.get("quoteAsset") != "USDT":
            continue
        if s.get("contractType") != "PERPETUAL":
            continue
        sym = s.get("symbol")
        if not sym or not sym.endswith("USDT"):
            continue
        out.append(sym)
    return out[:limit]


def _openai_call(prompt_text: str) -> dict:
    """
    Minimal OpenAI HTTP call (no SDK) with fallback:
      1) Responses API (/v1/responses)
      2) Chat Completions (/v1/chat/completions)
    Returns a normalized dict with:
      - ok (bool)
      - provider/model
      - text (assistant content)
      - raw_status/raw_json
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Try Responses API first
    url1 = "https://api.openai.com/v1/responses"
    payload1 = {
        "model": model,
        "input": prompt_text,
    }

    r = requests.post(url1, headers=headers, json=payload1, timeout=40)
    if r.status_code < 300:
        data = r.json()
        # Best-effort extract text
        text = ""
        try:
            # Many responses include output[].content[].text
            outs = data.get("output") or []
            if outs and isinstance(outs, list):
                content = outs[0].get("content") or []
                if content and isinstance(content, list):
                    # pick first text-like chunk
                    for c in content:
                        if c.get("type") == "output_text" and "text" in c:
                            text = c["text"]
                            break
        except Exception:
            text = ""

        return {
            "ok": True,
            "provider": "openai",
            "model": model,
            "text": text,
            "raw_status": r.status_code,
            "raw_json": data,
        }

    # Fallback: chat.completions
    url2 = "https://api.openai.com/v1/chat/completions"
    payload2 = {
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
    }
    r2 = requests.post(url2, headers=headers, json=payload2, timeout=40)
    data2 = {}
    try:
        data2 = r2.json()
    except Exception:
        pass

    if r2.status_code >= 300:
        raise RuntimeError(f"OpenAI HTTP {r2.status_code}: {str(data2)[:400]}")

    text2 = ""
    try:
        text2 = (data2.get("choices") or [])[0]["message"]["content"]
    except Exception:
        text2 = ""

    return {
        "ok": True,
        "provider": "openai",
        "model": model,
        "text": text2,
        "raw_status": r2.status_code,
        "raw_json": data2,
    }


def run_ai_market_intel(snapshot: dict) -> dict:
    """
    AI side-channel: generate market structure / risk notes for the current TopN.
    This DOES NOT output buy/sell signals; it outputs a compact JSON report.
    """
    # Guardrails: we want structured JSON output
    prompt = f"""
You are a quantitative market analyst. Produce a STRICT JSON object ONLY (no markdown, no extra text).
Goal: summarize market structure and risk based on TopN candidates for a futures execution bot.

Input snapshot JSON:
{json.dumps(snapshot, ensure_ascii=False)}

Output JSON schema (STRICT):
{{
  "meta": {{
    "provider": "openai",
    "model": "<model>",
    "ts": <unix int>
  }},
  "market_state": "<TREND|RANGE|CHAOS|MIXED>",
  "risk_off": <true|false>,
  "risk_notes": ["..."],
  "top_candidates": [
    {{"symbol":"XXXUSDT","bias":"LONG|SHORT|NEUTRAL","confidence":0.0,"notes":"..."}}
  ],
  "high_risk": [
    {{"symbol":"XXXUSDT","reason":"..."}}
  ]
}}

Rules:
- Do NOT output trade instructions or leverage/size.
- Use snapshot fields: expected_move_pct, noise_score, regime, edge_score.
- If noise_score is high (>=0.50), mark as higher risk.
- Keep confidence in [0,1], conservative.
""".strip()

    resp = _openai_call(prompt)

    # Parse JSON from model output text (best-effort)
    ai_text = (resp.get("text") or "").strip()
    ai_json = None
    parse_err = None

    if ai_text:
        try:
            ai_json = json.loads(ai_text)
        except Exception as e:
            parse_err = f"AI output not valid JSON: {repr(e)}"

    out = {
        "meta": {
            "provider": "openai",
            "model": resp.get("model"),
            "ts": int(time.time()),
        },
        "ok": bool(resp.get("ok")),
    }

    if ai_json and isinstance(ai_json, dict):
        # Merge but keep our meta authoritative
        ai_json.setdefault("meta", {})
        ai_json["meta"]["provider"] = "openai"
        ai_json["meta"]["model"] = resp.get("model")
        ai_json["meta"]["ts"] = int(time.time())
        return ai_json

    # Fallback: store raw (so you still have proof of calling)
    out["parse_error"] = parse_err
    out["raw_status"] = resp.get("raw_status")
    out["raw_json_preview"] = str(resp.get("raw_json"))[:1200]
    out["raw_text_preview"] = ai_text[:1200]
    return out


def main():
    hold_minutes = int(os.getenv("HOLD_MINUTES", "60"))
    interval = os.getenv("INTEL_INTERVAL", "15m")
    lookback = int(os.getenv("INTEL_LOOKBACK", "120"))
    uni_n = int(os.getenv("UNIVERSE", "80"))

    # Compatibility with older env naming in your repo
    topk = int(os.getenv("TOPN_K") or os.getenv("INTEL_TOPN_COUNT") or "10")
    out_path = os.getenv("TOPN_OUTPUT_PATH") or os.getenv("INTEL_TOPN_PATH") or r"..\win-heyue-main3\shared\topn.json"

    # Default is intentionally permissive to avoid "0 symbols" at boot.
    cost_pct = float(os.getenv("COST_PCT") or "0.0010")

    syms = universe_symbols(uni_n)
    results = []
    relaxed = []  # used only if strict scoring yields zero

    max_workers = int(os.getenv("MAX_WORKERS", "4"))
    ok_fetch = 0
    err_fetch = 0
    ok_score = 0
    skip_score = 0
    sample_err = None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fetch_klines, s, interval, lookback): s for s in syms}
        for f in as_completed(futs):
            s = futs[f]
            try:
                kl = f.result()
                ok_fetch += 1

                # Always compute probes so we can rank a fallback list if needed.
                atr = atr_pct(kl)
                noise = noise_score(kl)
                ts = trend_strength(kl)
                expected_move = atr * (max(hold_minutes / 15, 1.0) ** 0.5)
                relaxed.append({
                    "symbol": s,
                    "expected_move_pct": expected_move,
                    "noise_score": noise,
                    "trend_strength": ts,
                })

                sc = score_symbol(kl, cost_pct=cost_pct, hold_minutes=hold_minutes)
                if sc:
                    ok_score += 1
                    results.append({"symbol": s, **sc})
                else:
                    skip_score += 1

            except Exception as e:
                err_fetch += 1
                if sample_err is None:
                    sample_err = f"{s}: {repr(e)}"

    print(f"[ai] enabled={os.getenv('ENABLE_AI_INTEL')} provider={os.getenv('MARKET_INTEL_PROVIDER')} key={'YES' if os.getenv('OPENAI_API_KEY') else 'NO'}")
    print(f"[intel] fetch_ok={ok_fetch} fetch_err={err_fetch} score_ok={ok_score} score_skip={skip_score}")
    if sample_err:
        print(f"[intel] first_err={sample_err}")

    # If strict filtering yields nothing, fall back to a permissive ranking so execution bot
    # can still rotate symbols (it will still do its own entry rules and risk checks).
    if not results:
        trend_bonus_k = float(os.getenv("FALLBACK_TREND_BONUS_K", "15"))
        noise_penalty_k = float(os.getenv("FALLBACK_NOISE_PENALTY_K", "40"))
        for r in relaxed:
            r["edge_score"] = 100.0 * (r["expected_move_pct"] / max(cost_pct, 1e-6)) \
                              - noise_penalty_k * r["noise_score"] \
                              + trend_bonus_k * r["trend_strength"]
            r["regime"] = "FALLBACK"
            r["why"] = ["relaxed_fallback"]
        relaxed.sort(key=lambda x: x["edge_score"], reverse=True)
        results = relaxed

    results.sort(key=lambda x: x["edge_score"], reverse=True)
    topn = results[:topk]
    symbols = [x["symbol"] for x in topn]

    payload = {
        "ts": int(time.time()),
        "timeframe": interval,
        "hold_minutes": hold_minutes,
        "cost_pct": cost_pct,
        "symbols": symbols,
        "topn": topn
    }

    # --- AI side-channel ---
    ai_enabled = (os.getenv("ENABLE_AI_INTEL", "0").lower() in ("1", "true", "yes"))
    provider = (os.getenv("MARKET_INTEL_PROVIDER", "") or "").strip().lower()
    ai_out_path = os.getenv("AI_INTEL_OUTPUT_PATH") or (os.path.join(os.path.dirname(out_path), "ai_intel.json"))

    if ai_enabled and provider == "openai":
        try:
            print("[ai] calling OpenAI...")
            snapshot = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "timeframe": interval,
                "hold_minutes": hold_minutes,
                "cost_pct": cost_pct,
                "topn": [
                    {
                        "symbol": r.get("symbol"),
                        "edge_score": float(r.get("edge_score", 0.0)),
                        "expected_move_pct": float(r.get("expected_move_pct", 0.0)),
                        "noise_score": float(r.get("noise_score", 0.0)),
                        "regime": r.get("regime"),
                        "why": r.get("why", []),
                    }
                    for r in topn
                ],
            }

            ai_result = run_ai_market_intel(snapshot)

            os.makedirs(os.path.dirname(ai_out_path), exist_ok=True)
            with open(ai_out_path, "w", encoding="utf-8") as af:
                json.dump(ai_result, af, ensure_ascii=False, indent=2)

            payload["ai_intel_path"] = ai_out_path
            payload["ai_intel_provider"] = "openai"
            payload["ai_intel_model"] = (ai_result.get("meta") or {}).get("model")

            print(f"[ai] wrote ai_intel -> {ai_out_path}")

        except Exception as e:
            print(f"[ai] error={repr(e)}")
            payload["ai_intel_error"] = repr(e)

    else:
        # Not enabled or provider not set — explicitly record state for auditing
        payload["ai_intel_state"] = {
            "enabled": ai_enabled,
            "provider": provider or None
        }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[intel] universe={len(syms)} results={len(results)} topk={len(symbols)}")


if __name__ == "__main__":
    interval_sec = int(os.getenv("TOPN_REFRESH_SECONDS", "300"))  # 默认5分钟
    while True:
        try:
            main()
        except Exception as e:
            print(f"[intel] loop error: {repr(e)}")
        time.sleep(interval_sec)
