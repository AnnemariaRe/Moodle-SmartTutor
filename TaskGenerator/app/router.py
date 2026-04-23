import logging
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adaptive_client import fetch_mastery, push_mastery_update
from app.chains import check_chain
from app.database import get_db
from app.models import GeneratedTask, TaskAttempt
from app.predictor import select_optimal_difficulty
from app.schemas import (
    MASTERY_PASSED,
    CheckAnswerRequest,
    CheckAnswerResponse,
    PersonalizedTaskRequest,
    PersonalizedTaskResponse,
    TaskResponse,
    TaskSpec,
)

MAX_ATTEMPTS = 2
FALLBACK_HINT = "Подумай ещё раз о ключевом принципе этого задания."

router = APIRouter(prefix="/v1")
logger = logging.getLogger(__name__)

# Fallback order when the target difficulty has no approved tasks available
_DIFFICULTY_FALLBACK = {
    "easy":   ["easy", "medium", "hard"],
    "medium": ["medium", "easy", "hard"],
    "hard":   ["hard", "medium", "easy"],
}


async def _pick_approved_tasks(
    db: AsyncSession,
    student_id: int,
    course_id: int,
    concept_id: int,
    target_difficulty: str,
    count: int,
) -> list[GeneratedTask]:
    """
    Select up to `count` approved tasks for the concept that the student
    has NOT yet passed (score >= MASTERY_PASSED).

    Tasks answered incorrectly (score < MASTERY_PASSED) remain eligible
    and may be shown again.
    """
    passed_result = await db.execute(
        select(TaskAttempt.task_id)
        .where(
            TaskAttempt.student_id == student_id,
            TaskAttempt.concept_id == concept_id,
            TaskAttempt.score >= MASTERY_PASSED,
            TaskAttempt.task_id.is_not(None),
        )
    )
    passed_ids = {row[0] for row in passed_result.all()}

    for difficulty in _DIFFICULTY_FALLBACK.get(target_difficulty, [target_difficulty]):
        result = await db.execute(
            select(GeneratedTask).where(
                GeneratedTask.course_id == course_id,
                GeneratedTask.concept_id == concept_id,
                GeneratedTask.difficulty == difficulty,
                GeneratedTask.status == "approved",
            )
        )
        candidates = [t for t in result.scalars().all() if t.id not in passed_ids]
        if candidates:
            return random.sample(candidates, min(count, len(candidates)))

    return []


@router.post("/personalized-task", response_model=PersonalizedTaskResponse)
async def personalized_task(
    req: PersonalizedTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    concepts = await fetch_mastery(req.student_id, req.course_id)

    weak_concepts = [c for c in concepts if c.mastery < req.mastery_threshold][: req.max_concepts]

    if not weak_concepts:
        raise HTTPException(status_code=200, detail="Все концепты освоены — новых заданий нет.")

    all_tasks: list[TaskResponse] = []

    for concept in weak_concepts:
        target_difficulty, _ = await select_optimal_difficulty(
            db, req.student_id, concept.concept_id, concept.mastery
        )

        selected = await _pick_approved_tasks(
            db,
            student_id=req.student_id,
            course_id=req.course_id,
            concept_id=concept.concept_id,
            target_difficulty=target_difficulty,
            count=req.variants_per_concept,
        )

        if not selected:
            logger.warning(
                "No approved tasks in bank for concept=%s difficulty=%s student=%s",
                concept.concept_name, target_difficulty, req.student_id,
            )
            continue

        for task in selected:
            all_tasks.append(TaskResponse(
                id=task.id,
                concept_id=concept.concept_id,
                concept_name=concept.concept_name,
                spec=TaskSpec.model_validate(task.json_spec),
            ))

    if not all_tasks:
        raise HTTPException(
            status_code=404,
            detail="Нет одобренных заданий для ваших слабых концептов. Обратитесь к преподавателю.",
        )

    return PersonalizedTaskResponse(tasks=all_tasks)


async def _count_attempts_in_current_cycle(
    db: AsyncSession, task_id: int, student_id: int
) -> int:
    """Count failed attempts in the current retry cycle.
    A cycle starts fresh after a successful attempt."""
    last_correct_at = await db.scalar(
        select(func.max(TaskAttempt.created_at)).where(
            TaskAttempt.task_id == task_id,
            TaskAttempt.student_id == student_id,
            TaskAttempt.score >= MASTERY_PASSED,
        )
    )
    cutoff = last_correct_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
    failed = await db.scalar(
        select(func.count(TaskAttempt.id)).where(
            TaskAttempt.task_id == task_id,
            TaskAttempt.student_id == student_id,
            TaskAttempt.score < MASTERY_PASSED,
            TaskAttempt.created_at > cutoff,
        )
    )
    return int(failed or 0)


@router.post("/check-answer", response_model=CheckAnswerResponse)
async def check_answer(
    req: CheckAnswerRequest,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(GeneratedTask, req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено.")

    result = await check_chain.ainvoke({
        "task_spec": task.json_spec,
        "student_answer": req.answer,
    })

    score = float(result.get("score", 0.0))
    correct = bool(result.get("correct", score >= MASTERY_PASSED))
    llm_explanation = str(result.get("explanation", ""))

    # Attempt number within the current cycle (1 for first try, 2 for retry, ...)
    prior_failed = await _count_attempts_in_current_cycle(db, task.id, req.student_id)
    attempt_no = prior_failed + 1

    difficulty = task.difficulty or (task.json_spec.get("difficulty", "medium") if task.json_spec else "medium")
    db.add(TaskAttempt(
        task_id=task.id,
        student_id=req.student_id,
        concept_id=task.concept_id,
        difficulty=difficulty,
        score=score,
        attempt_no=attempt_no,
    ))
    await db.commit()

    # Mastery is updated only at the end of a cycle to avoid double-penalty
    is_final = correct or attempt_no >= MAX_ATTEMPTS
    if is_final:
        await push_mastery_update(
            student_id=req.student_id,
            course_id=task.course_id,
            concept_id=task.concept_id,
            score=score,
        )

    spec_explanation = (task.json_spec or {}).get("explanation") or llm_explanation

    if correct:
        return CheckAnswerResponse(
            score=score, correct=True, attempt_no=attempt_no, can_retry=False,
            hint=None, explanation=spec_explanation,
        )

    if attempt_no < MAX_ATTEMPTS:
        hint = (task.json_spec or {}).get("hint") or FALLBACK_HINT
        return CheckAnswerResponse(
            score=score, correct=False, attempt_no=attempt_no, can_retry=True,
            hint=hint, explanation=None,
        )

    return CheckAnswerResponse(
        score=score, correct=False, attempt_no=attempt_no, can_retry=False,
        hint=None, explanation=spec_explanation,
    )
