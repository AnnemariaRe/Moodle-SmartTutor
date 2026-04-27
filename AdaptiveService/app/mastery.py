import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_adaptive_db_session
from app.models import AssessmentMap, ContentItem, StudentConceptMastery, StudentConceptStats

logger = logging.getLogger(__name__)


async def handle_event(event: dict) -> None:
    event_type = event.get("event_type")
    handler = {
        "quiz_attempt_submitted": _handle_quiz,
        "assign_submission_graded": _handle_assign,
        "lesson_completed": _handle_lesson_completed,
        "lesson_answer_submitted": _handle_lesson_answer,
    }.get(event_type)
    if handler:
        await handler(event)
    else:
        logger.debug("Ignoring event_type=%s", event_type)


async def _handle_quiz(event: dict) -> None:
    p = event.get("payload", {})
    score = float(p.get("score", 0.0))
    max_score = float(p.get("max_score", 1.0))
    await _process_scored_event(event, score / max_score if max_score > 0 else 0.0)


async def _handle_assign(event: dict) -> None:
    p = event.get("payload", {})
    grade = float(p.get("grade", 0.0))
    max_grade = float(p.get("max_grade", 1.0))
    await _process_scored_event(event, grade / max_grade if max_grade > 0 else 0.0)


async def _handle_lesson_completed(event: dict) -> None:
    p = event.get("payload", {})
    num_q = int(p.get("num_questions", 0))
    num_c = int(p.get("num_correct", 0))
    rel_score = num_c / num_q if num_q > 0 else float(p.get("score_percent", 0.0)) / 100.0
    await _process_scored_event(event, rel_score)


async def _handle_lesson_answer(event: dict) -> None:
    """Per-question micro-update: 10% weight so individual answers nudge mastery gently."""
    p = event.get("payload", {})
    rel_score = 1.0 if p.get("is_correct") else 0.0
    student_id = event["student_id"]
    course_id = event["course_id"]
    cmid = event.get("cmid")
    async with get_adaptive_db_session() as db:
        concept_weights, role = await _concept_weights_for_cmid(db, course_id, cmid)
        if not concept_weights:
            return
        for concept_id, weight in concept_weights.items():
            await _update_mastery(db, student_id, course_id, concept_id, rel_score, weight * 0.1, role)
        await db.commit()


async def _process_scored_event(event: dict, rel_score: float) -> None:
    student_id = event["student_id"]
    course_id = event["course_id"]
    cmid = event.get("cmid")
    async with get_adaptive_db_session() as db:
        concept_weights, role = await _concept_weights_for_cmid(db, course_id, cmid)
        if not concept_weights:
            logger.debug("No content_item for cmid=%s course_id=%s — skipping", cmid, course_id)
            return
        for concept_id, weight in concept_weights.items():
            await _update_mastery(db, student_id, course_id, concept_id, rel_score, weight, role)
        if role != "placement":
            is_correct = rel_score >= 0.7
            for concept_id in concept_weights:
                await _update_concept_stats(db, student_id, course_id, concept_id, is_correct)
        await db.commit()


async def _concept_weights_for_cmid(
    db: AsyncSession, course_id: int, cmid: int | None
) -> tuple[dict[int, float], str]:
    if cmid is None:
        return {}, "regular"
    item = (
        await db.execute(
            select(ContentItem).where(
                ContentItem.course_id == course_id,
                ContentItem.moodle_cmid == cmid,
            )
        )
    ).scalars().first()
    if not item:
        return {}, "regular"
    weights: dict[int, float] = {item.concept_id: 1.0}
    for am in (
        await db.execute(select(AssessmentMap).where(AssessmentMap.content_item_id == item.id))
    ).scalars().all():
        weights[am.concept_id] = am.weight
    return weights, item.role


async def _update_concept_stats(
    db: AsyncSession, student_id: int, course_id: int, concept_id: int, is_correct: bool
) -> None:
    stats = (
        await db.execute(
            select(StudentConceptStats).where(
                StudentConceptStats.student_id == student_id,
                StudentConceptStats.course_id == course_id,
                StudentConceptStats.concept_id == concept_id,
            )
        )
    ).scalars().first()
    now = datetime.now(timezone.utc)
    if stats is None:
        db.add(StudentConceptStats(
            student_id=student_id,
            course_id=course_id,
            concept_id=concept_id,
            num_attempts=1,
            num_correct=1 if is_correct else 0,
            last_attempt_at=now,
            updated_at=now,
        ))
    else:
        stats.num_attempts += 1
        if is_correct:
            stats.num_correct += 1
        stats.last_attempt_at = now
        stats.updated_at = now


async def _update_mastery(
    db: AsyncSession,
    student_id: int,
    course_id: int,
    concept_id: int,
    rel_score: float,
    weight: float,
    role: str = "regular",
) -> None:
    scm = (
        await db.execute(
            select(StudentConceptMastery).where(
                StudentConceptMastery.student_id == student_id,
                StudentConceptMastery.course_id == course_id,
                StudentConceptMastery.concept_id == concept_id,
            )
        )
    ).scalars().first()
    if scm is None:
        scm = StudentConceptMastery(
            student_id=student_id,
            course_id=course_id,
            concept_id=concept_id,
            mastery=0.0,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(scm)

    old = scm.mastery
    if role == "placement":
        # Placement test: set mastery directly from score (no EMA)
        new_mastery = round(min(1.0, rel_score * weight), 4)
    else:
        # Continuous target: mastery asymptotically follows rel_score.
        target = rel_score
        if old == 0.0:
            # First evidence — adopt target directly so a strong first attempt
            # doesn't get diluted to half by EMA cold-start.
            new_mastery = round(min(1.0, target * weight), 4)
        else:
            # Subsequent attempts: EMA smooths out noisy attempts.
            new_mastery = round(max(0.0, min(1.0, old + weight * (target - old) * 0.5)), 4)

    logger.info(
        "Mastery: student=%s concept=%s  %.2f → %.2f  (score=%.2f role=%s)",
        student_id, concept_id, old, new_mastery, rel_score, role,
    )
    scm.mastery = new_mastery
    scm.updated_at = datetime.now(timezone.utc)
