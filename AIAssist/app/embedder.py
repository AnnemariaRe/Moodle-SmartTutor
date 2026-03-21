import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model: SentenceTransformer | None = None


def load_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model %s ...", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded.")
    return _model


def embed_batch(texts: List[str]) -> np.ndarray:
    return load_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)


def embed_one(text: str) -> np.ndarray:
    return embed_batch([text])[0]
