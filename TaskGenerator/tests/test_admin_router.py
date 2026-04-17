"""Tests for admin (teacher) endpoints: generate-bank, list bank, review, bulk review."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base, GeneratedTask
from app.database import get_db
from app.schemas import TaskSpec

# ── In-memory SQLite DB for tests ────────────────────────────────────────────

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


SAMPLE_SPEC = TaskSpec(
    type="mcq",
    difficulty="easy",
    question="Что такое переменная?",
    options=["Ячейка памяти", "Функция", "Класс", "Модуль"],
    correct_index=0,
    correct_answer=None,
    explanation="Переменная — именованная ячейка памяти.",
)

SAMPLE_CONCEPTS = [
    {"id": 1, "name": "Переменные"},
    {"id": 2, "name": "Циклы"},
]


# ── generate-bank ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_bank_creates_tasks():
    with (
        patch("app.admin_router.fetch_all_concepts", new=AsyncMock(return_value=SAMPLE_CONCEPTS)),
        patch("app.admin_router.generate_tasks_for_bank", new=AsyncMock(return_value=[SAMPLE_SPEC])),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/admin/generate-bank", json={
                "course_id": 10,
                "teacher_id": 5,
                "tasks_per_concept": 3,
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["concepts_covered"] == 2
    # 2 concepts × 3 difficulties × 1 task each = 6
    assert data["total_tasks"] == 6
    assert len(data["batch_id"]) == 36  # UUID


@pytest.mark.asyncio
async def test_generate_bank_no_concepts_returns_404():
    with patch("app.admin_router.fetch_all_concepts", new=AsyncMock(return_value=[])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/admin/generate-bank", json={
                "course_id": 99,
                "teacher_id": 5,
            })
    assert resp.status_code == 404


# ── list bank ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_bank_returns_tasks():
    # Pre-insert tasks directly
    async with TestSession() as db:
        db.add(GeneratedTask(
            course_id=10, concept_id=1, concept_name="Переменные",
            difficulty="easy", json_spec=SAMPLE_SPEC.model_dump(),
            status="pending_review", batch_id="batch-1",
        ))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/admin/bank", params={"course_id": 10})

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["tasks"][0]["concept_name"] == "Переменные"


@pytest.mark.asyncio
async def test_list_bank_filters_by_status():
    async with TestSession() as db:
        db.add(GeneratedTask(
            course_id=10, concept_id=1, concept_name="Переменные",
            difficulty="easy", json_spec=SAMPLE_SPEC.model_dump(),
            status="approved",
        ))
        db.add(GeneratedTask(
            course_id=10, concept_id=1, concept_name="Переменные",
            difficulty="medium", json_spec=SAMPLE_SPEC.model_dump(),
            status="pending_review",
        ))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/admin/bank", params={"course_id": 10, "status": "approved"})

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["tasks"][0]["status"] == "approved"


# ── review single task ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_approve_task():
    async with TestSession() as db:
        task = GeneratedTask(
            course_id=10, concept_id=1, concept_name="Переменные",
            difficulty="easy", json_spec=SAMPLE_SPEC.model_dump(),
            status="pending_review",
        )
        db.add(task)
        await db.flush()
        task_id = task.id
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/admin/review", json={
            "task_id": task_id,
            "action": "approve",
            "reviewed_by": 5,
        })

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    async with TestSession() as db:
        task = await db.get(GeneratedTask, task_id)
        assert task.status == "approved"
        assert task.reviewed_by == 5


@pytest.mark.asyncio
async def test_review_reject_task():
    async with TestSession() as db:
        task = GeneratedTask(
            course_id=10, concept_id=1, concept_name="Переменные",
            difficulty="easy", json_spec=SAMPLE_SPEC.model_dump(),
            status="pending_review",
        )
        db.add(task)
        await db.flush()
        task_id = task.id
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/admin/review", json={
            "task_id": task_id,
            "action": "reject",
            "reviewed_by": 5,
        })

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_review_with_edited_spec():
    async with TestSession() as db:
        task = GeneratedTask(
            course_id=10, concept_id=1, concept_name="Переменные",
            difficulty="easy", json_spec=SAMPLE_SPEC.model_dump(),
            status="pending_review",
        )
        db.add(task)
        await db.flush()
        task_id = task.id
        await db.commit()

    edited = SAMPLE_SPEC.model_copy(update={"question": "Новый вопрос"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/admin/review", json={
            "task_id": task_id,
            "action": "approve",
            "reviewed_by": 5,
            "edited_spec": edited.model_dump(),
        })

    assert resp.status_code == 200
    async with TestSession() as db:
        task = await db.get(GeneratedTask, task_id)
        assert task.json_spec["question"] == "Новый вопрос"


# ── bulk review ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_approve():
    ids = []
    async with TestSession() as db:
        for _ in range(3):
            t = GeneratedTask(
                course_id=10, concept_id=1, concept_name="X",
                difficulty="easy", json_spec=SAMPLE_SPEC.model_dump(),
                status="pending_review",
            )
            db.add(t)
            await db.flush()
            ids.append(t.id)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/admin/review-bulk", json={
            "task_ids": ids,
            "action": "approve",
            "reviewed_by": 5,
        })

    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 3
    assert all(r["status"] == "approved" for r in results)
