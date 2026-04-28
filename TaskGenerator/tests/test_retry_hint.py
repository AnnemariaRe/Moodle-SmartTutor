"""Minimal tests for the retry/hint flow in check-answer endpoint."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.router import FALLBACK_HINT, MAX_ATTEMPTS, _count_attempts_in_current_cycle


class _FakeDB:
    """Minimal stub of AsyncSession returning pre-canned scalar() results."""

    def __init__(self, last_correct_at, failed_count):
        self._results = [last_correct_at, failed_count]

    async def scalar(self, stmt):
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_attempts_counted_from_last_correct():
    """After a correct attempt, the cycle resets and failures are counted anew."""
    db = _FakeDB(last_correct_at=datetime.now(timezone.utc), failed_count=0)
    assert await _count_attempts_in_current_cycle(db, 1, 10) == 0


@pytest.mark.asyncio
async def test_attempts_counted_when_no_correct_yet():
    """If the student never answered correctly, all failures count in cycle."""
    db = _FakeDB(last_correct_at=None, failed_count=1)
    assert await _count_attempts_in_current_cycle(db, 1, 10) == 1


def test_max_attempts_constant():
    """MVP hardcodes MAX_ATTEMPTS=2: one retry after the first wrong answer."""
    assert MAX_ATTEMPTS == 2


def test_fallback_hint_is_russian_and_non_empty():
    """Ensure fallback has a non-empty Russian hint so UI always has something to show."""
    assert FALLBACK_HINT
    assert any("а" <= ch.lower() <= "я" for ch in FALLBACK_HINT)


@pytest.mark.asyncio
async def test_check_answer_returns_hint_on_first_wrong():
    """First wrong attempt: response contains the spec's hint, no explanation."""
    from app.router import check_answer
    from app.schemas import CheckAnswerRequest

    fake_task = type("T", (), {
        "id": 42, "course_id": 10, "concept_id": 5, "difficulty": "medium",
        "json_spec": {
            "hint": "Вспомни про правило замены букв.",
            "explanation": "Полное объяснение.",
            "difficulty": "medium",
        },
    })()

    class _DB:
        def __init__(self):
            self.added = []
            self._scalars = [None, 0]  # no prior correct, 0 prior failures
        async def get(self, model, pk): return fake_task
        async def scalar(self, stmt): return self._scalars.pop(0)
        def add(self, obj): self.added.append(obj)
        async def commit(self): pass

    with patch("app.router.check_chain") as mock_chain, \
         patch("app.router.push_mastery_update", AsyncMock()) as mock_push:
        mock_chain.ainvoke = AsyncMock(return_value={
            "score": 0.2, "correct": False, "explanation": "(llm-explanation)"
        })
        req = CheckAnswerRequest(task_id=42, student_id=99, answer={"text": "wrong"})
        resp = await check_answer(req, db=_DB())

    assert resp.correct is False
    assert resp.can_retry is True
    assert resp.attempt_no == 1
    assert resp.hint == "Вспомни про правило замены букв."
    assert resp.explanation is None
    # Mastery must NOT update on mid-cycle wrong attempt (double-penalty prevention)
    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_check_answer_returns_explanation_on_second_wrong():
    """Second wrong attempt: response contains the explanation, no hint, mastery updates."""
    from app.router import check_answer
    from app.schemas import CheckAnswerRequest

    fake_task = type("T", (), {
        "id": 42, "course_id": 10, "concept_id": 5, "difficulty": "medium",
        "json_spec": {
            "hint": "Подсказка.",
            "explanation": "Финальное объяснение.",
            "difficulty": "medium",
        },
    })()

    class _DB:
        def __init__(self):
            self.added = []
            self._scalars = [None, 1]  # no prior correct, 1 prior failure
        async def get(self, model, pk): return fake_task
        async def scalar(self, stmt): return self._scalars.pop(0)
        def add(self, obj): self.added.append(obj)
        async def commit(self): pass

    with patch("app.router.check_chain") as mock_chain, \
         patch("app.router.push_mastery_update", AsyncMock()) as mock_push:
        mock_chain.ainvoke = AsyncMock(return_value={
            "score": 0.3, "correct": False, "explanation": "(llm)"
        })
        req = CheckAnswerRequest(task_id=42, student_id=99, answer={"text": "wrong again"})
        resp = await check_answer(req, db=_DB())

    assert resp.correct is False
    assert resp.can_retry is False
    assert resp.attempt_no == 2
    assert resp.hint is None
    assert resp.explanation == "Финальное объяснение."
    mock_push.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_hint_used_when_spec_missing_hint():
    """If json_spec has no hint (legacy tasks), fallback string is returned."""
    from app.router import check_answer
    from app.schemas import CheckAnswerRequest

    fake_task = type("T", (), {
        "id": 1, "course_id": 10, "concept_id": 5, "difficulty": "medium",
        "json_spec": {"explanation": "x", "difficulty": "medium"},  # no hint key
    })()

    class _DB:
        def __init__(self): self._scalars = [None, 0]
        async def get(self, model, pk): return fake_task
        async def scalar(self, stmt): return self._scalars.pop(0)
        def add(self, obj): pass
        async def commit(self): pass

    with patch("app.router.check_chain") as mock_chain, \
         patch("app.router.push_mastery_update", AsyncMock()):
        mock_chain.ainvoke = AsyncMock(return_value={
            "score": 0.1, "correct": False, "explanation": ""
        })
        req = CheckAnswerRequest(task_id=1, student_id=99, answer={"text": "x"})
        resp = await check_answer(req, db=_DB())

    assert resp.hint == FALLBACK_HINT
