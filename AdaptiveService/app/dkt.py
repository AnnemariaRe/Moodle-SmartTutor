from __future__ import annotations

import json
import logging
import pathlib

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = pathlib.Path("models")
MIN_HISTORY_STEPS = 2


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


class DKTPredictor:

    def __init__(self, weights: dict[str, np.ndarray], concept2idx: dict[int, int], hidden_size: int):
        self._W = weights
        self._concept2idx = concept2idx
        self._idx2concept = {v: k for k, v in concept2idx.items()}
        self._num_skills = len(concept2idx)
        self._hidden_size = hidden_size

    @classmethod
    def load(cls, course_id: int) -> DKTPredictor | None:
        """Load predictor for a course. Returns None if weights not found."""
        weights_path = MODEL_DIR / f"dkt_weights_{course_id}.npz"
        map_path = MODEL_DIR / f"dkt_skill_map_{course_id}.json"
        if not weights_path.exists() or not map_path.exists():
            return None
        try:
            W = dict(np.load(weights_path))
            with open(map_path) as f:
                meta = json.load(f)
            concept2idx = {int(k): v for k, v in meta["concept2idx"].items()}
            return cls(W, concept2idx, meta["hidden_size"])
        except Exception as exc:
            logger.warning("Failed to load DKT model for course %s: %s", course_id, exc)
            return None

    # LSTM math
    def _lstm_step(
        self, x: np.ndarray, h: np.ndarray, c: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        W = self._W
        i = _sigmoid(W["Wi"] @ x + W["Ri"] @ h + W["bi"])
        f = _sigmoid(W["Wf"] @ x + W["Rf"] @ h + W["bf"])
        g = np.tanh(W["Wg"] @ x + W["Rg"] @ h + W["bg"])
        o = _sigmoid(W["Wo"] @ x + W["Ro"] @ h + W["bo"])
        c_new = f * c + i * g
        h_new = o * np.tanh(c_new)
        return h_new, c_new

    def _run_lstm(self, sequence: list[tuple[int, int]]) -> np.ndarray:
        """Run LSTM over sequence, return final hidden state."""
        h = np.zeros(self._hidden_size)
        c = np.zeros(self._hidden_size)
        for skill_idx, correct in sequence:
            x = np.zeros(2 * self._num_skills)
            x[skill_idx * 2 + correct] = 1.0
            h, c = self._lstm_step(x, h, c)
        return h

    def _output(self, h: np.ndarray) -> np.ndarray:
        """P(correct) for all skills from hidden state."""
        return _sigmoid(self._W["W_out"] @ h + self._W["b_out"])

    # Public API
    def predict(
        self,
        stats_map: dict[int, tuple[int, int]],
    ) -> dict[int, float] | None:
        # Build pseudo-sequence from aggregate stats
        sequence: list[tuple[int, int]] = []
        for concept_id, (attempts, correct) in stats_map.items():
            skill_idx = self._concept2idx.get(concept_id)
            if skill_idx is None or attempts == 0:
                continue
            fails = attempts - correct
            sequence.extend([(skill_idx, 1)] * correct)
            sequence.extend([(skill_idx, 0)] * fails)

        if len(sequence) < MIN_HISTORY_STEPS:
            logger.debug("DKT: history too short (%d steps), skipping", len(sequence))
            return None

        # Shuffle to avoid trivial ordering bias
        rng = np.random.RandomState(sum(concept_id for concept_id in stats_map))
        rng.shuffle(sequence)

        h = self._run_lstm(sequence)
        p_correct = self._output(h)

        return {
            self._idx2concept[idx]: float(p_correct[idx])
            for idx in range(self._num_skills)
        }


# Convenience function
def get_dkt_predictions(
    stats_map: dict[int, tuple[int, int]],
    course_id: int,
) -> dict[int, float] | None:
    predictor = DKTPredictor.load(course_id)
    if predictor is None:
        return None
    return predictor.predict(stats_map)
