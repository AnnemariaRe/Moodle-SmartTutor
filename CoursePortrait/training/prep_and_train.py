import pandas as pd
import numpy as np
import xgboost as xgb
import os
from pathlib import Path
import pickle
from prepare_kdd_dataset import prepare_kdd_dataset

# Try importing ONNX converters
try:
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("Warning: skl2onnx not available, models will be saved as pickle")

BASE_DIR = Path(__file__).resolve().parent.parent
os.makedirs(BASE_DIR / "models", exist_ok=True)
os.makedirs(BASE_DIR / "datasets", exist_ok=True)


def prepare_mooc_data(file_path: str = None, auto_download: bool = True) -> pd.DataFrame:
    if file_path is None:
        file_path = str(BASE_DIR / "datasets/kddcup_train_log.csv")

    if file_path and os.path.exists(file_path):
        print(f"Loading data from {file_path}...")
        df = pd.read_csv(file_path)

        if 'durationMs' not in df.columns:
            df['durationMs'] = df.get('time_diff', np.random.randint(10000, 300000, len(df))).astype(float)

        if 'watchPercent' not in df.columns:
            df['watchPercent'] = (df.get('video_events', np.random.random(len(df))) /
                                 df.get('total_events', np.random.randint(1, 100, len(df)))).clip(0, 1)

        if 'dropout' not in df.columns:
            df['dropout'] = (df.get('next_event', pd.Series([None] * len(df))).isna()).astype(int)

        if 'step' not in df.columns:
            df['step'] = 1

        print(f"  Loaded {len(df)} records")
    else:
        raise FileNotFoundError(f"File {file_path} not found")

    if 'difficulty' not in df.columns and 'watchPercent' in df.columns:
        df['difficulty'] = pd.cut(
            df['watchPercent'],
            bins=[0, 0.3, 0.7, 1.0],
            labels=[2, 1, 0]  # 2=hard, 1=medium, 0=easy
        ).astype(int)
    elif 'difficulty' not in df.columns:
        df['difficulty'] = df['dropout'].map({0: 0, 1: 2})  # 0=easy, 2=hard

    return df


