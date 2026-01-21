"""
DecisionEngine: 支持 ML 推理与规则回退，并增加“趋势兜底试单”机制。

逻辑层次：
1. 先用规则算一个 base_action（HOLD / LONG / SHORT）。
2. 再调用 ML：
   - A 线：如果 ML 给出强置信度的 LONG/SHORT → 直接覆盖（大仓位，比如 5%）。
   - B 线：否则，如果 base_action 是 HOLD，
           且 ML 在 LONG / SHORT 上有“次强”信号 → 用很小仓位试单（趋势兜底）。
3. 其它情况保持规则决策。
"""
import os

from typing import Tuple, Optional, Dict, Any

from domain.models.market_state import StrategySnapshot, Action


# ===== 参数（含 Debug 激进版 B 线） =====
DEFAULT_PARAMS = {
    "min_free_capital_ratio": 0.05,
    "min_fee_to_gas": 1.2,
    "enter_relative_apy": 0.65,
    "exit_relative_apy": 0.35,
    "max_position_perc_of_capital": 0.2,

    # A 线：强信号覆盖规则（方向非常明确才用 5% 仓位重锤）
    "ml_confidence_threshold": 0.70,

    # B 线：趋势兜底试单（当前为“激进调试模式”）
    # 目的：先验证链路，哪怕 HOLD 优势很大，也允许用极小仓位去「探一手」。
    "ml_trend_try_threshold": 0.02,    # LONG/SHORT 中较大的那个概率 >= 2% 就有资格试单
    "ml_trend_min_gap": 1.00,          # 不再限制 HOLD 与趋势的差距，主要为了今晚能看到它动一下
    "ml_trend_position_fraction": 0.01 # 试单仓位占总资金比例（1%）
}


