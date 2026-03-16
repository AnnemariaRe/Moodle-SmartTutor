"""
Prepare sparse matrices for LightFM training from AdaptiveService DB.

Interaction weight per (student, content_item):
  - If student has attempt stats for the concept → weight = num_correct / num_attempts
  - Else if student has mastery (e.g., from placement test) → weight = mastery
  - Items are linked to students via concept: content_item.concept_id matches
    the concept the student interacted with.

User features (per student):
  - mastery_c{X}: mastery for concept X
  - fail_rate_c{X}: 1 - num_correct/num_attempts for concept X
  - kt_pred_c{X}: P(correct) from DKT model (if available, else same as mastery)

Item features (per content_item):
  - type one-hot: type_page, type_quiz, type_assign, type_lesson, type_book
  - difficulty bucket: diff_easy (<0.4), diff_medium (0.4–0.7), diff_hard (>0.7)
  - concept membership: concept_c{X} = 1.0 for primary, weight for secondary (assessment_map)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

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


@dataclass
class LightFMDataset:
    interactions: csr_matrix       # (n_users, n_items)
    user_features: csr_matrix      # (n_users, n_user_features)
    item_features: csr_matrix      # (n_items, n_item_features)
    user_id_map: dict[int, int]    # student_id → row index
    item_id_map: dict[int, int]    # content_item.id → col index
    cmid_map: dict[int, int]       # content_item.id → moodle_cmid
    concept_ids: list[int]         # ordered list of concept ids used in features


async def prepare_lightfm_data(
    db: AsyncSession,
    course_id: int,
) -> LightFMDataset | None:
    """Build LightFMDataset for a course. Returns None if not enough data."""

    # Content items (columns)
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

    # Student data
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

    # Interaction matrix
    all_concept_ids_in_items = set(concept_to_items.keys())

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

    if not interaction_acc:
        logger.warning("Zero interactions built for course_id=%s", course_id)
        return None

    rows, cols, data = zip(*[(r, c, v) for (r, c), v in interaction_acc.items()])
    interactions = csr_matrix((data, (rows, cols)), shape=(n_users, n_items), dtype=np.float32)

    # Item features
    all_concept_ids = sorted(all_concept_ids_in_items)
    concept_feat_idx = {cid: i for i, cid in enumerate(all_concept_ids)}
    n_concept_feats = len(all_concept_ids)
    n_item_features = len(_ITEM_TYPES) + len(_DIFF_BUCKETS) + n_concept_feats

    if_rows, if_cols, if_data = [], [], []

    for item in items:
        row = item_id_map[item.id]
        # type one-hot
        type_col = _ITEM_TYPES.index(item.type) if item.type in _ITEM_TYPES else 0
        if_rows.append(row); if_cols.append(type_col); if_data.append(1.0)
        # difficulty bucket
        if item.difficulty < 0.4:
            diff_col = len(_ITEM_TYPES)
        elif item.difficulty < 0.7:
            diff_col = len(_ITEM_TYPES) + 1
        else:
            diff_col = len(_ITEM_TYPES) + 2
        if_rows.append(row); if_cols.append(diff_col); if_data.append(1.0)
        # primary concept
        c_off = len(_ITEM_TYPES) + len(_DIFF_BUCKETS)
        if item.concept_id in concept_feat_idx:
            if_rows.append(row)
            if_cols.append(c_off + concept_feat_idx[item.concept_id])
            if_data.append(1.0)

    # secondary concepts from assessment_map
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

    # User features
    # [mastery_c0 ... | fail_rate_c0 ... | kt_pred_c0 ...]
    # kt_pred block: DKT predictions if model available, else copy of mastery
    from app.dkt import get_dkt_predictions

    n_user_features = n_concept_feats * 3  # mastery + fail_rate + kt_pred
    uf_rows, uf_cols, uf_data = [], [], []

    for student_id, user_idx in user_id_map.items():
        student_stats = {
            cid: stats_dict.get((student_id, cid), (0, 0))
            for cid in concept_feat_idx
        }
        # DKT predictions for this student (None → fallback to mastery)
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

    logger.info(
        "LightFM dataset: course=%s users=%d items=%d interactions=%d",
        course_id, n_users, n_items, interactions.nnz,
    )
    return LightFMDataset(
        interactions=interactions,
        user_features=user_features,
        item_features=item_features,
        user_id_map=user_id_map,
        item_id_map=item_id_map,
        cmid_map=cmid_map,
        concept_ids=all_concept_ids,
    )
