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

# Try importing Kaggle hub for downloading datasets
try:
    KAGGLE_AVAILABLE = True
except ImportError:
    KAGGLE_AVAILABLE = False
    print("Warning: kagglehub not available, will use local datasets only")

os.makedirs("models", exist_ok=True)
os.makedirs("datasets", exist_ok=True)


def prepare_mooc_data(file_path: str = None, auto_download: bool = True) -> pd.DataFrame:
    if file_path is None:
        file_path = "datasets/kddcup_train_log.csv"

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

    if len(df) < 50:
        print(f"Warning: insufficient data for training ({len(df)} records)")
        print("  Recommended minimum is 100-200 records for good quality")

    print(f"\nTotal records for training: {len(df)}")

    feature_cols = ['durationMs', 'watchPercent', 'step']

    print(f"  Training features: {feature_cols}")

    X = df[feature_cols].fillna(0)

    X['durationMs'] = X['durationMs'] / 1000.0

    y_dropout = df['dropout'].fillna(0).astype(int)
    y_difficulty = df['difficulty'].fillna(1).astype(int)

    print(f"Dropout rate: {y_dropout.mean():.2%}")
    print(f"Difficulty distribution: {y_difficulty.value_counts().to_dict()}")

    models = {}
    print("\nTraining dropout prediction model...")
    dropout_model = xgb.XGBClassifier(
        objective='binary:logistic',
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42
    )
    dropout_model.fit(X, y_dropout)
    models['dropout'] = dropout_model
    print(f"Dropout model accuracy: {dropout_model.score(X, y_dropout):.2%}")

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
                model_path = f"models/{name}_predictor.onnx"
                with open(model_path, "wb") as f:
                    f.write(onnx_model.SerializeToString())
                print(f"✓ {name} model saved to {model_path} (ONNX)")
                onnx_success = True
            except Exception as e:
                print(f"✗ Error exporting {name} model to ONNX: {e}")

        pickle_path = f"models/{name}_predictor.pkl"
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
        default="datasets/kddcup_train_log.csv",
        help="Path to the public MOOC dataset file"
    )

    args = parser.parse_args()

    train_models(
        mooc_file=args.mooc_data,
        auto_download=True  # Automatically download dataset from Kaggle
    )
