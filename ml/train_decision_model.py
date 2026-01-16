# ml/train_decision_model.py
"""
训练三分类决策模型：HOLD / LONG / SHORT
使用 data/cases_auto_labeled.jsonl：
1）对 auto_rule 样本降权；
2）对类别做重采样：削弱 HOLD 数量；
3）对类别再加一层 class_weight，进一步放大 LONG/SHORT 影响力。
"""

import json
import random
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

DATA_PATH = "data/cases_auto_labeled.jsonl"
MODEL_PATH = "ml_decision_model.joblib"  # 和 inference 保持一致


def extract_features(row: dict) -> dict:
    """
    从 snapshot.market.cexFeatures 中抽取特征。
    缺失时用 0.0 兜底。
    """
    snapshot = row.get("snapshot", {})
    market = snapshot.get("market", {})
    cex = market.get("cexFeatures", {})

    def f(name: str) -> float:
        v = cex.get(name, 0.0)
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    return {
        "priceChange5m": f("priceChange5m"),
        "volumeChange5m": f("volumeChange5m"),
        "volatility5m": f("volatility5m"),
        "priceChange15m": f("priceChange15m"),
        "volumeChange15m": f("volumeChange15m"),
        "volatility15m": f("volatility15m"),
    }


def main():
    # 1) 读原始数据
    rows = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    # 1.1 按标签拆成三组，方便重采样
    hold_rows = []
    long_rows = []
    short_rows = []

    for r in rows:
        label = r.get("label")
        if label == "HOLD":
            hold_rows.append(r)
        elif label == "LONG":
            long_rows.append(r)
        elif label == "SHORT":
            short_rows.append(r)

    n_hold = len(hold_rows)
    n_long = len(long_rows)
    n_short = len(short_rows)

    print(f"[TRAIN] Raw label counts: HOLD={n_hold}, LONG={n_long}, SHORT={n_short}")

    if n_long + n_short == 0:
        print("[TRAIN] 没有 LONG/SHORT 样本，无法训练有用的模型。")
        return

    # 1.2 重采样：限制 HOLD 数量，不让它压死其它类别
    #    这里设置：HOLD 数量 <= 2 * (LONG+SHORT)
    total_ls = n_long + n_short
    max_hold = min(n_hold, 2 * total_ls)

    if n_hold > max_hold:
        hold_rows = random.sample(hold_rows, max_hold)

    # 组合训练集，并打乱顺序
    train_rows = hold_rows + long_rows + short_rows
    random.shuffle(train_rows)

    print(
        f"[TRAIN] After resample: HOLD={len(hold_rows)}, "
        f"LONG={len(long_rows)}, SHORT={len(short_rows)}, "
        f"Total={len(train_rows)}"
    )

    # 2) 抽取特征 / 标签 / 样本权重
    X_list = []
    y_list = []
    w_list = []

    for r in train_rows:
        label = r.get("label")
        if label not in ("HOLD", "LONG", "SHORT"):
            continue

        feats = extract_features(r)
        X_list.append(feats)
        y_list.append(label)

        source = r.get("source")
        # auto_rule 作为弱标签，进一步降权
        if source == "auto_rule":
            w_list.append(0.3)
        else:
            w_list.append(1.0)

    if not X_list:
        print("没有可用训练样本，检查数据文件:", DATA_PATH)
        return

    X = pd.DataFrame(X_list)

    # 3) 标签编码
    le = LabelEncoder()
    y_enc = le.fit_transform(y_list)

    # 3.1 类别权重：再对 HOLD 降权，对 LONG/SHORT 略微放大
    base_class_weight = {
        "HOLD": 0.3,   # HOLD 整体权重打到 0.3
        "LONG": 1.5,
        "SHORT": 1.5,
    }
    class_weight = {
        idx: base_class_weight.get(label, 1.0)
        for idx, label in enumerate(le.classes_)
    }

    print("[TRAIN] Label classes:", list(le.classes_))
    print("[TRAIN] Class weight (by index):", class_weight)

    # 4) 训练模型（稍微放宽模型容量，让它更容易捕捉多空信号）
    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=8,
        min_samples_leaf=5,
        random_state=42,
        class_weight=class_weight,
    )

    clf.fit(X, y_enc, sample_weight=w_list)

    # 5) 保存模型包
    model_pack = {
        "model": clf,
        "label_encoder": le,
        "features": list(X.columns),
    }

    joblib.dump(model_pack, MODEL_PATH)

    print(f"[TRAIN] Done. Saved model to: {MODEL_PATH}")
    print(f"[TRAIN] Classes: {list(le.classes_)}")
    print(f"[TRAIN] Feature columns: {list(X.columns)}")


if __name__ == "__main__":
    main()