def _plot_evaluation(model, X_test, y_test, y_pred, y_prob,
                     roc_auc, f1, precision, recall,
                     feature_cols, df_full, y_full):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import seaborn as sns
        from sklearn.metrics import roc_curve, precision_recall_curve
    except ImportError:
        print("  (matplotlib/seaborn не установлены, графики пропущены)")
        return

    sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    fig.suptitle("Dropout Risk Predictor — Evaluation", fontsize=15, fontweight="bold", y=1.01)

    # ── 1. ROC curve ────────────────────────────────────────────────────────
    ax = axes[0, 0]
    if y_test.nunique() == 2:
        fpr, tpr, _ = roc_curve(y_test, y_prob)
        ax.plot(fpr, tpr, color="#4c78a8", lw=2, label=f"ROC (AUC = {roc_auc:.3f})")
        ax.plot([0, 1], [0, 1], "--", color="#bbb", lw=1, label="Random (AUC = 0.5)")
        ax.fill_between(fpr, tpr, alpha=0.08, color="#4c78a8")
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_title("ROC Curve")
        ax.legend(loc="lower right")
        ax.grid(False) 
    else:
        ax.text(0.5, 0.5, "Недостаточно\nклассов в тесте",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("ROC Curve")

    # ── 2. Precision-Recall curve ────────────────────────────────────────────
    ax = axes[0, 1]
    if y_test.nunique() == 2:
        prec_vals, rec_vals, _ = precision_recall_curve(y_test, y_prob)
        baseline = y_test.mean()
        ax.plot(rec_vals, prec_vals, color="#f58518", lw=2,
                label=f"P-R curve (F1={f1:.3f})")
        ax.axhline(baseline, linestyle="--", color="#bbb", lw=1,
                   label=f"Baseline (random) = {baseline:.3f}")
        ax.fill_between(rec_vals, prec_vals, alpha=0.08, color="#f58518")
        ax.set_xlabel("Recall")
        ax.set_ylabel("Precision")
        ax.set_title("Precision-Recall Curve")
        ax.legend(loc="upper right")
        ax.grid(False) 
    else:
        ax.text(0.5, 0.5, "Недостаточно\nклассов в тесте",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Precision-Recall Curve")

    # ── 3. Confusion matrix ──────────────────────────────────────────────────
    ax = axes[1, 0]
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(y_test, y_pred)
    labels = ["Не отвал\n(0)", "Отвал\n(1)"]
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=labels, yticklabels=labels,
        linewidths=0.5, linecolor="#ddd", ax=ax,
        annot_kws={"size": 14, "weight": "bold"},
    )
    ax.set_xlabel("Предсказание")
    ax.set_ylabel("Факт")
    ax.set_title("Confusion Matrix (тестовая выборка)")

    # ── 4. Feature importance ────────────────────────────────────────────────
    ax = axes[1, 1]
    importances = model.feature_importances_
    names = ["duration\n(сек)", "watch\nPercent", "step\n(порядок)"]
    colors = ["#4c78a8", "#f58518", "#54a24b"]
    bars = ax.barh(names, importances, color=colors, edgecolor="white", height=0.5)
    ax.set_xlabel("Feature Importance (gain)")
    ax.set_title("Важность признаков")
    ax.set_xlim(0, max(importances) * 1.25)
    for bar, val in zip(bars, importances):
        ax.text(val + 0.005, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=11)

    # ── Metrics summary strip ────────────────────────────────────────────────
    metrics_text = (
        f"Train: {len(X_test) * 4}   Test: {len(X_test)}   "
        f"Dropout rate: {y_full.mean():.1%}   "
        f"Accuracy: {(y_pred == y_test).mean():.3f}   "
        f"ROC-AUC: {roc_auc:.3f}   F1: {f1:.3f}   "
        f"Precision: {precision:.3f}   Recall: {recall:.3f}"
    )
    fig.text(0.5, -0.01, metrics_text, ha="center", fontsize=9, color="#555")

    plt.tight_layout()
    out_path = str(BASE_DIR / "models/dropout_eval.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  📊 Графики сохранены: {out_path}")


def train_models(
    mooc_file: str = "datasets/kddcup_train_log.csv",
    auto_download: bool = True
):
    """
    Train XGBoost models and export to ONNX format using MOOC data.
    Automatically downloads the KDD Cup 2015 dataset from Kaggle if the local file is not found.
    """
    print("Training ML models for Course Portrait Service")
    print()

    # Load MOOC data
    df = prepare_mooc_data(mooc_file, auto_download=auto_download)

    if len(df) == 0:
        print("Error: no data found for training!")
        print("The dataset will be automatically downloaded from Kaggle on the next run.")
        return None

    # If too much data, use a sample to speed up training
    if len(df) > 100000:
        print(f"Large dataset ({len(df)} records), using 10% sample to speed up training...")
        df = df.sample(frac=0.1, random_state=42)

    print(f"\nTotal records for training: {len(df)}")

    feature_cols = ['durationMs', 'watchPercent', 'step']

    print(f"  Training features: {feature_cols}")

    X = df[feature_cols].fillna(0)

    X['durationMs'] = X['durationMs'] / 1000.0

    y_dropout = df['dropout'].fillna(0).astype(int)
    y_difficulty = df['difficulty'].fillna(1).astype(int)

    print(f"Dropout rate: {y_dropout.mean():.2%}")
    print(f"Difficulty distribution: {y_difficulty.value_counts().to_dict()}")

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        accuracy_score, roc_auc_score, f1_score,
        precision_score, recall_score, confusion_matrix,
        classification_report,
    )

    test_size = 0.2 if len(df) >= 100 else 0.0
    if test_size > 0:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_dropout, test_size=test_size, random_state=42, stratify=y_dropout
        )
    else:
        X_train, X_test, y_train, y_test = X, X, y_dropout, y_dropout

    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    scale_pos_weight = round(n_neg / n_pos, 1) if n_pos > 0 else 1.0
    print(f"  scale_pos_weight = {scale_pos_weight} (neg={n_neg}, pos={n_pos})")

    models = {}
    dropout_model = xgb.XGBClassifier(
        objective='binary:logistic',
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=42
    )
    dropout_model.fit(X_train, y_train)
    models['dropout'] = dropout_model

    # Evaluation
    y_pred = dropout_model.predict(X_test)
    y_prob = dropout_model.predict_proba(X_test)[:, 1]

    acc       = accuracy_score(y_test, y_pred)
    f1        = f1_score(y_test, y_pred, zero_division=0)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall    = recall_score(y_test, y_pred, zero_division=0)
    try:
        roc_auc = roc_auc_score(y_test, y_prob)
    except ValueError:
        roc_auc = float('nan')
    cm = confusion_matrix(y_test, y_pred)

    _plot_evaluation(
        dropout_model, X_test, y_test, y_pred, y_prob,
        roc_auc, f1, precision, recall,
        feature_cols, df, y_dropout,
    )

    # 2. Difficulty Predictor
    print("\nTraining difficulty prediction model...")
    difficulty_model = xgb.XGBClassifier(
        objective='multi:softprob',
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        num_class=3,
        random_state=42
    )
    difficulty_model.fit(X, y_difficulty)
    models['difficulty'] = difficulty_model
    print(f"Difficulty model accuracy: {difficulty_model.score(X, y_difficulty):.2%}")

    print("\nExporting models...")
    initial_type = [('input', FloatTensorType([None, len(feature_cols)]))] if ONNX_AVAILABLE else None

    for name, model in models.items():
        onnx_success = False
        if ONNX_AVAILABLE:
            try:
                onnx_model = convert_sklearn(
                    model,
                    initial_types=initial_type,
                    target_opset=12
                )
                model_path = str(BASE_DIR / f"models/{name}_predictor.onnx")
                with open(model_path, "wb") as f:
                    f.write(onnx_model.SerializeToString())
                print(f"✓ {name} model saved to {model_path} (ONNX)")
                onnx_success = True
            except Exception as e:
                print(f"✗ Error exporting {name} model to ONNX: {e}")

        pickle_path = str(BASE_DIR / f"models/{name}_predictor.pkl")
        with open(pickle_path, "wb") as f:
            pickle.dump(model, f)
        if not onnx_success:
            print(f"✓ {name} model saved to {pickle_path} (pickle)")
        else:
            print(f"  Also saved as pickle: {pickle_path}")

    print("\nTraining complete!")
    return models


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Train ML models for Course Portrait Service",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--mooc-data",
        default=str(BASE_DIR / "datasets/kddcup_train_log.csv"),
        help="Path to the public MOOC dataset file"
    )

    args = parser.parse_args()

    train_models(
        mooc_file=args.mooc_data,
        auto_download=True
    )
