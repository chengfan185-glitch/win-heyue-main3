# core/strategy/alpha_gate.py
from collections import deque
import numpy as np

class AlphaGate:
    """
    规则 Alpha Gate
    - 识别极端状态
    - 决定是否允许进入 ML Gate
    """

    def __init__(
        self,
        price_th_5m=0.0025,      # +0.25%
        volume_th_5m=0.80,       # +80%
        vol_quantile=0.90,       # 波动率分位
        vol_window=30            # 最近 N 条用于计算分位
    ):
        self.price_th_5m = price_th_5m
        self.volume_th_5m = volume_th_5m
        self.vol_quantile = vol_quantile
        self.vol_window = vol_window
        self._vol_hist = deque(maxlen=vol_window)

    def update(self, feats: dict):
        """
        每个 tick / bar 调用一次
        """
        v = feats.get("volatility_5m")
        if v is not None:
            self._vol_hist.append(float(v))

    def _vol_extreme(self, v: float) -> bool:
        if len(self._vol_hist) < self.vol_window:
            return False
        q = np.quantile(self._vol_hist, self.vol_quantile)
        return v >= q

    def is_extreme(self, feats: dict) -> dict:
        """
        返回:
        {
          "pass": bool,
          "hit_rules": [list]
        }
        """
        hit = []

        # Rule 1: 短期价格冲高
        if feats.get("price_change_5m", 0) >= self.price_th_5m:
            hit.append("PRICE_SPIKE_5M")

        # Rule 2: 成交量异常
        if feats.get("volume_change_5m", 0) >= self.volume_th_5m:
            hit.append("VOLUME_SPIKE_5M")

        # Rule 3: 波动率异常
        v = feats.get("volatility_5m")
        if v is not None and self._vol_extreme(v):
            hit.append("VOLATILITY_EXTREME_5M")

        return {
            "pass": len(hit) >= 2,
            "hit_rules": hit
        }
