"""
Unit tests for the urgency scoring logic in recommendations.py.
The _urgency function is defined locally inside get_recommendations,
so we replicate the formula here and test it directly.
"""
import pytest


def urgency(mastery: float, num_attempts: int, num_correct: int) -> float:
    """Mirror of the _urgency function in recommendations.py."""
    fail_rate = 1.0 - (num_correct / num_attempts) if num_attempts > 0 else 0.0
    return (1.0 - mastery) * (1.0 + fail_rate)


class TestUrgencyFormula:

    def test_zero_attempts_urgency_equals_one_minus_mastery(self):
        # No attempts → fail_rate=0 → urgency = (1-mastery)*1
        assert urgency(0.0, 0, 0) == pytest.approx(1.0)
        assert urgency(0.5, 0, 0) == pytest.approx(0.5)
        assert urgency(0.7, 0, 0) == pytest.approx(0.3)

    def test_high_fail_rate_increases_urgency(self):
        # Same mastery, more failures → higher urgency
        low_fail = urgency(0.4, 10, 9)   # fail_rate=0.1
        high_fail = urgency(0.4, 10, 1)  # fail_rate=0.9
        assert high_fail > low_fail

    def test_lower_mastery_increases_urgency(self):
        # Same stats, lower mastery → higher urgency
        high_m = urgency(0.6, 5, 3)
        low_m = urgency(0.2, 5, 3)
        assert low_m > high_m

    def test_perfect_mastery_gives_zero_urgency(self):
        # mastery=1.0 → always 0 regardless of attempts
        assert urgency(1.0, 0, 0) == pytest.approx(0.0)
        assert urgency(1.0, 10, 5) == pytest.approx(0.0)

    def test_all_correct_no_boost(self):
        # num_correct == num_attempts → fail_rate=0
        assert urgency(0.5, 10, 10) == pytest.approx(0.5)

    def test_all_wrong_doubles_urgency_at_zero_mastery(self):
        # mastery=0, all wrong → urgency = 1.0*(1+1.0) = 2.0
        assert urgency(0.0, 5, 0) == pytest.approx(2.0)

    def test_urgency_ranking(self):
        """Concepts should be ranked by urgency descending."""
        # Concept A: mastery=0.3, 10 attempts, 2 correct → fail_rate=0.8
        ua = urgency(0.3, 10, 2)   # (0.7)*(1.8) = 1.26
        # Concept B: mastery=0.4, 0 attempts → fail_rate=0.0
        ub = urgency(0.4, 0, 0)    # (0.6)*(1.0) = 0.60
        # Concept C: mastery=0.1, 5 attempts, 5 correct → fail_rate=0.0
        uc = urgency(0.1, 5, 5)    # (0.9)*(1.0) = 0.90

        ranking = sorted([ua, ub, uc], reverse=True)
        assert ranking == [ua, uc, ub]

    def test_fail_rate_computation(self):
        # 3 out of 10 correct → fail_rate = 0.7
        result = urgency(0.0, 10, 3)
        expected = 1.0 * (1.0 + 0.7)
        assert result == pytest.approx(expected)
