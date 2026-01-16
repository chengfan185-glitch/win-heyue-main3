from __future__ import annotations
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "analysis" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FILE = DATA_DIR / "samples_5m_600v2.csv"

# ---------- 可调参数（先别乱改） ----------
HOLD_BARS = int(os.getenv("PB_HOLD_BARS", "3"))  # 3 根 5m = 15 分钟
TAKER_FEE_RATE = float(os.getenv("PB_TAKER_FEE_RATE", "0.0004"))  # 0.04% 单边
SLIPPAGE_RATE = float(os.getenv("PB_SLIPPAGE_RATE", "0.0005"))    # 5 bps 单边
# ---------------------------------------

def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for k in candidates:
        if k.lower() in cols:
            return cols[k.lower()]
    return None

def _parse_action(x: Any) -> str:
    if x is None:
        return "HOLD"
    s = str(x).strip().upper()
    if s in {"LONG", "BUY"}:
        return "LONG"
    if s in {"SHORT", "SELL"}:
        return "SHORT"
    if s in {"HOLD", "NONE", ""}:
        return "HOLD"
    return s  # 兼容别的命名

def _split_tags(val: Any) -> List[str]:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return []
    s = str(val).strip()
    if not s:
        return []
    for sep in ["|", ",", ";", "，", "、"]:
        s = s.replace(sep, "|")
    return [t.strip() for t in s.split("|") if t.strip()]

