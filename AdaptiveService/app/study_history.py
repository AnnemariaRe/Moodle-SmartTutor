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
    """Pure-function classifier — separated from DB calls for testability."""
    studied: set[int] = set()
    failed: set[int] = set()

    for row in rows:
        cmid = int(row["cmid"])
        et = row["event_type"]
        raw_payload = row["payload"]
        # asyncpg may return JSONB as str or dict depending on codec; normalise
        if isinstance(raw_payload, str):
            import json
            try:
                payload = json.loads(raw_payload)
            except Exception:
                payload = {}
        else:
            payload = raw_payload or {}

        if et in _SCORED_EVENTS:
            score = float(payload.get("score") or 0)
            max_score = float(payload.get("max_score") or 1) or 1
            if score / max_score >= PASS_THRESHOLD:
                studied.add(cmid)
            else:
                failed.add(cmid)
        elif et == "lesson_completed":
            studied.add(cmid)
        elif et in _VIEW_EVENTS:
            if item_types.get(cmid) in _VIEW_STUDIED_TYPES:
                studied.add(cmid)

    # Failed quiz/assign overrides any prior viewing — student should retry
    return studied - failed
