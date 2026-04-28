"""
Unit tests for DKT (Deep Knowledge Tracing) inference logic.
"""
import json
import numpy as np
import pytest

from app.dkt import DKTPredictor, _sigmoid


class TestSigmoid:

    def test_zero_input_gives_half(self):
        result = _sigmoid(np.array([0.0]))
        assert float(result[0]) == pytest.approx(0.5)

    def test_large_positive_clipped_to_one(self):
        # x=100 → clipped to 30 → sigmoid(30) ≈ 1.0
        result = _sigmoid(np.array([100.0]))
        assert float(result[0]) == pytest.approx(1.0, abs=1e-6)

    def test_large_negative_clipped_to_zero(self):
        result = _sigmoid(np.array([-100.0]))
        assert float(result[0]) == pytest.approx(0.0, abs=1e-6)

    def test_output_in_0_1_range(self):
        xs = np.linspace(-50, 50, 100)
        ys = _sigmoid(xs)
        assert np.all(ys >= 0.0)
        assert np.all(ys <= 1.0)

    def test_monotonically_increasing(self):
        xs = np.array([-5.0, -1.0, 0.0, 1.0, 5.0])
        ys = _sigmoid(xs)
        assert list(ys) == sorted(ys)


def _make_weights(num_skills: int, hidden_size: int) -> dict:
    """Construct minimal random LSTM weights for shape consistency."""
    rng = np.random.RandomState(42)
    input_size = 2 * num_skills
    return {
        "Wi": rng.randn(hidden_size, input_size).astype(np.float32),
        "Ri": rng.randn(hidden_size, hidden_size).astype(np.float32),
        "bi": np.zeros(hidden_size, dtype=np.float32),
        "Wf": rng.randn(hidden_size, input_size).astype(np.float32),
        "Rf": rng.randn(hidden_size, hidden_size).astype(np.float32),
        "bf": np.zeros(hidden_size, dtype=np.float32),
        "Wg": rng.randn(hidden_size, input_size).astype(np.float32),
        "Rg": rng.randn(hidden_size, hidden_size).astype(np.float32),
        "bg": np.zeros(hidden_size, dtype=np.float32),
        "Wo": rng.randn(hidden_size, input_size).astype(np.float32),
        "Ro": rng.randn(hidden_size, hidden_size).astype(np.float32),
        "bo": np.zeros(hidden_size, dtype=np.float32),
        "W_out": rng.randn(num_skills, hidden_size).astype(np.float32),
        "b_out": np.zeros(num_skills, dtype=np.float32),
    }


def _make_predictor(num_skills: int = 3, hidden_size: int = 8) -> DKTPredictor:
    cids = [100, 200, 300, 400, 500]
    concept2idx = {cids[i]: i for i in range(num_skills)}
    return DKTPredictor(_make_weights(num_skills, hidden_size), concept2idx, hidden_size)


