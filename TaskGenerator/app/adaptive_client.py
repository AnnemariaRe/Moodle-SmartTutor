import logging
from typing import List

import httpx

from app.schemas import ConceptMastery
from app.settings import settings

logger = logging.getLogger(__name__)


async def fetch_mastery(student_id: int, course_id: int) -> List[ConceptMastery]:
    async with httpx.AsyncClient(base_url=settings.adaptive_url, timeout=10.0) as client:
        resp = await client.get("/v1/state", params={"student_id": student_id, "course_id": course_id})
        resp.raise_for_status()
        data = resp.json()
        return [ConceptMastery.model_validate(c) for c in data["state"]]


async def push_mastery_update(
    student_id: int,
    course_id: int,
    concept_id: int,
    score: float,
) -> None:
    async with httpx.AsyncClient(base_url=settings.adaptive_url, timeout=10.0) as client:
        try:
            resp = await client.post(
                "/v1/internal/mastery-update",
                json={
                    "student_id": student_id,
                    "course_id": course_id,
                    "concept_id": concept_id,
                    "score": score,
                },
            )
            resp.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to push mastery update: student=%s concept=%s score=%.2f",
                student_id, concept_id, score,
            )
