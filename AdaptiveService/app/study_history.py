"""Fetch studied cmids from TrackingService DB to exclude from recommendations."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

TRACKING_DB_URL = os.getenv("TRACKING_DB_URL", "")
PASS_THRESHOLD = 0.7

_SCORED_EVENTS = ("quiz_attempt_submitted", "assign_submission_graded")
_VIEW_EVENTS = ("course_module_viewed", "lesson_page_view")
# Types where simple view = studied (no other completion signal exists).
# `lesson` is intentionally absent: it's "studied" only via `lesson_completed`.
_VIEW_STUDIED_TYPES = ("page", "book")


async def fetch_studied_cmids(
    student_id: int,
    course_id: int,
    item_types: dict[int, str],
) -> set[int]:
    """Return cmids the student has completed and shouldn't be recommended again.

    Rules:
    - Scored event (quiz/assign) with score/max_score >= 0.7 → studied
    - lesson_completed event → studied
    - course_module_viewed / lesson_page_view for page/book → studied (no other signal)
    - lesson view alone (no lesson_completed) → NOT studied (student saw but didn't finish)
    - Failed scored attempts (< 0.7) → NOT studied (eligible for retry)

    On any DB failure returns empty set so recommendations still work.
    """
    if not TRACKING_DB_URL:
        return set()

    try:
        import asyncpg
        conn = await asyncpg.connect(TRACKING_DB_URL)
    except Exception as exc:
        logger.warning("Cannot connect to TrackingService DB: %s", exc)
        return set()

    try:
        rows = await conn.fetch(
            """SELECT cmid, event_type, payload
               FROM events
               WHERE student_id=$1 AND course_id=$2 AND cmid IS NOT NULL""",
            student_id, course_id,
        )
    except Exception as exc:
        logger.warning("Failed to query studied cmids: %s", exc)
        return set()
    finally:
        await conn.close()

    return _classify(rows, item_types)


def _classify(rows, item_types: dict[int, str]) -> set[int]:
    """Pure-function classifier — separated from DB calls for testability.

    For scored content (quiz/assign/lesson) we track the BEST observed score
    per cmid: a single failed attempt does not block forever if a later
    attempt passed.
    """
    import json

    best_score: dict[int, float] = {}
    viewed: set[int] = set()

    for row in rows:
        cmid = int(row["cmid"])
        et = row["event_type"]
        raw_payload = row["payload"]
        if isinstance(raw_payload, str):
            try:
                payload = json.loads(raw_payload)
            except Exception:
                payload = {}
        else:
            payload = raw_payload or {}

        if et in _SCORED_EVENTS:
            score = float(payload.get("score") or 0)
            max_score = float(payload.get("max_score") or 1) or 1
            ratio = score / max_score
            best_score[cmid] = max(best_score.get(cmid, 0.0), ratio)
        elif et == "lesson_completed":
            num_q = int(payload.get("num_questions") or 0)
            num_c = int(payload.get("num_correct") or 0)
            if num_q == 0:
                # Lesson without questions — completion alone is success
                ratio = 1.0
            else:
                ratio = num_c / num_q
            best_score[cmid] = max(best_score.get(cmid, 0.0), ratio)
        elif et in _VIEW_EVENTS:
            if item_types.get(cmid) in _VIEW_STUDIED_TYPES:
                viewed.add(cmid)

    studied = {cmid for cmid, s in best_score.items() if s >= PASS_THRESHOLD}
    studied |= viewed
    return studied