class TestDKTPredict:

    def test_returns_none_when_history_too_short(self):
        predictor = _make_predictor()
        # 1 attempt → sequence length 1 < MIN_HISTORY_STEPS=2 → None
        stats = {100: (1, 1)}
        assert predictor.predict(stats) is None

    def test_returns_none_when_no_known_concepts(self):
        predictor = _make_predictor()
        # All concept IDs unknown to the model
        stats = {999: (5, 3), 888: (4, 2)}
        assert predictor.predict(stats) is None

    def test_returns_none_when_all_attempts_zero(self):
        predictor = _make_predictor()
        stats = {100: (0, 0), 200: (0, 0)}
        assert predictor.predict(stats) is None

    def test_returns_dict_for_sufficient_history(self):
        predictor = _make_predictor()
        # 3 + 2 = 5 steps ≥ MIN_HISTORY_STEPS
        stats = {100: (3, 2), 200: (2, 1)}
        result = predictor.predict(stats)
        assert result is not None
        assert isinstance(result, dict)

    def test_output_keys_are_concept_ids(self):
        predictor = _make_predictor(num_skills=3)
        stats = {100: (3, 2), 200: (2, 1)}
        result = predictor.predict(stats)
        assert result is not None
        # All keys are valid concept IDs from concept2idx
        assert all(k in {100, 200, 300} for k in result.keys())

    def test_output_probabilities_in_0_1(self):
        predictor = _make_predictor()
        stats = {100: (5, 3), 200: (4, 2), 300: (3, 1)}
        result = predictor.predict(stats)
        assert result is not None
        for cid, prob in result.items():
            assert 0.0 <= prob <= 1.0, f"P({cid})={prob} out of [0,1]"

    def test_skips_unknown_concepts_in_stats(self):
        predictor = _make_predictor()
        # 999 is not in concept2idx — should be silently ignored
        # 100 and 200 together contribute enough steps
        stats = {100: (3, 2), 999: (10, 9)}
        result = predictor.predict(stats)
        assert result is not None
        assert 999 not in result

    def test_skips_zero_attempt_concepts(self):
        """Concepts with 0 attempts contribute nothing to the sequence."""
        predictor = _make_predictor()
        stats = {100: (0, 0), 200: (4, 2)}
        # Only concept 200 contributes: 4 steps ≥ MIN_HISTORY_STEPS
        result = predictor.predict(stats)
        assert result is not None

    def test_all_concepts_have_output(self):
        """Predictor outputs P(correct) for every concept in concept2idx, not just seen ones."""
        predictor = _make_predictor(num_skills=3)
        stats = {100: (5, 3)}  # only concept 100 seen, but output covers all 3
        result = predictor.predict(stats)
        assert result is not None
        assert len(result) == 3

    def test_min_history_boundary(self):
        """Exactly MIN_HISTORY_STEPS steps → should return result, not None."""
        predictor = _make_predictor()
        # MIN_HISTORY_STEPS=2: need exactly 2 sequence entries
        # concept 100: (2, 2) → 2 correct → 2 steps
        stats = {100: (2, 2)}
        result = predictor.predict(stats)
        assert result is not None

    def test_one_below_min_history_returns_none(self):
        predictor = _make_predictor()
        # MIN_HISTORY_STEPS=2: 1 step → None
        stats = {100: (1, 0)}
        assert predictor.predict(stats) is None


class TestDKTLoad:

    def test_returns_none_when_weights_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.dkt.MODEL_DIR", tmp_path)
        assert DKTPredictor.load(course_id=999) is None

    def test_returns_none_when_map_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.dkt.MODEL_DIR", tmp_path)
        # Create weights file but no map file
        W = _make_weights(2, 4)
        np.savez(tmp_path / "dkt_weights_1.npz", **W)
        assert DKTPredictor.load(course_id=1) is None

    def test_returns_none_for_corrupt_weights(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.dkt.MODEL_DIR", tmp_path)
        (tmp_path / "dkt_weights_1.npz").write_bytes(b"not a valid npz")
        map_data = {"concept2idx": {"100": 0}, "hidden_size": 4}
        (tmp_path / "dkt_skill_map_1.json").write_text(json.dumps(map_data))
        assert DKTPredictor.load(course_id=1) is None

    def test_loads_valid_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.dkt.MODEL_DIR", tmp_path)
        num_skills, hidden_size = 2, 4
        W = _make_weights(num_skills, hidden_size)
        np.savez(tmp_path / "dkt_weights_2.npz", **W)
        map_data = {"concept2idx": {"100": 0, "200": 1}, "hidden_size": hidden_size}
        (tmp_path / "dkt_skill_map_2.json").write_text(json.dumps(map_data))

        predictor = DKTPredictor.load(course_id=2)
        assert predictor is not None
        assert predictor._num_skills == 2
        assert predictor._hidden_size == 4
        assert predictor._concept2idx == {100: 0, 200: 1}

    def test_loaded_predictor_can_predict(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.dkt.MODEL_DIR", tmp_path)
        num_skills, hidden_size = 2, 8
        W = _make_weights(num_skills, hidden_size)
        np.savez(tmp_path / "dkt_weights_3.npz", **W)
        map_data = {"concept2idx": {"100": 0, "200": 1}, "hidden_size": hidden_size}
        (tmp_path / "dkt_skill_map_3.json").write_text(json.dumps(map_data))

        predictor = DKTPredictor.load(course_id=3)
        assert predictor is not None
        result = predictor.predict({100: (5, 3), 200: (4, 2)})
        assert result is not None
        assert set(result.keys()) == {100, 200}
