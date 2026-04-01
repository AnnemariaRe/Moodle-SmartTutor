"""
Unit tests for mastery update logic (EMA and placement formulas).
"""
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from app.mastery import (
    handle_event,
    _handle_quiz,
    _handle_assign,
    _handle_lesson_completed,
    _handle_lesson_answer,
    _update_mastery,
    _update_concept_stats,
)
from app.models import StudentConceptMastery, StudentConceptStats


def _make_db(existing_record=None):
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_record
    db = AsyncMock()
    db.execute.return_value = mock_result
    db.add = MagicMock()
    return db


def _make_scm(mastery: float) -> StudentConceptMastery:
    scm = MagicMock(spec=StudentConceptMastery)
    scm.mastery = mastery
    return scm


# EMA mastery (role="regular") 

class TestEMAMastery:
    """Tests for the weighted EMA formula: delta = weight*(target-old)*0.5"""

    @pytest.mark.asyncio
    async def test_high_score_increases_mastery(self):
        scm = _make_scm(0.0)
        db = _make_db(scm)
        # rel_score=0.9 → target=0.8; delta = 1.0*(0.8-0.0)*0.5 = 0.4
        await _update_mastery(db, 1, 1, 1, rel_score=0.9, weight=1.0, role="regular")
        assert scm.mastery == pytest.approx(0.4, abs=1e-4)

    @pytest.mark.asyncio
    async def test_mid_score_targets_05(self):
        scm = _make_scm(0.0)
        db = _make_db(scm)
        # rel_score=0.6 → target=0.5; delta = 1.0*(0.5-0.0)*0.5 = 0.25
        await _update_mastery(db, 1, 1, 1, rel_score=0.6, weight=1.0, role="regular")
        assert scm.mastery == pytest.approx(0.25, abs=1e-4)

    @pytest.mark.asyncio
    async def test_low_score_targets_02(self):
        scm = _make_scm(0.5)
        db = _make_db(scm)
        # rel_score=0.3 → target=0.2; delta = 1.0*(0.2-0.5)*0.5 = -0.15
        await _update_mastery(db, 1, 1, 1, rel_score=0.3, weight=1.0, role="regular")
        assert scm.mastery == pytest.approx(0.35, abs=1e-4)

    @pytest.mark.asyncio
    async def test_mastery_capped_at_1(self):
        scm = _make_scm(0.9)
        db = _make_db(scm)
        # rel_score=0.9 → target=0.8; delta = 1.0*(0.8-0.9)*0.5 = -0.05 → goes down slightly
        # With weight=4 and old=0.9: delta = 4*(0.8-0.9)*0.5 = -0.2 → 0.7
        # Use very high weight to test cap:
        scm2 = _make_scm(0.95)
        db2 = _make_db(scm2)
        # delta = 2*(0.8-0.95)*0.5 = -0.15 → result is 0.8
        scm3 = _make_scm(0.0)
        db3 = _make_db(scm3)
        # delta = 10*(0.8-0.0)*0.5 = 4.0 → clipped to 1.0
        await _update_mastery(db3, 1, 1, 1, rel_score=0.9, weight=10.0, role="regular")
        assert scm3.mastery == pytest.approx(1.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_mastery_floored_at_0(self):
        scm = _make_scm(0.1)
        db = _make_db(scm)
        # rel_score=0.0 → target=0.2; delta = 10*(0.2-0.1)*0.5 = 0.5
        scm = _make_scm(0.3)
        db = _make_db(scm)
        await _update_mastery(db, 1, 1, 1, rel_score=0.0, weight=10.0, role="regular")
        assert scm.mastery == pytest.approx(0.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_weight_scales_delta(self):
        scm1 = _make_scm(0.0)
        db1 = _make_db(scm1)
        await _update_mastery(db1, 1, 1, 1, rel_score=0.9, weight=0.5, role="regular")
        # delta = 0.5 * (0.8 - 0.0) * 0.5 = 0.2
        assert scm1.mastery == pytest.approx(0.2, abs=1e-4)

        scm2 = _make_scm(0.0)
        db2 = _make_db(scm2)
        await _update_mastery(db2, 1, 1, 1, rel_score=0.9, weight=2.0, role="regular")
        # delta = 2.0 * (0.8 - 0.0) * 0.5 = 0.8
        assert scm2.mastery == pytest.approx(0.8, abs=1e-4)

    @pytest.mark.asyncio
    async def test_new_student_record_created(self):
        """When no SCM row exists, a new one is inserted with mastery starting at 0."""
        db = _make_db(existing_record=None)
        await _update_mastery(db, 42, 5, 7, rel_score=0.9, weight=1.0, role="regular")
        assert db.add.called
        added = db.add.call_args[0][0]
        # The new record's mastery is set after add(), so check via scm attr
        assert added.mastery == pytest.approx(0.4, abs=1e-4)

    @pytest.mark.asyncio
    async def test_exact_08_boundary_hits_high_target(self):
        scm = _make_scm(0.0)
        db = _make_db(scm)
        # rel_score exactly 0.8 → target=0.8
        await _update_mastery(db, 1, 1, 1, rel_score=0.8, weight=1.0, role="regular")
        assert scm.mastery == pytest.approx(0.4, abs=1e-4)

    @pytest.mark.asyncio
    async def test_exact_05_boundary_hits_mid_target(self):
        scm = _make_scm(0.0)
        db = _make_db(scm)
        # rel_score exactly 0.5 → target=0.5
        await _update_mastery(db, 1, 1, 1, rel_score=0.5, weight=1.0, role="regular")
        assert scm.mastery == pytest.approx(0.25, abs=1e-4)


class TestPlacementMastery:
    """Tests for direct placement formula: min(1.0, rel_score * weight)"""

    @pytest.mark.asyncio
    async def test_placement_direct_score(self):
        scm = _make_scm(0.0)
        db = _make_db(scm)
        await _update_mastery(db, 1, 1, 1, rel_score=0.8, weight=1.0, role="placement")
        assert scm.mastery == pytest.approx(0.8, abs=1e-4)

    @pytest.mark.asyncio
    async def test_placement_with_weight(self):
        scm = _make_scm(0.0)
        db = _make_db(scm)
        # score=0.6, weight=0.9 → 0.6*0.9=0.54
        await _update_mastery(db, 1, 1, 1, rel_score=0.6, weight=0.9, role="placement")
        assert scm.mastery == pytest.approx(0.54, abs=1e-4)

    @pytest.mark.asyncio
    async def test_placement_capped_at_1(self):
        scm = _make_scm(0.0)
        db = _make_db(scm)
        # score=1.0, weight=2.0 → min(1.0, 2.0) = 1.0
        await _update_mastery(db, 1, 1, 1, rel_score=1.0, weight=2.0, role="placement")
        assert scm.mastery == pytest.approx(1.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_placement_ignores_previous_mastery(self):
        """Placement overwrites old mastery, doesn't use EMA smoothing."""
        scm = _make_scm(0.9)  # high old mastery
        db = _make_db(scm)
        # Low score → placement just writes min(1.0, 0.2*1.0) = 0.2
        await _update_mastery(db, 1, 1, 1, rel_score=0.2, weight=1.0, role="placement")
        assert scm.mastery == pytest.approx(0.2, abs=1e-4)

    @pytest.mark.asyncio
    async def test_placement_zero_score(self):
        scm = _make_scm(0.5)
        db = _make_db(scm)
        await _update_mastery(db, 1, 1, 1, rel_score=0.0, weight=1.0, role="placement")
        assert scm.mastery == pytest.approx(0.0, abs=1e-4)


class TestConceptStats:
    def _make_db_stats(self, existing=None):
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing
        db = AsyncMock()
        db.execute.return_value = mock_result
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_first_attempt_correct(self):
        db = self._make_db_stats(existing=None)
        await _update_concept_stats(db, student_id=1, course_id=1, concept_id=1, is_correct=True)
        assert db.add.called
        added = db.add.call_args[0][0]
        assert added.num_attempts == 1
        assert added.num_correct == 1

    @pytest.mark.asyncio
    async def test_first_attempt_wrong(self):
        db = self._make_db_stats(existing=None)
        await _update_concept_stats(db, student_id=1, course_id=1, concept_id=1, is_correct=False)
        assert db.add.called
        added = db.add.call_args[0][0]
        assert added.num_attempts == 1
        assert added.num_correct == 0

    @pytest.mark.asyncio
    async def test_subsequent_attempt_correct(self):
        existing = MagicMock(spec=StudentConceptStats)
        existing.num_attempts = 3
        existing.num_correct = 2
        db = self._make_db_stats(existing=existing)
        await _update_concept_stats(db, 1, 1, 1, is_correct=True)
        assert existing.num_attempts == 4
        assert existing.num_correct == 3

    @pytest.mark.asyncio
    async def test_subsequent_attempt_wrong(self):
        existing = MagicMock(spec=StudentConceptStats)
        existing.num_attempts = 5
        existing.num_correct = 3
        db = self._make_db_stats(existing=existing)
        await _update_concept_stats(db, 1, 1, 1, is_correct=False)
        assert existing.num_attempts == 6
        assert existing.num_correct == 3  # unchanged


class TestHandleEvent:
    """Tests for handle_event dispatch routing."""

    async def test_dispatches_quiz_event(self, monkeypatch):
        called = []
        async def fake_handle_quiz(event):
            called.append(event)
        monkeypatch.setattr("app.mastery._handle_quiz", fake_handle_quiz)
        await handle_event({"event_type": "quiz_attempt_submitted"})
        assert len(called) == 1

    async def test_dispatches_assign_event(self, monkeypatch):
        called = []
        async def fake_handle_assign(event):
            called.append(event)
        monkeypatch.setattr("app.mastery._handle_assign", fake_handle_assign)
        await handle_event({"event_type": "assign_submission_graded"})
        assert len(called) == 1

    async def test_dispatches_lesson_completed(self, monkeypatch):
        called = []
        async def fake_handler(event):
            called.append(event)
        monkeypatch.setattr("app.mastery._handle_lesson_completed", fake_handler)
        await handle_event({"event_type": "lesson_completed"})
        assert len(called) == 1

    async def test_dispatches_lesson_answer(self, monkeypatch):
        called = []
        async def fake_handler(event):
            called.append(event)
        monkeypatch.setattr("app.mastery._handle_lesson_answer", fake_handler)
        await handle_event({"event_type": "lesson_answer_submitted"})
        assert len(called) == 1

    async def test_ignores_unknown_event_type(self):
        # Should not raise
        await handle_event({"event_type": "unknown_event_xyz"})

    async def test_ignores_missing_event_type(self):
        await handle_event({})


class TestHandlerScoreNormalization:
    """Tests for rel_score computation in each handler."""

    async def test_quiz_score_normalization(self, monkeypatch):
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_quiz({"payload": {"score": 7.0, "max_score": 10.0}})
        assert captured["rel_score"] == pytest.approx(0.7)

    async def test_quiz_zero_max_score_gives_zero(self, monkeypatch):
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_quiz({"payload": {"score": 5.0, "max_score": 0.0}})
        assert captured["rel_score"] == pytest.approx(0.0)

    async def test_quiz_missing_payload_defaults_to_zero(self, monkeypatch):
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_quiz({})
        assert captured["rel_score"] == pytest.approx(0.0)

    async def test_assign_grade_normalization(self, monkeypatch):
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_assign({"payload": {"grade": 8.5, "max_grade": 10.0}})
        assert captured["rel_score"] == pytest.approx(0.85)

    async def test_assign_zero_max_grade_gives_zero(self, monkeypatch):
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_assign({"payload": {"grade": 3.0, "max_grade": 0.0}})
        assert captured["rel_score"] == pytest.approx(0.0)

    async def test_lesson_completed_score_from_questions(self, monkeypatch):
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_lesson_completed({"payload": {"num_questions": 5, "num_correct": 4}})
        assert captured["rel_score"] == pytest.approx(0.8)

    async def test_lesson_completed_fallback_to_score_percent(self, monkeypatch):
        """When num_questions=0, fall back to score_percent/100."""
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_lesson_completed({"payload": {"num_questions": 0, "score_percent": 75.0}})
        assert captured["rel_score"] == pytest.approx(0.75)

    async def test_lesson_completed_all_correct(self, monkeypatch):
        captured = {}
        async def fake_process(event, rel_score):
            captured["rel_score"] = rel_score
        monkeypatch.setattr("app.mastery._process_scored_event", fake_process)
        await _handle_lesson_completed({"payload": {"num_questions": 10, "num_correct": 10}})
        assert captured["rel_score"] == pytest.approx(1.0)


class TestLessonAnswer:
    """Tests for _handle_lesson_answer: 10% weight + is_correct → rel_score."""

    def _patch_session(self, monkeypatch, mock_db, concept_weights, role="regular"):
        @asynccontextmanager
        async def fake_session():
            yield mock_db

        async def fake_concept_weights(db, course_id, cmid):
            return concept_weights, role

        monkeypatch.setattr("app.mastery.get_adaptive_db_session", fake_session)
        monkeypatch.setattr("app.mastery._concept_weights_for_cmid", fake_concept_weights)

    async def test_correct_answer_uses_rel_score_1(self, monkeypatch):
        mock_db = AsyncMock()
        calls = []
        async def fake_update(db, student_id, course_id, concept_id, rel_score, weight, role="regular"):
            calls.append({"rel_score": rel_score, "weight": weight})
        self._patch_session(monkeypatch, mock_db, {100: 1.0})
        monkeypatch.setattr("app.mastery._update_mastery", fake_update)
        await _handle_lesson_answer({
            "student_id": 1, "course_id": 1, "cmid": 10,
            "payload": {"is_correct": True},
        })
        assert len(calls) == 1
        assert calls[0]["rel_score"] == pytest.approx(1.0)
        assert calls[0]["weight"] == pytest.approx(0.1)  # weight * 0.1

    async def test_wrong_answer_uses_rel_score_0(self, monkeypatch):
        mock_db = AsyncMock()
        calls = []
        async def fake_update(db, student_id, course_id, concept_id, rel_score, weight, role="regular"):
            calls.append({"rel_score": rel_score, "weight": weight})
        self._patch_session(monkeypatch, mock_db, {100: 1.0})
        monkeypatch.setattr("app.mastery._update_mastery", fake_update)
        await _handle_lesson_answer({
            "student_id": 1, "course_id": 1, "cmid": 10,
            "payload": {"is_correct": False},
        })
        assert calls[0]["rel_score"] == pytest.approx(0.0)

    async def test_weight_scaled_by_01(self, monkeypatch):
        """Original weight 0.8 should be passed as 0.08 (10% reduction)."""
        mock_db = AsyncMock()
        calls = []
        async def fake_update(db, student_id, course_id, concept_id, rel_score, weight, role="regular"):
            calls.append(weight)
        self._patch_session(monkeypatch, mock_db, {100: 0.8})
        monkeypatch.setattr("app.mastery._update_mastery", fake_update)
        await _handle_lesson_answer({
            "student_id": 1, "course_id": 1, "cmid": 10,
            "payload": {"is_correct": True},
        })
        assert calls[0] == pytest.approx(0.08)

    async def test_no_content_item_skips_update(self, monkeypatch):
        """Empty concept_weights → _update_mastery not called."""
        mock_db = AsyncMock()
        calls = []
        async def fake_update(db, student_id, course_id, concept_id, rel_score, weight, role="regular"):
            calls.append(True)
        self._patch_session(monkeypatch, mock_db, {})  # empty
        monkeypatch.setattr("app.mastery._update_mastery", fake_update)
        await _handle_lesson_answer({
            "student_id": 1, "course_id": 1, "cmid": 99,
            "payload": {"is_correct": True},
        })
        assert calls == []
