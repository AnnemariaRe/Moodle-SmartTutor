"""
Tests for CoursePortrait analytics: difficulty calculators,
MetricsCalculator, and MLPredictor fallback.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.difficulty_calculators import (
    QuizDifficultyCalculator,
    VideoDifficultyCalculator,
    TextDifficultyCalculator,
    AssignmentDifficultyCalculator,
    GenericDifficultyCalculator,
    DifficultyCalculatorFactory,
    DifficultyResult,
)
from app.services.calculator import MetricsCalculator
from app.services.ml_predictor import MLPredictor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quiz(avg_score=70.0, attempts=1.0, completion=0.9, time=500):
    return {"moduleType": "quiz", "avgScore": avg_score,
            "attemptCount": attempts, "completionRate": completion,
            "avgTimeSpent": time, "expectedTime": 600}


def _video(watch=0.8, seek_back=0, pauses=0, dropout=0.05):
    return {"moduleType": "video", "watchPercent": watch,
            "seekBackwardCount": seek_back, "pauseCount": pauses,
            "dropoutRate": dropout}


def _text(read_time=60000, scroll=0.85, returns=0.1, dropout=0.05):
    return {"moduleType": "page", "avgReadTime": read_time,
            "expectedReadTime": 60000, "scrollDepth": scroll,
            "returnVisits": returns, "dropoutRate": dropout}


def _assign(submit=0.9, grade=80.0, late=0.05, resub=0.05):
    return {"moduleType": "assign", "submissionRate": submit,
            "avgGrade": grade, "lateSubmissions": late,
            "resubmissions": resub}


def _generic(duration=60000, median=60000, dropout=0.1, engagement=0.7):
    return {"moduleType": "unknown", "avgDurationMs": duration,
            "medianDurationMs": median, "dropoutRate": dropout,
            "engagementScore": engagement}


# ---------------------------------------------------------------------------
# BaseDifficultyCalculator._get_difficulty_level
# ---------------------------------------------------------------------------

class TestDifficultyLevel:
    def test_easy(self):
        assert QuizDifficultyCalculator._get_difficulty_level(0.0) == "easy"
        assert QuizDifficultyCalculator._get_difficulty_level(0.39) == "easy"

    def test_medium(self):
        assert QuizDifficultyCalculator._get_difficulty_level(0.4) == "medium"
        assert QuizDifficultyCalculator._get_difficulty_level(0.69) == "medium"

    def test_hard(self):
        assert QuizDifficultyCalculator._get_difficulty_level(0.7) == "hard"
        assert QuizDifficultyCalculator._get_difficulty_level(1.0) == "hard"

    def test_clamp(self):
        assert QuizDifficultyCalculator._clamp(-0.5) == 0.0
        assert QuizDifficultyCalculator._clamp(1.5) == 1.0
        assert QuizDifficultyCalculator._clamp(0.5) == 0.5


# ---------------------------------------------------------------------------
# QuizDifficultyCalculator
# ---------------------------------------------------------------------------

class TestQuizCalculator:
    calc = QuizDifficultyCalculator()

    def test_returns_difficulty_result(self):
        result = self.calc.calculate(_quiz())
        assert isinstance(result, DifficultyResult)
        assert result.module_type == "quiz"

    def test_score_in_range(self):
        result = self.calc.calculate(_quiz())
        assert 0.0 <= result.difficulty_score <= 1.0

    def test_easy_on_perfect_data(self):
        result = self.calc.calculate(_quiz(avg_score=100, attempts=1.0, completion=1.0, time=300))
        assert result.difficulty_level == "easy"
        assert result.difficulty_score < 0.4

    def test_hard_on_bad_data(self):
        result = self.calc.calculate(_quiz(avg_score=20, attempts=4.0, completion=0.3, time=1500))
        assert result.difficulty_level == "hard"
        assert result.difficulty_score >= 0.7

    def test_medium_band(self):
        result = self.calc.calculate(_quiz(avg_score=55, attempts=2.0, completion=0.7, time=700))
        assert result.difficulty_level == "medium"

    def test_four_metrics_returned(self):
        result = self.calc.calculate(_quiz())
        assert len(result.metrics) == 4

    def test_contributions_sum_equals_score(self):
        result = self.calc.calculate(_quiz(avg_score=45, attempts=3.0, completion=0.5, time=900))
        total = sum(m.contribution for m in result.metrics)
        assert abs(total - result.difficulty_score) < 1e-6

    def test_suggestions_present_on_hard(self):
        result = self.calc.calculate(_quiz(avg_score=20, attempts=4.0, completion=0.3, time=1500))
        assert len(result.suggestions) > 0

    def test_no_suggestions_on_easy(self):
        result = self.calc.calculate(_quiz(avg_score=95, attempts=1.0, completion=1.0, time=200))
        assert len(result.suggestions) == 0

    def test_attempts_clamped_at_3(self):
        # (4 - 1) / 2 = 1.5 → clamp → 1.0, must not break
        result = self.calc.calculate(_quiz(attempts=10.0))
        assert result.difficulty_score <= 1.0

    def test_defaults_used_when_keys_missing(self):
        result = self.calc.calculate({"moduleType": "quiz"})
        assert isinstance(result, DifficultyResult)


# ---------------------------------------------------------------------------
# VideoDifficultyCalculator
# ---------------------------------------------------------------------------

class TestVideoCalculator:
    calc = VideoDifficultyCalculator()

    def test_returns_difficulty_result(self):
        result = self.calc.calculate(_video())
        assert isinstance(result, DifficultyResult)
        assert result.module_type == "video"

    def test_easy_on_good_video(self):
        result = self.calc.calculate(_video(watch=0.95, seek_back=0, pauses=1, dropout=0.02))
        assert result.difficulty_level == "easy"

    def test_hard_on_bad_video(self):
        result = self.calc.calculate(_video(watch=0.2, seek_back=8, pauses=12, dropout=0.5))
        assert result.difficulty_level == "hard"

    def test_four_metrics_returned(self):
        result = self.calc.calculate(_video())
        assert len(result.metrics) == 4

    def test_watch_percent_inverted(self):
        low_watch = self.calc.calculate(_video(watch=0.1)).difficulty_score
        high_watch = self.calc.calculate(_video(watch=0.9)).difficulty_score
        assert low_watch > high_watch

    def test_seek_back_increases_difficulty(self):
        no_seek = self.calc.calculate(_video(seek_back=0)).difficulty_score
        many_seek = self.calc.calculate(_video(seek_back=8)).difficulty_score
        assert many_seek > no_seek

    def test_contributions_sum_equals_score(self):
        result = self.calc.calculate(_video(watch=0.4, seek_back=5, pauses=8, dropout=0.25))
        total = sum(m.contribution for m in result.metrics)
        assert abs(total - result.difficulty_score) < 1e-6


# ---------------------------------------------------------------------------
# TextDifficultyCalculator
# ---------------------------------------------------------------------------

class TestTextCalculator:
    calc = TextDifficultyCalculator()

    def test_returns_difficulty_result(self):
        result = self.calc.calculate(_text())
        assert isinstance(result, DifficultyResult)
        assert result.module_type == "text"

    def test_easy_on_ideal_reading(self):
        result = self.calc.calculate(_text(read_time=60000, scroll=0.95, returns=0.0, dropout=0.0))
        assert result.difficulty_level == "easy"

    def test_hard_on_poor_reading(self):
        result = self.calc.calculate(_text(read_time=180000, scroll=0.3, returns=3.0, dropout=0.4))
        assert result.difficulty_level == "hard"

    def test_four_metrics_returned(self):
        result = self.calc.calculate(_text())
        assert len(result.metrics) == 4

    def test_scroll_depth_inverted(self):
        low_scroll = self.calc.calculate(_text(scroll=0.2)).difficulty_score
        high_scroll = self.calc.calculate(_text(scroll=0.95)).difficulty_score
        assert low_scroll > high_scroll

    def test_zero_expected_time_doesnt_crash(self):
        data = _text()
        data["expectedReadTime"] = 0
        result = self.calc.calculate(data)
        assert 0.0 <= result.difficulty_score <= 1.0


# ---------------------------------------------------------------------------
# AssignmentDifficultyCalculator
# ---------------------------------------------------------------------------

class TestAssignmentCalculator:
    calc = AssignmentDifficultyCalculator()

    def test_returns_difficulty_result(self):
        result = self.calc.calculate(_assign())
        assert isinstance(result, DifficultyResult)
        assert result.module_type == "assignment"

    def test_easy_on_perfect_assignment(self):
        result = self.calc.calculate(_assign(submit=1.0, grade=100.0, late=0.0, resub=0.0))
        assert result.difficulty_level == "easy"

    def test_hard_on_failing_assignment(self):
        result = self.calc.calculate(_assign(submit=0.3, grade=25.0, late=0.7, resub=0.6))
        assert result.difficulty_level == "hard"

    def test_four_metrics_returned(self):
        result = self.calc.calculate(_assign())
        assert len(result.metrics) == 4

    def test_grade_inverted(self):
        low_grade = self.calc.calculate(_assign(grade=20.0)).difficulty_score
        high_grade = self.calc.calculate(_assign(grade=90.0)).difficulty_score
        assert low_grade > high_grade

    def test_contributions_sum_equals_score(self):
        result = self.calc.calculate(_assign(submit=0.5, grade=40.0, late=0.4, resub=0.3))
        total = sum(m.contribution for m in result.metrics)
        assert abs(total - result.difficulty_score) < 1e-6


# ---------------------------------------------------------------------------
# GenericDifficultyCalculator
# ---------------------------------------------------------------------------

class TestGenericCalculator:
    calc = GenericDifficultyCalculator()

    def test_returns_difficulty_result(self):
        result = self.calc.calculate(_generic())
        assert isinstance(result, DifficultyResult)
        assert result.module_type == "generic"

    def test_three_metrics_returned(self):
        result = self.calc.calculate(_generic())
        assert len(result.metrics) == 3

    def test_zero_median_doesnt_crash(self):
        data = _generic()
        data["medianDurationMs"] = 0
        result = self.calc.calculate(data)
        assert 0.0 <= result.difficulty_score <= 1.0

    def test_high_engagement_lowers_difficulty(self):
        low_eng = self.calc.calculate(_generic(engagement=0.1)).difficulty_score
        high_eng = self.calc.calculate(_generic(engagement=0.95)).difficulty_score
        assert low_eng > high_eng


# ---------------------------------------------------------------------------
# DifficultyCalculatorFactory
# ---------------------------------------------------------------------------

class TestDifficultyCalculatorFactory:
    @pytest.mark.parametrize("module_type,expected_class", [
        ("quiz", QuizDifficultyCalculator),
        ("video", VideoDifficultyCalculator),
        ("resource", VideoDifficultyCalculator),
        ("page", TextDifficultyCalculator),
        ("book", TextDifficultyCalculator),
        ("label", TextDifficultyCalculator),
        ("assign", AssignmentDifficultyCalculator),
        ("workshop", AssignmentDifficultyCalculator),
    ])
    def test_correct_calculator_for_type(self, module_type, expected_class):
        calc = DifficultyCalculatorFactory.get_calculator(module_type)
        assert isinstance(calc, expected_class)

    def test_unknown_type_returns_generic(self):
        calc = DifficultyCalculatorFactory.get_calculator("unknownxyz")
        assert isinstance(calc, GenericDifficultyCalculator)

    def test_type_case_insensitive(self):
        calc = DifficultyCalculatorFactory.get_calculator("QUIZ")
        assert isinstance(calc, QuizDifficultyCalculator)

    def test_calculate_difficulty_routes_by_type(self):
        result = DifficultyCalculatorFactory.calculate_difficulty(
            {"moduleType": "quiz", "avgScore": 50.0}
        )
        assert result.module_type == "quiz"

    def test_fallback_to_video_calculator_when_watch_percent_present(self):
        data = {"moduleType": "custom_video", "watchPercent": 0.6}
        result = DifficultyCalculatorFactory.calculate_difficulty(data)
        assert result.module_type == "video"

    def test_fallback_to_generic_when_no_watch_percent(self):
        data = {"moduleType": "custom_unknown"}
        result = DifficultyCalculatorFactory.calculate_difficulty(data)
        assert result.module_type == "generic"


# ---------------------------------------------------------------------------
# MetricsCalculator
# ---------------------------------------------------------------------------

class TestMetricsCalculator:
    """Tests for the aggregating metrics calculator."""

    def _make_predictor(self):
        """Minimal predictor without model (fallback)."""
        return MLPredictor(models_dir="/nonexistent")

    def _make_modules(self):
        return [
            {"moduleId": 1, "moduleType": "quiz", "avgDurationMs": 300000,
             "watchPercent": 0.8, "dropoutRate": 0.05, "pauseCount": 2, "step": 1,
             "avgScore": 75.0, "attemptCount": 1.2, "completionRate": 0.9,
             "avgTimeSpent": 400, "expectedTime": 600},
            {"moduleId": 2, "moduleType": "video", "avgDurationMs": 600000,
             "watchPercent": 0.35, "dropoutRate": 0.45, "pauseCount": 10, "step": 2,
             "seekBackwardCount": 6},
            {"moduleId": 3, "moduleType": "page", "avgDurationMs": 120000,
             "watchPercent": 0.9, "dropoutRate": 0.02, "pauseCount": 0, "step": 3},
        ]

    def test_calculate_difficulty_scores_returns_all_modules(self):
        modules = self._make_modules()
        predictor = self._make_predictor()
        result = MetricsCalculator.calculate_difficulty_scores(modules, predictor)
        assert len(result) == 3

    def test_each_module_has_dropout_risk(self):
        modules = self._make_modules()
        predictor = self._make_predictor()
        result = MetricsCalculator.calculate_difficulty_scores(modules, predictor)
        for m in result:
            assert "dropoutRisk" in m
            assert 0.0 <= m["dropoutRisk"] <= 1.0

    def test_each_module_has_difficulty_score(self):
        modules = self._make_modules()
        predictor = self._make_predictor()
        result = MetricsCalculator.calculate_difficulty_scores(modules, predictor)
        for m in result:
            assert "difficultyScore" in m
            assert 0.0 <= m["difficultyScore"] <= 1.0

    def test_each_module_has_difficulty_level(self):
        modules = self._make_modules()
        predictor = self._make_predictor()
        result = MetricsCalculator.calculate_difficulty_scores(modules, predictor)
        for m in result:
            assert m.get("difficultyLevel") in {"easy", "medium", "hard"}

    def test_type_aware_sets_difficulty_details(self):
        modules = self._make_modules()
        predictor = self._make_predictor()
        result = MetricsCalculator.calculate_difficulty_scores(modules, predictor, use_type_aware=True)
        for m in result:
            assert m.get("difficultyDetails") is not None

    def test_empty_modules_returns_empty(self):
        predictor = self._make_predictor()
        result = MetricsCalculator.calculate_difficulty_scores([], predictor)
        assert result == []

    def test_identify_bottlenecks_finds_hard_modules(self):
        modules = [
            {"moduleId": 1, "difficultyScore": 0.8, "studentCount": 100},
            {"moduleId": 2, "difficultyScore": 0.2, "studentCount": 80},
            {"moduleId": 3, "difficultyScore": 0.6, "studentCount": 50},
        ]
        bottlenecks = MetricsCalculator.identify_bottlenecks(modules, threshold=0.35)
        assert 1 in bottlenecks
        assert 3 in bottlenecks
        assert 2 not in bottlenecks

    def test_identify_bottlenecks_excludes_low_traffic(self):
        modules = [
            {"moduleId": 1, "difficultyScore": 0.9, "studentCount": 100},
            {"moduleId": 2, "difficultyScore": 0.9, "studentCount": 5},  # <10% traffic
        ]
        bottlenecks = MetricsCalculator.identify_bottlenecks(modules, threshold=0.35)
        assert 1 in bottlenecks
        assert 2 not in bottlenecks

    def test_identify_bottlenecks_empty_returns_empty(self):
        assert MetricsCalculator.identify_bottlenecks([]) == []

    def test_analyze_dropoff_chains_returns_top5(self):
        sequences = [
            [1, 2, 3], [1, 2, 3], [1, 2, 3],
            [4, 5, 6], [4, 5, 6],
            [7, 8, 9],
        ]
        chains = MetricsCalculator.analyze_dropoff_chains(sequences)
        assert len(chains) <= 5
        assert [1, 2, 3] in chains
        assert [4, 5, 6] in chains

    def test_analyze_dropoff_chains_ignores_long_sequences(self):
        # Long sequences (>=5 modules) are not dropout, ignored
        sequences = [
            [1, 2, 3, 4, 5, 6],  # not dropout
            [1, 2, 3],            # dropout
        ]
        chains = MetricsCalculator.analyze_dropoff_chains(sequences)
        assert [1, 2, 3] in chains
        # [4, 5, 6] — tail of long sequence should not appear in top chains
        assert [4, 5, 6] not in chains

    def test_analyze_dropoff_chains_empty_returns_empty(self):
        assert MetricsCalculator.analyze_dropoff_chains([]) == []

    def test_generate_recommendations_high_dropout(self):
        modules = [
            {"moduleId": 10, "moduleName": "Quiz", "difficultyScore": 0.5,
             "dropoutRate": 0.6, "watchPercent": 0.7, "dropoutRisk": 0.8},
        ]
        recs = MetricsCalculator.generate_recommendations(modules)
        assert len(recs) == 1
        assert recs[0]["priority"] == "high"

    def test_generate_recommendations_low_watch(self):
        modules = [
            {"moduleId": 11, "moduleName": "Video", "difficultyScore": 0.3,
             "dropoutRate": 0.1, "watchPercent": 0.2, "dropoutRisk": 0.1},
        ]
        recs = MetricsCalculator.generate_recommendations(modules)
        assert len(recs) == 1
        assert recs[0]["priority"] == "medium"

    def test_generate_recommendations_no_issues(self):
        modules = [
            {"moduleId": 12, "moduleName": "Page", "difficultyScore": 0.2,
             "dropoutRate": 0.05, "watchPercent": 0.85, "dropoutRisk": 0.1},
        ]
        recs = MetricsCalculator.generate_recommendations(modules)
        assert len(recs) == 0

    def test_generate_recommendations_sorted_by_priority(self):
        modules = [
            {"moduleId": 1, "moduleName": "A", "difficultyScore": 0.8,
             "dropoutRate": 0.1, "watchPercent": 0.2, "dropoutRisk": 0.1},
            {"moduleId": 2, "moduleName": "B", "difficultyScore": 0.5,
             "dropoutRate": 0.6, "watchPercent": 0.7, "dropoutRisk": 0.8},
        ]
        recs = MetricsCalculator.generate_recommendations(modules)
        priorities = [r["priority"] for r in recs]
        assert priorities.index("high") < priorities.index("medium")


# ---------------------------------------------------------------------------
# MLPredictor (fallback without model)
# ---------------------------------------------------------------------------