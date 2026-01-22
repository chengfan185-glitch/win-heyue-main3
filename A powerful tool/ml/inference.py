# ml/inference.py
"""
MLDecisionModel: 带“趋势兜底”的三分类决策器

对外接口：
- MLDecisionModel.load(path)          → 返回实例
- ml_model.decide(snapshot)           → 返回 "HOLD" / "LONG" / "SHORT"
- ml_model.decide_with_meta(snapshot) → 返回 dict（包含概率、reason）
- ml_model.predict(features)          → 兼容旧版 CEX-ML-FEATS 调用（snake_case）
- ml_model.predict_proba(features)    → 兼容 runner 的 ML Gate / ML Bonus（返回 dict 概率）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import joblib
import pandas as pd

MODEL_PATH = "ml_decision_model.joblib"

# 默认 6 特征（CamelCase）——如果模型包里没有 feature 列信息，就用这个兜底
DEFAULT_FEATURES: List[str] = [
    "priceChange5m",
    "volumeChange5m",
    "volatility5m",
    "priceChange15m",
    "volumeChange15m",
    "volatility15m",
]


# =========================
# 通用小工具：把对象变成 dict
# =========================
def _ensure_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj

    # Pydantic v1
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except TypeError:
            return obj.dict(by_alias=False)

    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except TypeError:
            return obj.model_dump(by_alias=False)

    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)

    return {}


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _extract_features_from_snapshot(snapshot: Any, feature_names: List[str]) -> Dict[str, float]:
    """
    从 snapshot.market.cexFeatures 抽取特征，并按训练时的列顺序输出。
    snapshot 可以是 StrategySnapshot 对象或 dict。
    """
    snap = _ensure_dict(snapshot)
    market = _ensure_dict(snap.get("market", {}) or {})
    cex = _ensure_dict(market.get("cexFeatures", {}) or {})

    # 训练特征是 CamelCase
    feats = {
        "priceChange5m": _to_float(cex.get("priceChange5m", 0.0)),
        "volumeChange5m": _to_float(cex.get("volumeChange5m", 0.0)),
        "volatility5m": _to_float(cex.get("volatility5m", 0.0)),
        "priceChange15m": _to_float(cex.get("priceChange15m", 0.0)),
        "volumeChange15m": _to_float(cex.get("volumeChange15m", 0.0)),
        "volatility15m": _to_float(cex.get("volatility15m", 0.0)),
    }

    # 只返回模型真正用到的列
    return {name: _to_float(feats.get(name, 0.0)) for name in feature_names}


def rule_gate(snapshot: Any) -> bool:
    """
    Rule Gate：目前调试阶段全部放行。
    如需再加一层简单规则过滤，可以在这里做。
    """
    return True


class MLDecisionModel:
    """
    带“趋势兜底”的三分类决策模型封装。
    """

    def __init__(self, model_path: str = MODEL_PATH, min_confidence: float = 0.35):
        pack = joblib.load(model_path)
        self.model, self.label_encoder, self.features = self._unpack_model_pack(pack)
        self.min_confidence = float(min_confidence)

        # 兜底：features 为空时，用默认 6 列
        if not self.features:
            self.features = DEFAULT_FEATURES.copy()

    # 兼容 runner 里写的 MLDecisionModel.load(path)
    @classmethod
    def load(
        cls,
        model_path: str = MODEL_PATH,
        min_confidence: float = 0.50,
    ) -> "MLDecisionModel":
        return cls(model_path=model_path, min_confidence=min_confidence)

    @property
    def is_fitted(self) -> bool:
        """
        兼容旧代码使用的属性：
        - DecisionEngine 里会用 self.ml_model.is_fitted 判断模型是否可用
        - 简单认为只要模型成功加载，这里就返回 True
        """
        return hasattr(self, "model") and self.model is not None

    # =========================
    # runner 需要的接口：predict_proba(features)->dict
    # features 是 snake_case（来自你的 cex_features）
    # =========================
    def predict_proba(self, features: Dict[str, Any]) -> Dict[str, float]:
        """
        输入（snake_case）:
        {
          "price_change_5m": ...,
          "volume_change_5m": ...,
          "volatility_5m": ...,
          "price_change_15m": ...,
          "volume_change_15m": ...,
          "volatility_15m": ...
        }

        输出（dict-like）:
        {"HOLD":p, "LONG":p, "SHORT":p}
        """
        feats = features or {}

        mapped = {
            "priceChange5m": _to_float(feats.get("price_change_5m", 0.0)),
            "volumeChange5m": _to_float(feats.get("volume_change_5m", 0.0)),
            "volatility5m": _to_float(feats.get("volatility_5m", 0.0)),
            "priceChange15m": _to_float(feats.get("price_change_15m", 0.0)),
            "volumeChange15m": _to_float(feats.get("volume_change_15m", 0.0)),
            "volatility15m": _to_float(feats.get("volatility_15m", 0.0)),
        }

        X = pd.DataFrame([mapped], columns=self.features)

        try:
            proba = self.model.predict_proba(X)[0]
        except Exception:
            # 模型不支持 predict_proba，就给空 dict（上层用 fail-open/降级策略）
            return {"HOLD": 0.0, "LONG": 0.0, "SHORT": 0.0}

        labels = self._classes()

        # 尝试对齐长度
        if len(labels) != len(proba):
            if hasattr(self.model, "classes_"):
                try:
                    labels = [str(x) for x in list(self.model.classes_)]
                except Exception:
                    labels = ["HOLD", "LONG", "SHORT"]

        prob_map = {str(lbl).upper(): float(p) for lbl, p in zip(labels, proba)}

        # 统一输出键
        return {
            "HOLD": float(prob_map.get("HOLD", 0.0)),
            "LONG": float(prob_map.get("LONG", 0.0)),
            "SHORT": float(prob_map.get("SHORT", 0.0)),
        }

    # =========================
    # 旧版 CEX-ML-FEATS 接口：predict()->(decision, confidence)
    # =========================
    def predict(self, features: Dict[str, Any]) -> Tuple[str, float]:
        prob_map = self.predict_proba(features)
        best_label = max(prob_map, key=prob_map.get)
        best_prob = float(prob_map[best_label])

        # 低置信度 或 预测非 LONG/SHORT → 一律当 HOLD
        if best_label not in ("LONG", "SHORT") or best_prob < self.min_confidence:
            return "HOLD", best_prob
        return best_label, best_prob

    # =========================
    # snapshot → 概率
    # =========================
    def _predict_proba_from_snapshot(self, snapshot: Any) -> Tuple[Dict[str, float], str, float]:
        feat_dict = _extract_features_from_snapshot(snapshot, self.features)
        X = pd.DataFrame([feat_dict], columns=self.features)

        try:
            proba = self.model.predict_proba(X)[0]
        except Exception:
            # 模型不支持 predict_proba 就当 HOLD
            prob_map = {"HOLD": 1.0, "LONG": 0.0, "SHORT": 0.0}
            return prob_map, "HOLD", 1.0

        labels = self._classes()

        if len(labels) != len(proba):
            if hasattr(self.model, "classes_"):
                try:
                    labels = [str(x) for x in list(self.model.classes_)]
                except Exception:
                    labels = ["HOLD", "LONG", "SHORT"]

        prob_map = {str(lbl).upper(): float(p) for lbl, p in zip(labels, proba)}
        # 统一键
        norm = {
            "HOLD": float(prob_map.get("HOLD", 0.0)),
            "LONG": float(prob_map.get("LONG", 0.0)),
            "SHORT": float(prob_map.get("SHORT", 0.0)),
        }
        best_label = max(norm, key=norm.get)
        best_prob = float(norm[best_label])
        return norm, best_label, best_prob

    # =========================
    # snapshot → 决策 + meta 信息
    # =========================
    def decide_with_meta(self, snapshot: Any) -> Dict[str, Any]:
        # 0) Gate（目前全部放行，但保留结构）
        if not rule_gate(snapshot):
            return {
                "decision": "HOLD",
                "raw_label": "HOLD",
                "confidence": 1.0,
                "probs": {"HOLD": 1.0, "LONG": 0.0, "SHORT": 0.0},
                "reason": "rule_gate_hold",
            }

        # 1) 模型预测 + 概率
        prob_map, best_label, best_prob = self._predict_proba_from_snapshot(snapshot)

        decision = best_label
        reason = "ml_label"

        if best_label not in ("LONG", "SHORT") or best_prob < self.min_confidence:
            decision = "HOLD"
            reason = "low_confidence_or_hold"

        # 2) 趋势兜底逻辑（只在最终 HOLD 时触发）
        snap = _ensure_dict(snapshot)
        market = _ensure_dict(snap.get("market", {}) or {})
        cex = _ensure_dict(market.get("cexFeatures", {}) or {})

        p15 = _to_float(cex.get("priceChange15m", 0.0))
        v15 = _to_float(cex.get("volumeChange15m", 0.0))

        # 阈值：你原来写的是 0.0004 / 0.25（继续沿用）
        if decision == "HOLD" and abs(p15) > 0.0004 and abs(v15) > 0.25:
            if p15 > 0:
                decision = "LONG"
            elif p15 < 0:
                decision = "SHORT"

            if best_prob < 0.55:
                best_prob = 0.55
            reason = "trend_override_15m"

        return {
            "decision": decision,
            "raw_label": best_label,
            "confidence": float(best_prob),
            "probs": prob_map,
            "reason": reason,
        }

    def decide(self, snapshot: Any) -> str:
        result = self.decide_with_meta(snapshot)
        return str(result["decision"])

    # =========================
    # pack 解包与 classes 兼容
    # =========================
    def _unpack_model_pack(self, pack: Any):
        """Support multiple serialization formats.

        Supported:
        - dict with keys: model, label_encoder, features (or common aliases)
        - sklearn estimator/pipeline object with predict_proba/classes_
        """
        model = None
        label_encoder = None
        features = None

        if isinstance(pack, dict):
            # model
            for k in ("model", "clf", "estimator", "pipeline"):
                if k in pack:
                    model = pack[k]
                    break
            if model is None and len(pack) == 1:
                model = next(iter(pack.values()))

            # label encoder / classes mapping
            label_encoder = (
                pack.get("label_encoder")
                or pack.get("encoder")
                or pack.get("le")
                or pack.get("class_encoder")
            )

            # features
            features = (
                pack.get("features")
                or pack.get("feature_names")
                or pack.get("feature_columns")
                or pack.get("columns")
            )

            # If pack stores classes directly
            if label_encoder is None and "classes" in pack:
                label_encoder = {"classes": list(pack["classes"])}

        else:
            # estimator object
            model = pack
            # features
            features = getattr(pack, "feature_names_in_", None)
            if features is not None:
                try:
                    features = list(features)
                except Exception:
                    features = None

        # Build minimal label_encoder if still missing
        if label_encoder is None and model is not None:
            classes = getattr(model, "classes_", None)
            if classes is not None:
                try:
                    classes = list(classes)
                except Exception:
                    pass
                label_encoder = {"classes": classes}

        # Normalize features
        if features is None:
            features = []
        if isinstance(features, tuple):
            features = list(features)

        return model, label_encoder, list(features)

    def _classes(self) -> List[str]:
        le = getattr(self, "label_encoder", None)
        if le is None:
            return ["HOLD", "LONG", "SHORT"]
        if isinstance(le, dict) and "classes" in le:
            try:
                return [str(x) for x in list(le["classes"])]
            except Exception:
                return ["HOLD", "LONG", "SHORT"]
        if hasattr(le, "classes_"):
            try:
                return [str(x) for x in list(le.classes_)]
            except Exception:
                return ["HOLD", "LONG", "SHORT"]
        return ["HOLD", "LONG", "SHORT"]
