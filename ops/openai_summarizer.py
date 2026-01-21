from __future__ import annotations

import time
from typing import Any, Dict, List

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

from ops.openai_budget import allow_call, load_budget, save_budget


def summarize_topn(
    topn: List[Dict[str, Any]],
    api_key: str,
    model: str,
    max_tokens: int,
    daily_budget_usd: float,
    cooldown_seconds: int,
    budget_file: str,
) -> str:
    if not api_key or OpenAI is None:
        return ""

    b = load_budget(budget_file)
    if not allow_call(b, daily_budget_usd, cooldown_seconds):
        return ""

    client = OpenAI(api_key=api_key)

    # Keep prompt compact; do not exceed max_tokens
    lines = []
    for r in topn:
        lines.append(
            f"{r['symbol']}: score={r['score']:.3f}, trend={r['trend']:.4f}, vol={r['vol']:.6f}, breakout={r['breakout']:.3f}, noise={r['noise']:.2f}"
        )
    prompt = "You are a crypto market analyst. Provide a terse bullet summary of the Top candidates and why they rank high. Avoid predictions. Provide risk notes.\n\n" + "\n".join(lines)

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )

    text = (resp.choices[0].message.content or "").strip()

    # Approximate cost: you can refine later with real pricing; for now, track by tokens.
    usage = getattr(resp, "usage", None)
    if usage:
        # crude estimate: $0.0005 per 1K tokens (placeholder)
        tokens = float((usage.total_tokens or 0))
        est = tokens / 1000.0 * 0.0005
    else:
        est = 0.001

    b.spent_usd += est
    b.last_call_ts = time.time()
    save_budget(budget_file, b)

    return text
