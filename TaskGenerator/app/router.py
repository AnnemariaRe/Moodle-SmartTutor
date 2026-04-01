import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adaptive_client import fetch_mastery, push_mastery_update
from app.chains import check_chain, generate_tasks
from app.database import get_db
from app.models import GeneratedTask, TaskAttempt
from app.schemas import (
    CheckAnswerRequest,
    CheckAnswerResponse,
    PersonalizedTaskRequest,
    PersonalizedTaskResponse,
    TaskResponse,
)

router = APIRouter(prefix="/v1")
logger = logging.getLogger(__name__)


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
        specs = await generate_tasks(
            concept_name=concept.concept_name,
            mastery=concept.mastery,
            student_id=req.student_id,
            concept_id=concept.concept_id,
            db=db,
            variants=req.variants_per_concept,
        )
        if not specs:
            logger.warning("No specs generated for concept '%s'", concept.concept_name)
            continue

        for spec in specs:
            task = GeneratedTask(
                student_id=req.student_id,
                course_id=req.course_id,
                concept_id=concept.concept_id,
                concept_name=concept.concept_name,
                json_spec=spec.model_dump(),
                status="draft",
            )
            db.add(task)
            await db.flush()
            all_tasks.append(
                TaskResponse(
                    id=task.id,
                    concept_id=concept.concept_id,
                    concept_name=concept.concept_name,
                    spec=spec,
                )
            )

    await db.commit()

    if not all_tasks:
        raise HTTPException(status_code=500, detail="Не удалось сгенерировать задания.")

    return PersonalizedTaskResponse(tasks=all_tasks)


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
    correct = bool(result.get("correct", score >= 0.7))
    explanation = str(result.get("explanation", ""))

    # Mark task as used and record attempt for BKT history
    task.status = "used"
    difficulty = task.json_spec.get("difficulty", "medium") if task.json_spec else "medium"
    db.add(
        TaskAttempt(
            task_id=task.id,
            student_id=task.student_id,
            concept_id=task.concept_id,
            difficulty=difficulty,
            score=score,
        )
    )
    await db.commit()

    await push_mastery_update(
        student_id=task.student_id,
        course_id=task.course_id,
        concept_id=task.concept_id,
        score=score,
    )

    return CheckAnswerResponse(score=score, correct=correct, explanation=explanation)