class DecisionEngine:
    def __init__(self, ml_model: Optional[Any] = None, params: Optional[dict] = None):
        # 外部传入的 params 覆盖默认值
        self.ml_model = ml_model
        self.params = {**DEFAULT_PARAMS, **(params or {})}

    # =========================
    # 规则层（原始逻辑，基本不动）
    # =========================
    def _rule_only_decide(self, snapshot: StrategySnapshot) -> Tuple[Action, Optional[str], Dict, float]:
        """原本的规则决策逻辑，单独拆出来。"""

        # =====================================================
        # 🔴 强制真盘验证：只放行一单（DEBUG / REAL TRADE）
        # =====================================================
        if os.environ.get("FORCE_ONE_TRADE", "false") == "true":
            side = os.environ.get("RULE_DIRECTION", "SHORT").upper()
            amount = snapshot.capital.total_capital_usd * 0.01  # 1% 资金，小而安全
            if side == "LONG":
                return Action.LONG, None, {
                    "side": "BUY",
                    "price": None,
                    "amount_usd": amount,
                    "reason": "force_one_trade",
                }, 0.99
            else:
                return Action.SHORT, None, {
                    "side": "SELL",
                    "price": None,
                    "amount_usd": amount,
                    "reason": "force_one_trade",
                }, 0.99

        # ===== 原有规则逻辑（完全不动）=====
        capital = snapshot.capital
        if capital.free_capital_ratio < self.params["min_free_capital_ratio"]:
            return Action.HOLD, None, {}, 0.0

        best_score = -999.0
        best_pool = None
        best_pf = None

        for pf in snapshot.pool_features.values():
            score = (
                pf.relative_apy_rank * 0.6
                + min(1.0, pf.fee_to_gas_ratio / 5.0) * 0.3
                - max(0.0, pf.tvl_outflow_rate) * 0.1
            )
            if score > best_score:
                best_score = score
                best_pool = pf.pool_id
                best_pf = pf

        if best_pool is None or best_pf is None:
            return Action.HOLD, None, {}, 0.0

        pf = best_pf
        if (
            pf.relative_apy_rank >= self.params["enter_relative_apy"]
            and pf.fee_to_gas_ratio >= self.params["min_fee_to_gas"]
        ):
            amount = snapshot.capital.total_capital_usd * min(
                self.params["max_position_perc_of_capital"],
                0.1 + pf.relative_apy_rank * 0.2,
            )
            base_action = Action.LONG
            base_target = best_pool
            base_order = {"side": "BUY", "price": None, "amount_usd": amount}
            base_conf = 0.6
        elif (
            pf.relative_apy_rank <= self.params["exit_relative_apy"]
            or pf.tvl_outflow_rate > 0.05
        ):
            amount = snapshot.capital.utilized_capital_usd * 0.2
            base_action = Action.SHORT
            base_target = best_pool
            base_order = {"side": "SELL", "price": None, "amount_usd": amount}
            base_conf = 0.5
        else:
            base_action = Action.HOLD
            base_target = None
            base_order = {}
            base_conf = 0.0

        return base_action, base_target, base_order, base_conf


    # =========================
    # 规则 + ML 决策层
    # =========================
    def decide(self, snapshot: StrategySnapshot) -> Tuple[Action, Optional[str], Dict, float]:
        """
        返回 (action: Action, target_pool_id, order_params, confidence)

        - 先用规则层算一个 base_action
        - 再用 ML 做两层决策：
          A 线：强信号覆盖（NON-HOLD 且置信度高）
          B 线：趋势兜底试单（HOLD 概率虽然高，但趋势概率也不算太小 → 小仓位试单）
        """
        # 1) 规则层先算出一个 base 决策
        base_action, base_target, base_order, base_conf = self._rule_only_decide(snapshot)

        # 2) 如果没有 ML 或未训练好，直接返回规则决策
        if not self.ml_model or not getattr(self.ml_model, "is_fitted", False):
            print("[Decision] No ML model or not fitted; using rule-based decision.")
            return base_action, base_target, base_order, base_conf

        # 3) 调用 ML 模型（优先用 decide_with_meta，如果没有再兼容 predict）
        try:
            if hasattr(self.ml_model, "decide_with_meta"):
                meta = self.ml_model.decide_with_meta(snapshot)
            else:
                # 兼容老接口：predict(snapshot) → (label, conf) 或 "HOLD"
                pred = self.ml_model.predict(snapshot)
                if isinstance(pred, (tuple, list)) and len(pred) >= 2:
                    label, conf = pred[0], float(pred[1])
                else:
                    label, conf = str(pred), 1.0
                meta = {
                    "decision": label,
                    "raw_label": label,
                    "confidence": conf,
                    "probs": {str(label): conf},
                    "reason": "predict_fallback",
                }
        except Exception as e:
            print("ML predict failed, keeping rule-based decision:", e)
            return base_action, base_target, base_order, base_conf

        ml_action = meta.get("decision")
        raw_label = meta.get("raw_label", ml_action)
        ml_conf = float(meta.get("confidence", 0.0))
        probs = meta.get("probs", {}) or {}
        reason = meta.get("reason", "")

        # ===== 打印 ML 概率，方便调试 =====
        hold_p = float(probs.get("HOLD", 0.0))
        long_p = float(probs.get("LONG", 0.0))
        short_p = float(probs.get("SHORT", 0.0))
        print(
            f"[ML PROBS] HOLD={hold_p:.3f} LONG={long_p:.3f} SHORT={short_p:.3f}"
        )
        # ==================================

        # 打印 base vs ML 决策
        try:
            base_action_str = base_action.value if hasattr(base_action, "value") else str(base_action)
        except Exception:
            base_action_str = str(base_action)

        ml_action_str = ml_action.value if hasattr(ml_action, "value") else str(ml_action)
        print(
            f"[Decision] base_action={base_action_str} "
            f"ml_action={ml_action_str} ml_confidence={ml_conf:.3f} reason={reason}"
        )

        # 4) A 线：强信号覆盖 —— ML 直接给出 LONG/SHORT 且置信度足够高
        ml_conf_thr = self.params["ml_confidence_threshold"]

        def _is_hold(x) -> bool:
            try:
                if isinstance(x, Action):
                    return x == Action.HOLD
                return str(x).upper() == "HOLD"
            except Exception:
                return False

        if not _is_hold(ml_action) and ml_conf >= ml_conf_thr:
            side = "BUY" if (ml_action == Action.LONG or str(ml_action).upper() == "LONG") else "SELL"
            amount = snapshot.capital.total_capital_usd * 0.05  # 强信号固定 5% 仓位
            chosen_action = (
                ml_action
                if isinstance(ml_action, Action)
                else (Action.LONG if str(ml_action).upper() == "LONG" else Action.SHORT)
            )
            chosen_order = {"side": side, "price": None, "amount_usd": amount}
            print(
                f"[Decision] ML strong override: final_action={ml_action_str} "
                f"final_conf={ml_conf:.3f}, amount_usd={amount:.2f}"
            )
            return chosen_action, None, chosen_order, ml_conf

        # 5) B 线：趋势兜底试单 —— ML 最终给的是 HOLD，但 LONG/SHORT 概率不算太低
        trend_p = max(long_p, short_p)
        trend_label = "LONG" if long_p >= short_p else "SHORT"

        thr_trend = self.params["ml_trend_try_threshold"]
        thr_gap = self.params["ml_trend_min_gap"]
        pos_frac = self.params["ml_trend_position_fraction"]

        # 条件解释：
        # - trend_p >= thr_trend：趋势方向本身概率不能太小（Debug 模式下仅需 >= 2%）
        # - hold_p - trend_p <= thr_gap：当前基本取消 gap 限制（=1.0），更多为了验证链路
        if trend_p >= thr_trend and (hold_p - trend_p) <= thr_gap:
            side = "BUY" if trend_label == "LONG" else "SELL"
            amount = snapshot.capital.total_capital_usd * pos_frac
            chosen_action = Action.LONG if trend_label == "LONG" else Action.SHORT
            chosen_order = {"side": side, "price": None, "amount_usd": amount}
            print(
                f"[Decision] ML trend-try override: trend={trend_label} "
                f"trend_p={trend_p:.3f} hold_p={hold_p:.3f} amount_usd={amount:.2f}"
            )
            return chosen_action, None, chosen_order, trend_p

        # 6) 都没触发，就老老实实用规则决策
        print("[Decision] ML did not override; keeping rule-based decision.")
        return base_action, base_target, base_order, base_conf
