"""Tests for student task selection from the approved bank."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base, GeneratedTask, TaskAttempt
from app.database import get_db
from app.schemas import ConceptMastery, TaskSpec, MASTERY_PASSED
from datetime import datetime, timezone

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(engine_test, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _concept(concept_id, name, mastery=0.3):
    return ConceptMastery(
        concept_id=concept_id,
        concept_name=name,
        mastery=mastery,
        updated_at=datetime.now(timezone.utc),
    )


def _spec(difficulty="easy"):
    return TaskSpec(
        type="mcq", difficulty=difficulty,
        question="Вопрос?",
        options=["A", "B", "C"], correct_index=0,
        correct_answer=None,
        explanation="Потому что A.",
    )


async def _add_task(db, course_id, concept_id, difficulty="easy", status="approved"):
    t = GeneratedTask(
        course_id=course_id, concept_id=concept_id,
        concept_name="Концепт", difficulty=difficulty,
        json_spec=_spec(difficulty).model_dump(), status=status,
    )
    db.add(t)
    await db.flush()
    return t.id


# ── basic selection ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_student_gets_approved_tasks():
    async with TestSession() as db:
        await _add_task(db, course_id=1, concept_id=1)
        await db.commit()

    with (
        patch("app.router.fetch_mastery", new=AsyncMock(return_value=[_concept(1, "Концепт")])),
        patch("app.router.select_optimal_difficulty", new=AsyncMock(return_value=("easy", 0.3))),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/personalized-task", json={
                "student_id": 42, "course_id": 1,
                "max_concepts": 1, "variants_per_concept": 1,
            })

    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["spec"]["difficulty"] == "easy"


@pytest.mark.asyncio
async def test_student_gets_no_pending_tasks():
    """pending_review tasks must not be served to students."""
    async with TestSession() as db:
        await _add_task(db, course_id=1, concept_id=1, status="pending_review")
        await db.commit()

    with (
        patch("app.router.fetch_mastery", new=AsyncMock(return_value=[_concept(1, "Концепт")])),
        patch("app.router.select_optimal_difficulty", new=AsyncMock(return_value=("easy", 0.3))),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/personalized-task", json={
                "student_id": 42, "course_id": 1,
                "max_concepts": 1, "variants_per_concept": 1,
            })

    assert resp.status_code == 404


# ── passed task exclusion ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_passed_task_not_shown_again():
    """A task with a successful attempt (score >= MASTERY_PASSED) must be excluded."""
    async with TestSession() as db:
        task_id = await _add_task(db, course_id=1, concept_id=1)
        db.add(TaskAttempt(
            task_id=task_id, student_id=42, concept_id=1,
            difficulty="easy", score=MASTERY_PASSED,
        ))
        await db.commit()

    with (
        patch("app.router.fetch_mastery", new=AsyncMock(return_value=[_concept(1, "Концепт")])),
        patch("app.router.select_optimal_difficulty", new=AsyncMock(return_value=("easy", 0.3))),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/personalized-task", json={
                "student_id": 42, "course_id": 1,
                "max_concepts": 1, "variants_per_concept": 1,
            })

    # All approved tasks are exhausted — should return 404
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_failed_task_shown_again():
    """A task answered incorrectly (score < MASTERY_PASSED) must remain eligible."""
    async with TestSession() as db:
        task_id = await _add_task(db, course_id=1, concept_id=1)
        db.add(TaskAttempt(
            task_id=task_id, student_id=42, concept_id=1,
            difficulty="easy", score=MASTERY_PASSED - 0.1,  # failed
        ))
        await db.commit()

    with (
        patch("app.router.fetch_mastery", new=AsyncMock(return_value=[_concept(1, "Концепт")])),
        patch("app.router.select_optimal_difficulty", new=AsyncMock(return_value=("easy", 0.3))),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/personalized-task", json={
                "student_id": 42, "course_id": 1,
                "max_concepts": 1, "variants_per_concept": 1,
            })

    assert resp.status_code == 200
    assert len(resp.json()["tasks"]) == 1


# ── difficulty fallback ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_difficulty_fallback_to_medium():
    """If no 'hard' tasks available, fall back to 'medium'."""
    async with TestSession() as db:
        await _add_task(db, course_id=1, concept_id=1, difficulty="medium")
        await db.commit()

    with (
        patch("app.router.fetch_mastery", new=AsyncMock(return_value=[_concept(1, "Концепт")])),
        patch("app.router.select_optimal_difficulty", new=AsyncMock(return_value=("hard", 0.8))),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/personalized-task", json={
                "student_id": 42, "course_id": 1,
                "max_concepts": 1, "variants_per_concept": 1,
            })

    assert resp.status_code == 200
    assert resp.json()["tasks"][0]["spec"]["difficulty"] == "medium"


@pytest.mark.asyncio
async def test_empty_bank_returns_404():
    with (
        patch("app.router.fetch_mastery", new=AsyncMock(return_value=[_concept(1, "Концепт")])),
        patch("app.router.select_optimal_difficulty", new=AsyncMock(return_value=("easy", 0.3))),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/personalized-task", json={
                "student_id": 42, "course_id": 1,
                "max_concepts": 1, "variants_per_concept": 1,
            })

    assert resp.status_code == 404


# ── all concepts mastered ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_mastered_returns_200_with_detail():
    with patch("app.router.fetch_mastery", new=AsyncMock(return_value=[_concept(1, "Концепт", mastery=0.9)])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/personalized-task", json={
                "student_id": 42, "course_id": 1,
                "mastery_threshold": 0.7,
            })

    # FastAPI returns HTTP 200 with detail for "all mastered"
    assert resp.status_code == 200
    assert "освоены" in resp.json().get("detail", "")


# ── check-answer records attempt ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_answer_records_attempt():
    async with TestSession() as db:
        task_id = await _add_task(db, course_id=1, concept_id=1)
        await db.commit()

    with patch("app.router.push_mastery_update", new=AsyncMock()):
        with patch("app.router.check_chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(return_value={
                "score": 0.9, "correct": True, "explanation": "Верно!"
            })
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/v1/check-answer", json={
                    "task_id": task_id,
                    "student_id": 42,
                    "answer": {"selected_index": 0},
                })

    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 0.9
    assert data["correct"] is True

    # Verify TaskAttempt was recorded
    async with TestSession() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(TaskAttempt).where(TaskAttempt.task_id == task_id, TaskAttempt.student_id == 42)
        )
        attempt = result.scalar_one_or_none()
        assert attempt is not None
        assert attempt.score == 0.9

    # Verify task is still "approved" (not "used")
    async with TestSession() as db:
        task = await db.get(GeneratedTask, task_id)
        assert task.status == "approved"