def calc_max_drawdown(equity_curve: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / np.maximum(peak, 1e-12)
    return float(dd.min())

def main():
    file_path = Path(os.getenv("PB_SAMPLES_FILE", str(DEFAULT_FILE)))
    if not file_path.exists():
        raise FileNotFoundError(f"Samples file not found: {file_path}")

    df = pd.read_csv(file_path)
    if len(df) < (HOLD_BARS + 2):
        raise ValueError("Not enough rows to run backtest.")

    # 尝试自动识别关键列
    price_col = _find_col(df, ["close", "price", "last_price", "entry_price"])
    action_col = _find_col(df, ["action", "decision", "signal", "final_action"])
    allow_col  = _find_col(df, ["approved", "allow", "is_allowed", "passed"])
    tags_col   = _find_col(df, ["risk_tags", "risk_tag", "tags"])
    tf_col     = _find_col(df, ["timeframe", "tf"])

    if price_col is None:
        raise ValueError("Cannot find price column (expected close/price).")
    if action_col is None:
        raise ValueError("Cannot find action/decision column (expected action/decision/signal).")

    # 标准化
    prices = df[price_col].astype(float).to_numpy()
    actions = df[action_col].apply(_parse_action).to_numpy()

    # 是否允许交易（如果没有列，就默认：非 HOLD 都算 ALLOW）
    if allow_col is not None:
        allowed_flags = df[allow_col].astype(str).str.lower().isin(["1", "true", "yes", "y", "allow", "approved"]).to_numpy()
    else:
        allowed_flags = (actions != "HOLD")

    # 只对允许且非 HOLD 的样本做“模拟成交”
    idxs = np.where((actions != "HOLD") & (allowed_flags))[0]

    trades = []
    equity = [1.0]  # 资金曲线（归一化）
    cost_per_round = 2.0 * (TAKER_FEE_RATE + SLIPPAGE_RATE)  # 进出各一次

    for i in idxs:
        exit_i = i + HOLD_BARS
        if exit_i >= len(prices):
            continue

        entry = prices[i]
        exitp = prices[exit_i]
        act = actions[i]

        if entry <= 0 or exitp <= 0:
            continue

        if act == "LONG":
            gross = (exitp / entry) - 1.0
        elif act == "SHORT":
            gross = (entry / exitp) - 1.0
        else:
            continue

        net = gross - cost_per_round

        equity.append(equity[-1] * (1.0 + net))
        trades.append({
            "index": int(i),
            "action": act,
            "entry": float(entry),
            "exit": float(exitp),
            "gross_ret": float(gross),
            "net_ret": float(net),
        })

    total_samples = int(len(df))
    trade_count = int(len(trades))
    allow_ratio = float(trade_count / max(1, total_samples))

    if trade_count == 0:
        net_expectancy = 0.0
        max_dd = 0.0
    else:
        net_expectancy = float(np.mean([t["net_ret"] for t in trades]))
        max_dd = calc_max_drawdown(np.array(equity, dtype=float))

    # Top 风险标签统计（如果存在列）
    tag_counts: Dict[str, int] = {}
    if tags_col is not None:
        for v in df[tags_col].to_list():
            for t in _split_tags(v):
                tag_counts[t] = tag_counts.get(t, 0) + 1
    top_risk_tags = [k for k, _ in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:3]]
    while len(top_risk_tags) < 3:
        top_risk_tags.append("(none)")

    # 给一句“结论”（先用保守规则）
    if trade_count < 20:
        final_conclusion = "成交样本偏少：先继续跑到 1000，再下结论"
    else:
        if net_expectancy > 0 and max_dd > -0.05:
            final_conclusion = "继续跑到 1000（方向正确）"
        elif net_expectancy <= 0:
            final_conclusion = "净期望值不为正：先别实盘，建议回到策略/过滤条件"
        else:
            final_conclusion = "回撤偏大：先强化风控或降低交易频率，再验证"

    # 输出报告
    report = {
        "samples_file": str(file_path),
        "timeframe": str(df[tf_col].iloc[0]) if tf_col and len(df) else "5m",
        "total_samples": total_samples,
        "trade_count": trade_count,
        "net_expectancy": net_expectancy,
        "max_drawdown": max_dd,
        "allow_ratio": allow_ratio,
        "top_risk_tags": top_risk_tags,
        "params": {
            "hold_bars": HOLD_BARS,
            "taker_fee_rate_one_way": TAKER_FEE_RATE,
            "slippage_rate_one_way": SLIPPAGE_RATE,
            "round_trip_cost": cost_per_round,
        },
        "conclusion": final_conclusion,
    }

    out_json = REPORT_DIR / f"paper_5m_{total_samples}.json"
    out_md = REPORT_DIR / f"paper_5m_{total_samples}.md"

    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md = f"""# Paper Backtest Report (5m / {total_samples})

- 样本文件：`{file_path.name}`
- 候选样本：{total_samples}
- 实际成交：{trade_count}
- 净期望值（均值）：{net_expectancy:+.4%}
- 最大回撤：{max_dd:.2%}
- ALLOW 占比：{allow_ratio:.0%}
- Top 风险标签：{", ".join(top_risk_tags)}

## 结论
{final_conclusion}

## 参数
- hold_bars: {HOLD_BARS}
- taker_fee_rate(one-way): {TAKER_FEE_RATE}
- slippage_rate(one-way): {SLIPPAGE_RATE}
- round_trip_cost: {cost_per_round}
"""
    out_md.write_text(md, encoding="utf-8")

    # 通知（AB）
    from tools.notify import notify_telegram, notify_windows

    summary_message = f"""
📊 *Market-bot 模拟完成（5m / {total_samples} 样本）*

• 候选样本：{total_samples}
• 实际成交：{trade_count}
• 净期望值：{net_expectancy:+.2%}
• 最大回撤：{max_dd:.2%}
• ALLOW 占比：{allow_ratio:.0%}

🔴 *Top 风险标签：*
1. {top_risk_tags[0]}
2. {top_risk_tags[1]}
3. {top_risk_tags[2]}

🧠 *结论：*
{final_conclusion}
""".strip()

    notify_telegram(summary_message)
    notify_windows("Market-bot 模拟完成", f"{total_samples} 样本｜期望值 {net_expectancy:+.2%}")

    print("\n==== PAPER BACKTEST DONE ====")
    print(f"[REPORT] {out_json}")
    print(f"[REPORT] {out_md}")
    print(summary_message)


if __name__ == "__main__":
    main()
