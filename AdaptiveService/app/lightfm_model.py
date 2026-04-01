from __future__ import annotations

import logging
import pathlib

import joblib
import numpy as np
from lightfm import LightFM

from app.lightfm_data import LightFMDataset

logger = logging.getLogger(__name__)

MODEL_DIR = pathlib.Path("models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MIN_INTERACTIONS = 10   # train only when we have meaningful data
DEFAULT_EPOCHS = 30


def model_path(course_id: int) -> pathlib.Path:
    return MODEL_DIR / f"lightfm_course_{course_id}.pkl"


def train_model(dataset: LightFMDataset, course_id: int, epochs: int = DEFAULT_EPOCHS) -> dict:
    """Train LightFM WARP model and persist to disk. Returns a status dict."""
    n_interactions = dataset.interactions.nnz
    if n_interactions < MIN_INTERACTIONS:
        msg = f"недостаточно данных ({n_interactions} взаимодействий, нужно ≥ {MIN_INTERACTIONS})"
        logger.warning("LightFM training skipped for course %s: %s", course_id, msg)
        return {"status": "skipped", "reason": msg}

    model = LightFM(
        loss="warp",
        no_components=32,
        learning_rate=0.05,
        item_alpha=1e-6,
        user_alpha=1e-6,
        random_state=42,
    )
    model.fit(
        interactions=dataset.interactions,
        user_features=dataset.user_features,
        item_features=dataset.item_features,
        epochs=epochs,
        num_threads=2,
        verbose=False,
    )

    joblib.dump({"model": model, "dataset": dataset}, model_path(course_id))

    n_users, n_items = dataset.interactions.shape
    logger.info(
        "LightFM trained: course=%s users=%d items=%d interactions=%d epochs=%d",
        course_id, n_users, n_items, n_interactions, epochs,
    )
    return {
        "status": "ok",
        "users": n_users,
        "items": n_items,
        "interactions": n_interactions,
        "epochs": epochs,
    }


def recommend(
    course_id: int,
    student_id: int,
    n: int = 3,
    exclude_known: bool = True,
) -> list[int] | None:
    path = model_path(course_id)
    if not path.exists():
        return None

    try:
        saved = joblib.load(path)
        model: LightFM = saved["model"]
        dataset: LightFMDataset = saved["dataset"]
    except Exception as exc:
        logger.warning("Failed to load LightFM model for course %s: %s", course_id, exc)
        return None

    user_idx = dataset.user_id_map.get(student_id)
    if user_idx is None:
        # Cold-start: student not seen during training
        return None

    n_items = dataset.interactions.shape[1]
    scores = model.predict(
        user_ids=user_idx,
        item_ids=np.arange(n_items),
        user_features=dataset.user_features,
        item_features=dataset.item_features,
    )

    if exclude_known:
        known_cols = dataset.interactions[user_idx].indices
        scores[known_cols] = -np.inf

    top_indices = np.argsort(-scores)

    idx_to_item_id = {v: k for k, v in dataset.item_id_map.items()}
    cmids: list[int] = []
    for idx in top_indices:
        if len(cmids) >= n:
            break
        if scores[idx] == -np.inf:
            break
        item_id = idx_to_item_id.get(int(idx))
        if item_id is not None:
            cmid = dataset.cmid_map.get(item_id)
            if cmid is not None:
                cmids.append(cmid)

    return cmids if cmids else None
