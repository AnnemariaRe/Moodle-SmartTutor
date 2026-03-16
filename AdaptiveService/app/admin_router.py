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
from app.models import AssessmentMap, Concept, ConceptPrereq, ContentItem, StudentConceptMastery, StudentConceptStats
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
    """Replace the knowledge graph for a course from a JSON payload.
    Concepts are referenced by name (natural key within a course).
    """
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
