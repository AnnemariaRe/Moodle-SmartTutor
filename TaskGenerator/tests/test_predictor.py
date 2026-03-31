import pytest

from app.predictor import BKT, hybrid_bkt_recent


# ---------------------------------------------------------------------------
# BKT unit tests
# ---------------------------------------------------------------------------

def test_bkt_initial_knowledge():
    bkt = BKT(p_l0=0.3)
    assert bkt.knowledge == pytest.approx(0.3)


def test_bkt_update_wrong():
    """
    update(False) with default params, starting from p_l0=0.3:
        p_obs = 0.3*0.05 + 0.7*0.8 = 0.575
        posterior = 0.3*0.05 / 0.575 ≈ 0.02609
        knowledge  = 0.02609 + 0.97391*0.15 ≈ 0.17217
        p_correct  = 0.17217*0.95 + 0.82783*0.2 ≈ 0.329
    """
    bkt = BKT()
    p_correct = bkt.update(False)
    assert p_correct == pytest.approx(0.329, abs=0.005)
    # Knowledge drops after a wrong answer
    assert bkt.knowledge < 0.3


def test_bkt_update_correct():
    """
    update(True) with default params, starting from p_l0=0.3:
        p_obs = 0.3*0.95 + 0.7*0.2 = 0.425
        posterior = 0.3*0.95 / 0.425 ≈ 0.67059
        knowledge  = 0.67059 + 0.32941*0.15 ≈ 0.720
        p_correct  = 0.720*0.95 + 0.280*0.2 ≈ 0.740
    """
    bkt = BKT()
    p_correct = bkt.update(True)
    assert p_correct == pytest.approx(0.740, abs=0.005)
    # Knowledge rises after a correct answer
    assert bkt.knowledge > 0.3


def test_bkt_sequential_wrong_then_correct():
    """Two updates: wrong then correct."""
    bkt = BKT()
    bkt.update(False)   # knowledge ≈ 0.172
    p_correct = bkt.update(True)  # should recover toward mid-range
    # p_correct after wrong+correct should be ≈ 0.629
    assert p_correct == pytest.approx(0.629, abs=0.01)


def test_bkt_knowledge_monotone_correct():
    """Repeated correct answers should keep increasing knowledge."""
    bkt = BKT()
    prev = bkt.knowledge
    for _ in range(5):
        bkt.update(True)
        assert bkt.knowledge > prev
        prev = bkt.knowledge


def test_bkt_knowledge_decreases_on_wrong():
    """Wrong answer should reduce knowledge estimate (Bayesian update)."""
    bkt = BKT(p_l0=0.8)  # Start high
    bkt.update(False)
    assert bkt.knowledge < 0.8


def test_bkt_predict_difficulty():
    bkt = BKT(p_l0=0.9)
    assert bkt.predict_difficulty() == "hard"

    bkt.knowledge = 0.55
    assert bkt.predict_difficulty() == "medium"

    bkt.knowledge = 0.2
    assert bkt.predict_difficulty() == "easy"


# ---------------------------------------------------------------------------
# hybrid_bkt_recent tests
# ---------------------------------------------------------------------------

def test_hybrid_cold_start():
    """No history → easy (safe fallback)."""
    assert hybrid_bkt_recent([]) == "easy"


def test_hybrid_three_wrong():
    """
    3 wrong answers (score=0.2, 0.1, 0.3):
        recent_avg = 0.2   (< 0.4)
        BKT knowledge ≈ 0.16  (< 0.5)
    → "easy"
    """
    history = [("easy", 0.2), ("easy", 0.1), ("easy", 0.3)]
    assert hybrid_bkt_recent(history) == "easy"


def test_hybrid_three_correct():
    """
    3 strong correct answers (score=0.8, 0.9, 1.0):
        recent_avg = 0.9   (> 0.7)
        BKT knowledge ≈ 0.94  (> 0.6)
    → "hard"
    """
    history = [("easy", 0.8), ("easy", 0.9), ("easy", 1.0)]
    assert hybrid_bkt_recent(history) == "hard"


def test_hybrid_medium_performance():
    """
    Mixed mid-range performance (score≈0.5):
        recent_avg ≈ 0.5  (> 0.4)
        BKT knowledge moderate
    → "medium"
    """
    history = [("medium", 0.5), ("medium", 0.55), ("medium", 0.45)]
    result = hybrid_bkt_recent(history)
    assert result == "medium"


def test_hybrid_recent_window_is_five():
    """Only the last 5 attempts affect recent_avg, not the full history."""
    # Old bad scores followed by 5 strong scores
    old = [("easy", 0.1)] * 10
    recent = [("medium", 0.9)] * 5
    result = hybrid_bkt_recent(old + recent)
    # recent_avg = 0.9; BKT knowledge driven down by 10 wrongs but recent is strong
    # bkt_p may be moderate → at least "medium"
    assert result in ("medium", "hard")


def test_hybrid_mastery_override_not_in_hybrid():
    """hybrid_bkt_recent itself has no mastery override — it lives in select_optimal_difficulty."""
    # Even with all-wrong history and low mastery, the mastery override is applied externally
    history = [("easy", 0.9), ("easy", 0.95)]
    # High performance → should not return "easy"
    assert hybrid_bkt_recent(history) != "easy"
