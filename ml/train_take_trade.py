# ml/train_take_trade.py
import os
import json
import joblib
import pandas as pd
import numpy as np

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, roc_auc_score, average_precision_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingClassifier

DATA_PATH_DEFAULT = "data/samples.csv"
MODEL_OUT_DEFAULT = "ml_decision_model.joblib"
META_OUT_DEFAULT = "ml_decision_model.meta.json"

# 你定义“值得出手”的阈值（跑赢手续费）
EDGE_THRESHOLD = 0.5  # percent

# 为了防止过度频繁交易：只执行 Top-K% 置信度信号
TOP_PCT = 0.08  # 取前 8% 作为出手候选（你可以改 0.05~0.15）


def load_samples(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if len(df) < 50:
        raise ValueError(f"样本太少：{len(df)}，至少建议 200+ 再做第一次稳定训练。")
    return df


def infer_label(df: pd.DataFrame) -> pd.Series:
    # 兼容字段名：你之前统计用的是 net_pnl_after_fee_pct
    if "net_pnl_after_fee_pct" not in df.columns:
        raise ValueError("缺字段 net_pnl_after_fee_pct。请确认 samples.csv 里是否有该列。")
    y = (df["net_pnl_after_fee_pct"].astype(float) >= EDGE_THRESHOLD).astype(int)
    return y


def pick_feature_cols(df: pd.DataFrame) -> list:
    # 自动选取数值特征列：排除明显的标签/泄露字段
    leak_cols = {
        "net_pnl_after_fee_pct", "pnlPct", "pnl", "profit", "label",
        "decision", "action", "createdAt", "timestamp", "time", "open_time", "close_time",
        "entry_price", "exit_price", "fee", "fee_pct"
    }
    cols = []
    for c in df.columns:
        if c in leak_cols:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    if len(cols) < 3:
        raise ValueError(f"可用数值特征列太少：{cols}")
    return cols


def train_and_eval(X: pd.DataFrame, y: pd.Series):
    # 模型管线：标准化 + GBDT
    clf = Pipeline(steps=[
        ("scaler", StandardScaler(with_mean=True, with_std=True)),
        ("model", HistGradientBoostingClassifier(
            max_depth=6,
            learning_rate=0.05,
            max_iter=400,
            l2_regularization=0.0,
            random_state=42
        ))
    ])

    # 时间序列切分（更贴近真实交易）
    tscv = TimeSeriesSplit(n_splits=5)

    oof_pred = np.zeros(len(X), dtype=float)
    for fold, (tr_idx, va_idx) in enumerate(tscv.split(X), start=1):
        X_tr, y_tr = X.iloc[tr_idx], y.iloc[tr_idx]
        X_va, y_va = X.iloc[va_idx], y.iloc[va_idx]

        clf.fit(X_tr, y_tr)
        proba = clf.predict_proba(X_va)[:, 1]
        oof_pred[va_idx] = proba

        # 每折简单看一下
        if y_va.nunique() > 1:
            auc = roc_auc_score(y_va, proba)
            ap = average_precision_score(y_va, proba)
        else:
            auc, ap = float("nan"), float("nan")
        print(f"[Fold {fold}] valid positives={int(y_va.sum())}/{len(y_va)}  ROC-AUC={auc:.4f}  AP={ap:.4f}")

    # 全局报告
    if y.nunique() > 1:
        auc_all = roc_auc_score(y, oof_pred)
        ap_all = average_precision_score(y, oof_pred)
    else:
        auc_all, ap_all = float("nan"), float("nan")

    print("\n===== OOF Overall =====")
    print(f"Positives: {int(y.sum())}/{len(y)} ({(y.mean()*100):.2f}%)")
    print(f"ROC-AUC: {auc_all:.4f}")
    print(f"PR-AUC(AP): {ap_all:.4f}")

    # 用 Top-PCT 做“出手门槛”
    cut = np.quantile(oof_pred, 1 - TOP_PCT)
    y_hat = (oof_pred >= cut).astype(int)

    print(f"\n===== Decision Gate (Top {int(TOP_PCT*100)}%) =====")
    print(classification_report(y, y_hat, digits=4))

    # 最后用全量拟合，输出模型
    clf.fit(X, y)
    return clf, {"roc_auc_oof": auc_all, "ap_oof": ap_all, "top_pct": TOP_PCT, "cut_oof": float(cut)}


def main():
    data_path = os.getenv("SAMPLES_PATH", DATA_PATH_DEFAULT)
    model_out = os.getenv("MODEL_OUT", MODEL_OUT_DEFAULT)
    meta_out = os.getenv("META_OUT", META_OUT_DEFAULT)

    df = load_samples(data_path)
    y = infer_label(df)
    feat_cols = pick_feature_cols(df)

    X = df[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    model, meta = train_and_eval(X, y)
    joblib.dump({"model": model, "feature_cols": feat_cols}, model_out)

    with open(meta_out, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("\n✅ Saved:")
    print(f"- model: {model_out}")
    print(f"- meta : {meta_out}")
    print(f"- features({len(feat_cols)}): {feat_cols[:10]}{'...' if len(feat_cols)>10 else ''}")


if __name__ == "__main__":
    main()
