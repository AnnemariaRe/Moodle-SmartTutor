from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AssessmentMap,
    ContentItem,
    StudentConceptMastery,
    StudentConceptStats,
)

logger = logging.getLogger(__name__)

_ITEM_TYPES = ["page", "quiz", "assign", "lesson", "book"]
_DIFF_BUCKETS = ["diff_easy", "diff_medium", "diff_hard"]

IMPLICIT_EVENT_WEIGHTS: dict[str, float] = {
    "page_viewed": 0.10,
    "resource_viewed": 0.15,
    "video_watched": 0.20,
    "lesson_answer_submitted": 0.25,
}

_IMPLICIT_QUERY = """
SELECT student_id, cmid, event_type, ts
FROM events
WHERE course_id = %(course_id)s
  AND event_type = ANY(%(event_types)s)
  AND cmid IS NOT NULL
ORDER BY ts
"""

TRACKING_DB_URL = os.getenv("TRACKING_DB_URL", "")


@dataclass
class LightFMDataset:
    interactions: csr_matrix            # (n_users, n_items)
    user_features: csr_matrix           # (n_users, n_user_features)
    item_features: csr_matrix           # (n_items, n_item_features)
    user_id_map: dict[int, int]         # student_id → row index
    item_id_map: dict[int, int]         # content_item.id → col index
    cmid_map: dict[int, int]            # content_item.id → moodle_cmid
    concept_ids: list[int]              # ordered list of concept ids used in features
    # (user_idx, item_idx) → unix timestamp of the interaction; 0 if unknown
    interaction_timestamps: dict[tuple[int, int], int] = field(default_factory=dict)


async def _fetch_implicit_events(
    course_id: int,
    cmid_to_item_col: dict[int, int],  # moodle_cmid → item column index
    user_id_map: dict[int, int],       # student_id → user row index
) -> list[tuple[int, int, float, int]]:
    """Fetch implicit interaction events from TrackingService DB."""
    if not TRACKING_DB_URL:
        return []

    try:
        import asyncpg  # already in requirements via asyncpg dep
        conn = await asyncpg.connect(TRACKING_DB_URL)
    except Exception as exc:
        logger.warning("Cannot connect to TrackingService DB (%s): %s", TRACKING_DB_URL, exc)
        return []

    try:
        rows = await conn.fetch(
            """
            SELECT student_id, cmid, event_type, ts
            FROM events
            WHERE course_id = $1
              AND event_type = ANY($2::text[])
              AND cmid IS NOT NULL
            ORDER BY ts
            """,
            course_id,
            list(IMPLICIT_EVENT_WEIGHTS.keys()),
        )
    except Exception as exc:
        logger.warning("Failed to query implicit events: %s", exc)
        await conn.close()
        return []
    finally:
        await conn.close()

    results: list[tuple[int, int, float, int]] = []
    for row in rows:
        user_idx = user_id_map.get(int(row["student_id"]))
        item_col = cmid_to_item_col.get(int(row["cmid"]))
        if user_idx is None or item_col is None:
            continue
        weight = IMPLICIT_EVENT_WEIGHTS.get(row["event_type"], 0.1)
        results.append((user_idx, item_col, weight, int(row["ts"])))

    logger.info(
        "Implicit events fetched for course %s: %d events (%d students, %d items matched)",
        course_id,
        len(rows),
        len({r[0] for r in results}),
        len({r[1] for r in results}),
    )
    return results


