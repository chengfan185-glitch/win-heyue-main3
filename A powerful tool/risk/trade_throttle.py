import time

class TradeThrottle:
    def __init__(self, min_interval_sec=300):
        self.min_interval_sec = min_interval_sec
        self.last_trade_ts = {}

    def allow(self, symbol):
        now = time.time()
        last = self.last_trade_ts.get(symbol, 0)
        if now - last < self.min_interval_sec:
            return False
        self.last_trade_ts[symbol] = now
        return True
