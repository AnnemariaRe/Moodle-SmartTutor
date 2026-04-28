import os
import pathlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dkt import MODEL_DIR as DKT_DIR
from app.graph_builder import auto_extract_graph
from app.lightfm_model import model_path as lfm_path
from app.models import AssessmentMap, Concept, ConceptPrereq, ContentItem, RecommendationLog, StudentConceptMastery, StudentConceptStats
from app.schemas import (
    AdminGraphOut,
    AssessmentMapOut,
    ConceptOut,
    ConceptPrereqOut,
    ContentItemOut,
    GraphImport,
    PlacementTestOut,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

MOODLE_URL = os.getenv("MOODLE_URL", "http://moodle:8080")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")


@router.post("/graph/auto-extract")
async def auto_extract(
    course_id: int,
    replace_drafts: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Fetch course content from Moodle, extract concepts via LLM, build graph."""
    if not MOODLE_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MOODLE_TOKEN env var is not set")
    return await auto_extract_graph(
        db=db,
        course_id=course_id,
        moodle_url=MOODLE_URL,
        moodle_token=MOODLE_TOKEN,
        replace_drafts=replace_drafts,
    )


@router.get("/graph", response_model=AdminGraphOut)
async def get_graph(course_id: int, db: AsyncSession = Depends(get_db)):
    concepts = (await db.execute(select(Concept).where(Concept.course_id == course_id))).scalars().all()
    concept_ids = [c.id for c in concepts]
    prereqs = (await db.execute(select(ConceptPrereq).where(ConceptPrereq.concept_id.in_(concept_ids)))).scalars().all()
    items = (await db.execute(select(ContentItem).where(ContentItem.course_id == course_id))).scalars().all()
    item_ids = [i.id for i in items]
    maps = (
        (await db.execute(select(AssessmentMap).where(AssessmentMap.content_item_id.in_(item_ids)))).scalars().all()
        if item_ids else []
    )
    return AdminGraphOut(
        course_id=course_id,
        concepts=[ConceptOut.model_validate(c) for c in concepts],
        prereqs=[ConceptPrereqOut.model_validate(p) for p in prereqs],
        content_items=[ContentItemOut.model_validate(i) for i in items],
        assessment_maps=[AssessmentMapOut.model_validate(m) for m in maps],
    )


@router.post("/graph/import", status_code=status.HTTP_204_NO_CONTENT)
async def import_graph(data: GraphImport, db: AsyncSession = Depends(get_db)):
    """Replace the knowledge graph for a course from a JSON payload."""
    course_id = data.course_id
    existing_concept_ids = (
        await db.execute(select(Concept.id).where(Concept.course_id == course_id))
    ).scalars().all()
    if existing_concept_ids:
        await db.execute(delete(ContentItem).where(ContentItem.course_id == course_id))
        await db.execute(delete(ConceptPrereq).where(ConceptPrereq.concept_id.in_(existing_concept_ids)))
        await db.execute(delete(Concept).where(Concept.course_id == course_id))
        await db.flush()

    name_to_id: dict[str, int] = {}
    for c_data in data.concepts:
        c = Concept(course_id=course_id, name=c_data.name, difficulty=c_data.difficulty, is_approved=c_data.is_approved)
        db.add(c)
        await db.flush()
        name_to_id[c_data.name.lower().strip()] = c.id

    def resolve(name: str) -> int | None:
        return name_to_id.get(name.lower().strip())

    for p in data.prereqs:
        cid, pid = resolve(p.concept_name), resolve(p.prereq_concept_name)
        if cid and pid:
            db.add(ConceptPrereq(concept_id=cid, prereq_concept_id=pid))

    cmid_to_item_id: dict[int, int] = {}
    for item_data in data.content_items:
        cid = resolve(item_data.concept_name)
        if not cid:
            continue
        item = ContentItem(
            course_id=course_id, moodle_cmid=item_data.moodle_cmid,
            concept_id=cid, type=item_data.type, difficulty=item_data.difficulty,
        )
        db.add(item)
        await db.flush()
        cmid_to_item_id[item_data.moodle_cmid] = item.id

    for am_data in data.assessment_maps:
        item_id = cmid_to_item_id.get(am_data.moodle_cmid)
        cid = resolve(am_data.concept_name)
        if item_id and cid:
            db.add(AssessmentMap(content_item_id=item_id, concept_id=cid, weight=am_data.weight))

    await db.commit()


@router.post("/concepts/approve-all")
async def approve_all_concepts(course_id: int, db: AsyncSession = Depends(get_db)):
    """Approve all draft concepts for a course at once."""
    result = await db.execute(
        update(Concept)
        .where(Concept.course_id == course_id, Concept.is_approved == False)  # noqa: E712
        .values(is_approved=True)
    )
    await db.commit()
    return {"approved": result.rowcount}


@router.post("/concepts/{concept_id}/approve", response_model=ConceptOut)
async def approve_concept(concept_id: int, db: AsyncSession = Depends(get_db)):
    concept = (await db.execute(select(Concept).where(Concept.id == concept_id))).scalars().first()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")
    concept.is_approved = True
    await db.commit()
    await db.refresh(concept)
    return ConceptOut.model_validate(concept)


@router.post("/concepts/{concept_id}/merge")
async def merge_concept(concept_id: int, into_id: int, db: AsyncSession = Depends(get_db)):
    """Merge concept_id into into_id: re-points all references, then deletes it."""
    if concept_id == into_id:
        raise HTTPException(status_code=400, detail="Cannot merge concept into itself")
    await db.execute(update(ContentItem).where(ContentItem.concept_id == concept_id).values(concept_id=into_id))
    await db.execute(update(AssessmentMap).where(AssessmentMap.concept_id == concept_id).values(concept_id=into_id))
    await db.execute(
        delete(ConceptPrereq).where(
            (ConceptPrereq.concept_id == concept_id) | (ConceptPrereq.prereq_concept_id == concept_id)
        )
    )
    await db.execute(delete(Concept).where(Concept.id == concept_id))
    await db.commit()
    return {"status": "ok", "merged_into": into_id}


@router.post("/placement-test", response_model=PlacementTestOut, status_code=status.HTTP_201_CREATED)
async def set_placement_test(course_id: int, cmid: int, db: AsyncSession = Depends(get_db)):
    """Mark a content item as the placement test (uses direct mastery init, not EMA)."""
    item = (
        await db.execute(
            select(ContentItem).where(ContentItem.course_id == course_id, ContentItem.moodle_cmid == cmid)
        )
    ).scalars().first()
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"No content_item for course_id={course_id} cmid={cmid}. Run auto-extract first.",
        )
    await db.execute(
        update(ContentItem)
        .where(ContentItem.course_id == course_id, ContentItem.role == "placement")
        .values(role="regular")
    )
    item.role = "placement"
    await db.commit()
    await db.refresh(item)
    return PlacementTestOut(course_id=course_id, cmid=cmid, content_item_id=item.id)


@router.get("/placement-test", response_model=PlacementTestOut)
async def get_placement_test(course_id: int, db: AsyncSession = Depends(get_db)):
    item = (
        await db.execute(
            select(ContentItem).where(ContentItem.course_id == course_id, ContentItem.role == "placement")
        )
    ).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="No placement test set for this course")
    return PlacementTestOut(course_id=course_id, cmid=item.moodle_cmid, content_item_id=item.id)


@router.delete("/placement-test", status_code=status.HTTP_204_NO_CONTENT)
async def clear_placement_test(course_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(ContentItem)
        .where(ContentItem.course_id == course_id, ContentItem.role == "placement")
        .values(role="regular")
    )
    await db.commit()


@router.get("/model-stats")
async def model_stats(course_id: int, db: AsyncSession = Depends(get_db)):
    lfm = lfm_path(course_id)
    dkt_weights = pathlib.Path(DKT_DIR) / f"dkt_weights_{course_id}.npz"

    def _mtime(p: pathlib.Path) -> str | None:
        return datetime.fromtimestamp(p.stat().st_mtime).isoformat() if p.exists() else None

    n_students = (
        await db.execute(
            select(func.count(func.distinct(StudentConceptMastery.student_id))).where(
                StudentConceptMastery.course_id == course_id
            )
        )
    ).scalar() or 0
    n_interactions = (
        await db.execute(
            select(func.coalesce(func.sum(StudentConceptStats.num_attempts), 0)).where(
                StudentConceptStats.course_id == course_id
            )
        )
    ).scalar() or 0

    return {
        "course_id": course_id,
        "lightfm_model_exists": lfm.exists(),
        "lightfm_trained_at": _mtime(lfm),
        "dkt_model_exists": dkt_weights.exists(),
        "dkt_trained_at": _mtime(dkt_weights),
        "num_students": n_students,
        "num_interactions": int(n_interactions),
    }


@router.post("/train-lightfm")
async def train_lightfm(course_id: int, epochs: int = 30, db: AsyncSession = Depends(get_db)):
    """Train LightFM hybrid recommender. Returns training stats or 'skipped' if data is insufficient."""
    from app.lightfm_data import prepare_lightfm_data
    from app.lightfm_model import train_model

    dataset = await prepare_lightfm_data(db, course_id)
    if dataset is None:
        return {"status": "skipped", "reason": "нет данных: нет контент-айтемов или взаимодействий"}
    return train_model(dataset, course_id, epochs=epochs)


@router.get("/evaluate-lightfm")
async def evaluate_lightfm(course_id: int, k: int = 5, test_size: float = 0.2):
    """Evaluate the saved LightFM model using a train/test split."""
    import joblib
    from app.lightfm_model import model_path

    path = model_path(course_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Модель для курса {course_id} не найдена. Сначала запустите /train-lightfm")

    try:
        saved = joblib.load(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки модели: {exc}")

    try:
        return await _run_lightfm_eval(saved, course_id, k, test_size)
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")


async def _run_lightfm_eval(saved: dict, course_id: int, k: int, test_size: float) -> dict:
    import numpy as np
    from lightfm import LightFM
    from lightfm.evaluation import auc_score, precision_at_k, recall_at_k
    from scipy.sparse import lil_matrix

    model = saved["model"]
    dataset = saved["dataset"]
    interactions = dataset.interactions
    n_users = interactions.shape[0]

    if n_users < 5:
        raise HTTPException(
            status_code=422,
            detail=f"Слишком мало студентов ({n_users}) для оценки. Нужно минимум 5.",
        )

    train_mat = lil_matrix(interactions.shape, dtype=interactions.dtype)
    test_mat = lil_matrix(interactions.shape, dtype=interactions.dtype)
    coo = interactions.tocoo()

    user_entries: dict[int, list[tuple[int, float, int]]] = {}
    ts_map: dict[tuple[int, int], int] = getattr(dataset, "interaction_timestamps", {})
    for i in range(coo.nnz):
        u, col, w = int(coo.row[i]), int(coo.col[i]), float(coo.data[i])
        ts = ts_map.get((u, col), 0)
        user_entries.setdefault(u, []).append((col, w, ts))

    has_temporal = any(ts > 0 for (_, _, ts) in (e for entries in user_entries.values() for e in entries))
    split_method = "temporal" if has_temporal else "random"

    rng = np.random.RandomState(42)
    for uid, entries in user_entries.items():
        if has_temporal:
            # Sort by timestamp ascending; entries with ts=0 go first (oldest)
            entries.sort(key=lambda e: e[2])
        else:
            rng.shuffle(entries)

        split = max(1, int(len(entries) * (1 - test_size)))
        for col, w, _ in entries[:split]:
            train_mat[uid, col] = w
        for col, w, _ in entries[split:]:
            test_mat[uid, col] = w

    train_interactions = train_mat.tocsr()
    test_interactions = test_mat.tocsr()

    uf = dataset.user_features if dataset.user_features is not None else None

    # Retrain on train split for unbiased evaluation
    eval_model = LightFM(
        loss=model.loss,
        no_components=model.no_components,
        learning_rate=model.learning_rate,
        item_alpha=model.item_alpha,
        user_alpha=model.user_alpha,
        random_state=42,
    )
    eval_model.fit(
        interactions=train_interactions,
        user_features=uf,
        item_features=dataset.item_features,
        epochs=30,
        num_threads=2,
        verbose=False,
    )

    p_at_k = float(precision_at_k(
        eval_model, test_interactions,
        train_interactions=train_interactions,
        user_features=uf,
        item_features=dataset.item_features,
        k=k,
    ).mean())

    r_at_k = float(recall_at_k(
        eval_model, test_interactions,
        train_interactions=train_interactions,
        user_features=uf,
        item_features=dataset.item_features,
        k=k,
    ).mean())

    auc = float(auc_score(
        eval_model, test_interactions,
        train_interactions=train_interactions,
        user_features=uf,
        item_features=dataset.item_features,
    ).mean())

    n_implicit = sum(1 for ts in ts_map.values() if ts > 0)

    return {
        "course_id": course_id,
        "k": k,
        "users": n_users,
        "train_interactions": int(train_interactions.nnz),
        "test_interactions": int(test_interactions.nnz),
        "implicit_interactions": n_implicit,
        "split_method": split_method,
        f"precision_at_{k}": round(p_at_k, 4),
        f"recall_at_{k}": round(r_at_k, 4),
        "auc": round(auc, 4),
        "interpretation": {
            f"precision_at_{k}": "хорошо ≥ 0.15, плохо < 0.05",
            f"recall_at_{k}": "хорошо ≥ 0.20, плохо < 0.10",
            "auc": "хорошо ≥ 0.75, плохо < 0.60",
            "split_method": "temporal = сортировка по времени (честнее); random = случайный (нет timestamps)",
        },
    }


@router.get("/recommendations-stats")
async def recommendations_stats(
    course_id: int,
    window_minutes: int = 30,
    db: AsyncSession = Depends(get_db),
):
    import json as _json
    import os as _os
    from datetime import timedelta

    logs = (
        await db.execute(
            select(RecommendationLog).where(RecommendationLog.course_id == course_id)
        )
    ).scalars().all()

    if not logs:
        return {"course_id": course_id, "total_logged": 0, "hits": 0, "hit_rate": 0.0,
                "by_method": {}, "note": "No recommendations logged yet."}

    # Aggregate by method
    by_method_total: dict[str, int] = {}
    by_method_hits: dict[str, int] = {}
    for log in logs:
        by_method_total[log.method] = by_method_total.get(log.method, 0) + 1

    tracking_url = _os.getenv("TRACKING_DB_URL", "")
    if not tracking_url:
        return {
            "course_id": course_id,
            "total_logged": len(logs),
            "by_method_total": by_method_total,
            "note": "TRACKING_DB_URL not set — cannot compute hits.",
        }

    try:
        import asyncpg
        conn = await asyncpg.connect(tracking_url)
    except Exception as exc:
        return {
            "course_id": course_id,
            "total_logged": len(logs),
            "by_method_total": by_method_total,
            "note": f"TrackingService DB unreachable ({exc}) — counts only.",
        }

    hits = 0
    skipped_empty = 0
    try:
        for log in logs:
            recs = _json.loads(log.recommended_cmids or "[]")
            if not recs:
                skipped_empty += 1
                continue
            window_end = log.created_at + timedelta(minutes=window_minutes)
            row = await conn.fetchrow(
                """SELECT 1 FROM events
                   WHERE student_id=$1 AND course_id=$2 AND cmid = ANY($3::int[])
                     AND to_timestamp(ts) BETWEEN $4 AND $5
                   LIMIT 1""",
                log.student_id, course_id, recs, log.created_at, window_end,
            )
            if row:
                hits += 1
                by_method_hits[log.method] = by_method_hits.get(log.method, 0) + 1
    finally:
        await conn.close()

    total_with_recs = len(logs) - skipped_empty
    hit_rate = hits / total_with_recs if total_with_recs > 0 else 0.0

    by_method = {
        m: {
            "total": by_method_total[m],
            "hits": by_method_hits.get(m, 0),
            "hit_rate": round(by_method_hits.get(m, 0) / by_method_total[m], 4) if by_method_total[m] else 0.0,
        }
        for m in by_method_total
    }

    return {
        "course_id": course_id,
        "window_minutes": window_minutes,
        "total_logged": len(logs),
        "with_recommendations": total_with_recs,
        "empty_recs": skipped_empty,
        "hits": hits,
        "hit_rate": round(hit_rate, 4),
        "by_method": by_method,
    }
