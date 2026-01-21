import math

def _to_ohlc(klines):
    o = [float(x[1]) for x in klines]
    h = [float(x[2]) for x in klines]
    l = [float(x[3]) for x in klines]
    c = [float(x[4]) for x in klines]
    return o,h,l,c

def atr_pct(klines, n=14):
    o,h,l,c = _to_ohlc(klines)
    tr = []
    for i in range(1, len(c)):
        tr_i = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
        tr.append(tr_i)
    if len(tr) < n+1:
        return 0.0
    atr = sum(tr[-n:]) / n
    return atr / c[-1] if c[-1] else 0.0

def noise_score(klines, n=30):
    o,h,l,c = _to_ohlc(klines)
    n = min(n, len(c))
    scores = []
    for i in range(-n, 0):
        rng = h[i]-l[i]
        if rng <= 0:
            continue
        body = abs(c[i]-o[i])
        wick = max(rng - body, 0.0)
        scores.append(wick / rng)
    return sum(scores)/len(scores) if scores else 1.0

def ema(series, alpha):
    v = series[0]
    for x in series[1:]:
        v = alpha * x + (1-alpha) * v
    return v

def trend_strength(klines):
    o,h,l,c = _to_ohlc(klines)
    if len(c) < 50:
        return 0.0
    fast = ema(c[-50:], 2/(10+1))
    slow = ema(c[-50:], 2/(30+1))
    return abs(fast - slow) / c[-1] if c[-1] else 0.0