async def prepare_lightfm_data(
    db: AsyncSession,
    course_id: int,
) -> LightFMDataset | None:
    """Build LightFMDataset for a course."""

    items = (
        await db.execute(
            select(ContentItem).where(
                ContentItem.course_id == course_id,
                ContentItem.role != "placement",
            )
        )
    ).scalars().all()

    if not items:
        logger.warning("No content items for course_id=%s", course_id)
        return None

    item_id_map: dict[int, int] = {item.id: idx for idx, item in enumerate(items)}
    cmid_map: dict[int, int] = {item.id: item.moodle_cmid for item in items}
    # moodle_cmid → column index (needed for implicit lookup)
    cmid_to_col: dict[int, int] = {item.moodle_cmid: item_id_map[item.id] for item in items}
    n_items = len(items)

    # concept_id → [(item_col_idx, weight)] — primary + secondary via assessment_map
    concept_to_items: dict[int, list[tuple[int, float]]] = {}
    for item in items:
        concept_to_items.setdefault(item.concept_id, []).append((item_id_map[item.id], 1.0))

    maps = (
        await db.execute(
            select(AssessmentMap).where(
                AssessmentMap.content_item_id.in_(list(item_id_map.keys()))
            )
        )
    ).scalars().all()
    for am in maps:
        col = item_id_map.get(am.content_item_id)
        if col is not None:
            concept_to_items.setdefault(am.concept_id, []).append((col, am.weight))

    masteries_raw = (
        await db.execute(
            select(StudentConceptMastery).where(
                StudentConceptMastery.course_id == course_id
            )
        )
    ).scalars().all()

    stats_raw = (
        await db.execute(
            select(StudentConceptStats).where(
                StudentConceptStats.course_id == course_id
            )
        )
    ).scalars().all()

    if not masteries_raw and not stats_raw:
        logger.warning("No student data for course_id=%s", course_id)
        return None

    student_ids = sorted(
        {m.student_id for m in masteries_raw} | {s.student_id for s in stats_raw}
    )
    user_id_map: dict[int, int] = {sid: idx for idx, sid in enumerate(student_ids)}
    n_users = len(user_id_map)

    mastery_dict: dict[tuple[int, int], float] = {
        (m.student_id, m.concept_id): m.mastery for m in masteries_raw
    }
    stats_dict: dict[tuple[int, int], tuple[int, int]] = {
        (s.student_id, s.concept_id): (s.num_attempts, s.num_correct) for s in stats_raw
    }

    all_concept_ids_in_items = set(concept_to_items.keys())

    # --- Mastery-based interactions (explicit) ---
    # weight = correct/attempts ratio or mastery score; ts=0 (unknown)
    interaction_acc: dict[tuple[int, int], float] = {}
    all_keys = set(mastery_dict.keys()) | set(stats_dict.keys())

    for student_id, concept_id in all_keys:
        if concept_id not in all_concept_ids_in_items:
            continue
        user_idx = user_id_map[student_id]

        attempts, correct = stats_dict.get((student_id, concept_id), (0, 0))
        mastery = mastery_dict.get((student_id, concept_id), 0.0)

        weight = (correct / attempts) if attempts > 0 else mastery
        if weight <= 0:
            continue

        for item_col, concept_weight in concept_to_items.get(concept_id, []):
            key = (user_idx, item_col)
            interaction_acc[key] = max(interaction_acc.get(key, 0.0), weight * concept_weight)

    # mastery-based interactions have no known time, store as 0
    interaction_timestamps: dict[tuple[int, int], int] = {k: 0 for k in interaction_acc}

    # --- Implicit interactions (weak signals) ---
    implicit_events = await _fetch_implicit_events(course_id, cmid_to_col, user_id_map)
    n_implicit_added = 0
    for user_idx, item_col, weight, ts in implicit_events:
        key = (user_idx, item_col)
        # Only add if no explicit signal exists for this pair
        if key not in interaction_acc:
            interaction_acc[key] = weight
            interaction_timestamps[key] = ts
            n_implicit_added += 1
        else:
            # Keep explicit weight, upgrade timestamp if available
            if interaction_timestamps.get(key, 0) == 0 and ts > 0:
                interaction_timestamps[key] = ts

    if implicit_events:
        logger.info(
            "Implicit feedback: %d new (user, item) pairs added for course %s",
            n_implicit_added, course_id,
        )

    if not interaction_acc:
        logger.warning("Zero interactions built for course_id=%s", course_id)
        return None

    rows_idx, cols_idx, data = zip(
        *[(r, c, v) for (r, c), v in interaction_acc.items()]
    )
    interactions = csr_matrix(
        (data, (rows_idx, cols_idx)), shape=(n_users, n_items), dtype=np.float32
    )

    # --- Item features ---
    all_concept_ids = sorted(all_concept_ids_in_items)
    concept_feat_idx = {cid: i for i, cid in enumerate(all_concept_ids)}
    n_concept_feats = len(all_concept_ids)
    n_item_features = len(_ITEM_TYPES) + len(_DIFF_BUCKETS) + n_concept_feats

    if_rows, if_cols, if_data = [], [], []

    for item in items:
        row = item_id_map[item.id]
        type_col = _ITEM_TYPES.index(item.type) if item.type in _ITEM_TYPES else 0
        if_rows.append(row); if_cols.append(type_col); if_data.append(1.0)
        if item.difficulty < 0.4:
            diff_col = len(_ITEM_TYPES)
        elif item.difficulty < 0.7:
            diff_col = len(_ITEM_TYPES) + 1
        else:
            diff_col = len(_ITEM_TYPES) + 2
        if_rows.append(row); if_cols.append(diff_col); if_data.append(1.0)
        c_off = len(_ITEM_TYPES) + len(_DIFF_BUCKETS)
        if item.concept_id in concept_feat_idx:
            if_rows.append(row)
            if_cols.append(c_off + concept_feat_idx[item.concept_id])
            if_data.append(1.0)

    c_off = len(_ITEM_TYPES) + len(_DIFF_BUCKETS)
    for am in maps:
        col = item_id_map.get(am.content_item_id)
        if col is not None and am.concept_id in concept_feat_idx:
            if_rows.append(col)
            if_cols.append(c_off + concept_feat_idx[am.concept_id])
            if_data.append(float(am.weight))

    item_features = csr_matrix(
        (if_data, (if_rows, if_cols)),
        shape=(n_items, n_item_features),
        dtype=np.float32,
    )

    # --- User features ---
    from app.dkt import get_dkt_predictions

    n_user_features = n_concept_feats * 3  # mastery + fail_rate + kt_pred
    uf_rows, uf_cols, uf_data = [], [], []

    for student_id, user_idx in user_id_map.items():
        student_stats = {
            cid: stats_dict.get((student_id, cid), (0, 0))
            for cid in concept_feat_idx
        }
        dkt_preds = get_dkt_predictions(student_stats, course_id)

        for cid, c_idx in concept_feat_idx.items():
            mastery = mastery_dict.get((student_id, cid), 0.0)
            attempts, correct = student_stats[cid]
            fail_rate = 1.0 - (correct / attempts) if attempts > 0 else 0.0
            kt_pred = dkt_preds.get(cid, mastery) if dkt_preds else mastery

            if mastery > 0:
                uf_rows.append(user_idx); uf_cols.append(c_idx); uf_data.append(mastery)
            if fail_rate > 0:
                uf_rows.append(user_idx)
                uf_cols.append(n_concept_feats + c_idx)
                uf_data.append(fail_rate)
            if kt_pred > 0:
                uf_rows.append(user_idx)
                uf_cols.append(n_concept_feats * 2 + c_idx)
                uf_data.append(kt_pred)

    user_features = (
        csr_matrix((uf_data, (uf_rows, uf_cols)), shape=(n_users, n_user_features), dtype=np.float32)
        if uf_data
        else csr_matrix((n_users, n_user_features), dtype=np.float32)
    )

    n_implicit_total = sum(1 for ts in interaction_timestamps.values() if ts > 0)
    logger.info(
        "LightFM dataset: course=%s users=%d items=%d interactions=%d "
        "(explicit=%d implicit=%d)",
        course_id, n_users, n_items, interactions.nnz,
        interactions.nnz - n_implicit_total, n_implicit_total,
    )

    return LightFMDataset(
        interactions=interactions,
        user_features=user_features,
        item_features=item_features,
        user_id_map=user_id_map,
        item_id_map=item_id_map,
        cmid_map=cmid_map,
        concept_ids=all_concept_ids,
        interaction_timestamps=interaction_timestamps,
    )
