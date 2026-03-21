import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ingestor import reindex_course
from app.models import AssistantLog, CourseChunk
from app.schemas import ReindexResponse

logger = logging.getLogger(__name__)
admin_router = APIRouter(prefix="/v1/admin", tags=["admin"])


@admin_router.post("/reindex-course", response_model=ReindexResponse)
async def reindex(course_id: int = Query(..., gt=0), db: AsyncSession = Depends(get_db)):
    try:
        count = await reindex_course(course_id, db)
    except Exception as e:
        logger.error("Reindex failed for course_id=%d: %s", course_id, e)
        raise HTTPException(status_code=502, detail=f"Reindex failed: {e}")

    return ReindexResponse(
        course_id=course_id,
        chunks_created=count,
        message=f"Successfully indexed {count} chunks for course {course_id}",
    )


@admin_router.get("/index-stats")
async def index_stats(course_id: int = Query(..., gt=0), db: AsyncSession = Depends(get_db)):
    chunk_count = await db.scalar(select(func.count()).where(CourseChunk.course_id == course_id))
    log_count   = await db.scalar(select(func.count()).where(AssistantLog.course_id == course_id))
    return {"course_id": course_id, "chunks_indexed": chunk_count, "total_questions_asked": log_count}


@admin_router.get("/logs")
async def get_logs(
    course_id: int = Query(..., gt=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AssistantLog)
        .where(AssistantLog.course_id == course_id)
        .order_by(AssistantLog.ts.desc())
        .limit(limit)
    )
    return [
        {
            "id": log.id,
            "ts": log.ts.isoformat() if log.ts else None,
            "student_id": log.student_id,
            "question": log.question,
            "answer": log.answer,
        }
        for log in result.scalars().all()
    ]
