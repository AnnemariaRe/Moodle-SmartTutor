import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adaptive_client import fetch_all_concepts
from app.chains import generate_tasks_for_bank
from app.database import get_db
from app.models import GeneratedTask
from app.schemas import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    BulkReviewRequest,
    TaskBankItem,
    TaskBankListResponse,
    TaskReviewRequest,
    TaskReviewResponse,
)

router = APIRouter(prefix="/v1/admin")
logger = logging.getLogger(__name__)

DIFFICULTY_ORDER = ["easy", "medium", "hard"]


@router.post("/generate-bank", response_model=BatchGenerateResponse)
async def generate_bank(
    req: BatchGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a batch of tasks for all concepts of a course."""
    concepts = await fetch_all_concepts(req.course_id)
    if not concepts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No concepts found for course_id={req.course_id}. Add concepts to AdaptiveService first.",
        )

    difficulties = req.difficulties or DIFFICULTY_ORDER
    variants_per_difficulty = max(1, req.tasks_per_concept // len(difficulties))
    batch_id = str(uuid.uuid4())
    total_tasks = 0

    for concept in concepts:
        concept_id = concept["id"]
        concept_name = concept["name"]

        for difficulty in difficulties:
            specs = await generate_tasks_for_bank(
                concept_name=concept_name,
                difficulty=difficulty,
                variants=variants_per_difficulty,
                teacher_instructions=req.teacher_instructions,
            )
            for spec in specs:
                db.add(GeneratedTask(
                    course_id=req.course_id,
                    concept_id=concept_id,
                    concept_name=concept_name,
                    difficulty=difficulty,
                    json_spec=spec.model_dump(),
                    status="pending_review",
                    teacher_id=req.teacher_id,
                    teacher_instructions=req.teacher_instructions,
                    batch_id=batch_id,
                ))
                total_tasks += 1

    await db.commit()
    logger.info(
        "Generated bank batch=%s course=%s concepts=%d tasks=%d",
        batch_id, req.course_id, len(concepts), total_tasks,
    )
    return BatchGenerateResponse(
        batch_id=batch_id,
        total_tasks=total_tasks,
        concepts_covered=len(concepts),
    )


@router.get("/bank", response_model=TaskBankListResponse)
async def list_bank(
    course_id: int,
    status: Optional[str] = None,
    concept_id: Optional[int] = None,
    batch_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List tasks in the bank with optional filters."""
    query = select(GeneratedTask).where(GeneratedTask.course_id == course_id)
    if status:
        query = query.where(GeneratedTask.status == status)
    if concept_id is not None:
        query = query.where(GeneratedTask.concept_id == concept_id)
    if batch_id:
        query = query.where(GeneratedTask.batch_id == batch_id)
    query = query.order_by(GeneratedTask.concept_id, GeneratedTask.difficulty, GeneratedTask.id)

    result = await db.execute(query)
    tasks = result.scalars().all()

    items = [
        TaskBankItem(
            id=t.id,
            concept_id=t.concept_id,
            concept_name=t.concept_name,
            difficulty=t.difficulty or "",
            spec=t.json_spec,
            status=t.status,
            created_at=t.created_at,
        )
        for t in tasks
    ]
    return TaskBankListResponse(tasks=items, total=len(items))


@router.post("/review", response_model=TaskReviewResponse)
async def review_task(
    req: TaskReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a single task, optionally with edited spec."""
    if req.action not in ("approve", "reject"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="action must be 'approve' or 'reject'")

    task = await db.get(GeneratedTask, req.task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if req.edited_spec is not None:
        task.json_spec = req.edited_spec.model_dump()
        # sync difficulty column if it was changed in the spec
        if req.edited_spec.difficulty:
            task.difficulty = req.edited_spec.difficulty

    task.status = "approved" if req.action == "approve" else "rejected"
    task.reviewed_by = req.reviewed_by
    task.reviewed_at = datetime.now(timezone.utc)
    await db.commit()

    return TaskReviewResponse(id=task.id, status=task.status)


@router.post("/review-bulk", response_model=list[TaskReviewResponse])
async def review_bulk(
    req: BulkReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject multiple tasks at once."""
    if req.action not in ("approve", "reject"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="action must be 'approve' or 'reject'")

    result = await db.execute(
        select(GeneratedTask).where(GeneratedTask.id.in_(req.task_ids))
    )
    tasks = result.scalars().all()

    new_status = "approved" if req.action == "approve" else "rejected"
    now = datetime.now(timezone.utc)
    responses = []
    for task in tasks:
        task.status = new_status
        task.reviewed_by = req.reviewed_by
        task.reviewed_at = now
        responses.append(TaskReviewResponse(id=task.id, status=new_status))

    await db.commit()
    return responses


@router.delete("/batch/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete all tasks from a generation batch."""
    await db.execute(
        delete(GeneratedTask).where(GeneratedTask.batch_id == batch_id)
    )
    await db.commit()
