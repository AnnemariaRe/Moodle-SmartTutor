from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dkt import DKTPredictor, get_dkt_predictions
from app.lightfm_model import model_path, recommend as lightfm_recommend
from app.models import (
    AssessmentMap, Concept, ConceptPrereq, ContentItem,
    StudentConceptMastery, StudentConceptStats,
)
from app.recommendations import get_recommendations
from app.study_history import fetch_studied_cmids
from app.schemas import (
    AssessmentMapCreate,
    ConceptCreate,
    ConceptOut,
    ConceptPrereqCreate,
    ContentItemCreate,
    ContentItemOut,
    MasteryOut,
    RecommendationItem,
    RecommendationsOut,
    StudentStateOut,
)

router = APIRouter(prefix="/v1")


def _make_rec_item(item: ContentItem, concept_name: str, reason: str) -> RecommendationItem:
    return RecommendationItem(
        content_item_id=item.id,
        moodle_cmid=item.moodle_cmid,
        type=item.type,
        concept_id=item.concept_id,
        concept_name=concept_name,
        difficulty=item.difficulty,
        reason=reason,
    )


def _dedupe_by_cmid(items: list) -> list:
    seen: set[int] = set()
    result = []
    for i in items:
        if i.moodle_cmid not in seen:
            seen.add(i.moodle_cmid)
            result.append(i)
    return result


@router.post("/concepts", response_model=ConceptOut, status_code=status.HTTP_201_CREATED)
async def create_concept(data: ConceptCreate, db: AsyncSession = Depends(get_db)):
    concept = Concept(**data.model_dump())
    db.add(concept)
    await db.commit()
    await db.refresh(concept)
    return concept


@router.get("/concepts", response_model=list[ConceptOut])
async def list_concepts(course_id: int, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Concept).where(Concept.course_id == course_id))
    return rows.scalars().all()


@router.post("/concepts/prereqs", status_code=status.HTTP_201_CREATED)
async def add_prereq(data: ConceptPrereqCreate, db: AsyncSession = Depends(get_db)):
    db.add(ConceptPrereq(**data.model_dump()))
    await db.commit()
    return {"status": "ok"}


@router.post("/content-items", response_model=ContentItemOut, status_code=status.HTTP_201_CREATED)
async def create_content_item(data: ContentItemCreate, db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(
            select(ContentItem).where(
                ContentItem.course_id == data.course_id,
                ContentItem.moodle_cmid == data.moodle_cmid,
            )
        )
    ).scalars().first()
    if existing:
        for field, value in data.model_dump().items():
            setattr(existing, field, value)
        await db.commit()
        await db.refresh(existing)
        return existing
    item = ContentItem(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/content-items", response_model=list[ContentItemOut])
async def list_content_items(course_id: int, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(ContentItem).where(ContentItem.course_id == course_id))
    return rows.scalars().all()


@router.post("/assessment-maps", status_code=status.HTTP_201_CREATED)
async def add_assessment_map(data: AssessmentMapCreate, db: AsyncSession = Depends(get_db)):
    db.add(AssessmentMap(**data.model_dump()))
    await db.commit()
    return {"status": "ok"}


@router.get("/state", response_model=StudentStateOut)
async def get_student_state(
    student_id: int, course_id: int, db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(
            select(StudentConceptMastery, Concept)
            .join(Concept, StudentConceptMastery.concept_id == Concept.id)
            .where(
                StudentConceptMastery.student_id == student_id,
                StudentConceptMastery.course_id == course_id,
            )
        )
    ).all()
    state = [
        MasteryOut(
            concept_id=scm.concept_id,
            concept_name=concept.name,
            mastery=scm.mastery,
            updated_at=scm.updated_at,
        )
        for scm, concept in rows
    ]
    return StudentStateOut(student_id=student_id, course_id=course_id, state=state)


@router.get("/recommendations", response_model=RecommendationsOut)
async def get_student_recommendations(
    student_id: int,
    course_id: int,
    cmid: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    dkt_available = DKTPredictor.load(course_id) is not None
    base_features = ["ema_mastery", "attempt_stats"]
    if dkt_available:
        base_features.append("dkt_prediction")

    mastery_map: dict[int, float] = {
        m.concept_id: m.mastery
        for m in (
            await db.execute(
                select(StudentConceptMastery).where(
                    StudentConceptMastery.student_id == student_id,
                    StudentConceptMastery.course_id == course_id,
                )
            )
        ).scalars().all()
    }
    stats_map: dict[int, tuple[int, int]] = {
        s.concept_id: (s.num_attempts, s.num_correct)
        for s in (
            await db.execute(
                select(StudentConceptStats).where(
                    StudentConceptStats.student_id == student_id,
                    StudentConceptStats.course_id == course_id,
                )
            )
        ).scalars().all()
    }
    dkt_preds: dict[int, float] | None = (
        get_dkt_predictions(stats_map, course_id) if dkt_available else None
    )

    # Build cmid → type map for the course (needed by fetch_studied_cmids
    # to decide whether a "viewed" event for a non-scored type counts as studied).
    item_type_rows = (
        await db.execute(
            select(ContentItem.moodle_cmid, ContentItem.type).where(
                ContentItem.course_id == course_id,
            )
        )
    ).all()
    item_types: dict[int, str] = {row[0]: row[1] for row in item_type_rows}

    studied_cmids = await fetch_studied_cmids(student_id, course_id, item_types)
    exclude_cmids: set[int] = set(studied_cmids)
    if cmid is not None:
        exclude_cmids.add(cmid)

    ctx_meta: dict = {}

    # New student with no history (no attempts AND no mastery) → recommend placement test
    if not stats_map and not mastery_map:
        placement_item = (
            await db.execute(
                select(ContentItem).where(
                    ContentItem.course_id == course_id,
                    ContentItem.role == "placement",
                )
            )
        ).scalars().first()
        if placement_item and placement_item.visible and (cmid is None or placement_item.moodle_cmid != cmid):
            placement_concept = (
                await db.execute(select(Concept).where(Concept.id == placement_item.concept_id))
            ).scalars().first()
            pname = placement_concept.name if placement_concept else ""
            msg = "Начните с входного теста, чтобы оценить ваш уровень"
            return RecommendationsOut(
                student_id=student_id,
                course_id=course_id,
                method="rule_based",
                features_used=base_features,
                fallback_used=False,
                context="placement",
                context_message=msg,
                recommendations=[_make_rec_item(placement_item, pname, msg)],
            )

    if cmid is not None:
        current_item = (
            await db.execute(
                select(ContentItem).where(
                    ContentItem.course_id == course_id,
                    ContentItem.moodle_cmid == cmid,
                )
            )
        ).scalars().first()

        if current_item and current_item.role == "placement":
            # If student already has mastery data, placement is done — fall through
            # to normal recommendations (what to study next). Only block for brand-new students.
            if not mastery_map:
                return RecommendationsOut(
                    student_id=student_id,
                    course_id=course_id,
                    method="rule_based",
                    features_used=base_features,
                    fallback_used=False,
                    recommendations=[],
                )
            # Placement completed: recommend next unmastered concept's content
            post_placement_recs = await get_recommendations(
                db, student_id, course_id, exclude_cmids=exclude_cmids
            )
            if post_placement_recs:
                return RecommendationsOut(
                    student_id=student_id,
                    course_id=course_id,
                    method="rule_based",
                    features_used=base_features,
                    fallback_used=False,
                    context="post_placement",
                    context_message="Входной тест пройден — вот что изучить дальше",
                    recommendations=post_placement_recs,
                )
            # All mastered
            if all(v >= 0.7 for v in mastery_map.values()):
                return RecommendationsOut(
                    student_id=student_id,
                    course_id=course_id,
                    method="rule_based",
                    features_used=base_features,
                    fallback_used=False,
                    context="completed",
                    context_message="Поздравляем! Все концепты курса освоены.",
                    recommendations=[],
                )
            return RecommendationsOut(
                student_id=student_id,
                course_id=course_id,
                method="rule_based",
                features_used=base_features,
                fallback_used=False,
                recommendations=[],
            )

        if current_item:
            cid = current_item.concept_id
            concept = (
                await db.execute(select(Concept).where(Concept.id == cid))
            ).scalars().first()
            concept_name = concept.name if concept else ""

            current_mastery = mastery_map.get(cid, 0.0)
            current_dkt = dkt_preds.get(cid) if dkt_preds else None
            readiness = current_dkt if current_dkt is not None else current_mastery

            prereq_rows = (
                await db.execute(
                    select(ConceptPrereq).where(ConceptPrereq.concept_id == cid)
                )
            ).scalars().all()
            weak_prereq_ids = [
                pr.prereq_concept_id
                for pr in prereq_rows
                if mastery_map.get(pr.prereq_concept_id, 0.0) < 0.5
            ]
            weak_prereq_names: list[str] = []
            if weak_prereq_ids:
                weak_prereq_names = [
                    c.name for c in (
                        await db.execute(
                            select(Concept).where(Concept.id.in_(weak_prereq_ids))
                        )
                    ).scalars().all()
                ]

            has_attempts = cid in stats_map and stats_map[cid][0] > 0
            is_ungraded_assign = current_item.type == "assign" and not has_attempts

            if is_ungraded_assign:
                context = "pending_grade"
                context_message = "Задание ожидает проверки — пока изучи следующие материалы"
                target_ids = []
            elif weak_prereq_ids:
                context = "fix_prerequisites"
                if has_attempts:
                    context_message = f"Для лучшего освоения повтори: {', '.join(weak_prereq_names)}"
                else:
                    context_message = f"Сначала повтори: {', '.join(weak_prereq_names)}"
                target_ids = weak_prereq_ids
            elif readiness < 0.4:
                context = "review_current"
                context_message = "Рекомендуем дополнительные материалы"
                target_ids = [cid]
            elif readiness >= 0.7:
                context = "ready_to_continue"
                context_message = "Материал освоен — можно идти дальше"
                target_ids = []
            else:
                context = "progressing"
                context_message = "Хороший прогресс, вот дополнительные материалы"
                target_ids = [cid]

            ctx_meta = dict(
                current_cmid=cmid,
                current_concept_id=cid,
                current_concept_name=concept_name,
                current_mastery=current_mastery,
                current_dkt_p_correct=current_dkt,
                context=context,
                context_message=context_message,
                weak_prerequisites=weak_prereq_names,
            )

            if target_ids:
                direct_where = [
                    ContentItem.course_id == course_id,
                    ContentItem.concept_id.in_(target_ids),
                    ContentItem.role != "placement",
                    ContentItem.visible == True,
                ]
                if exclude_cmids:
                    direct_where.append(ContentItem.moodle_cmid.notin_(exclude_cmids))
                ctx_items = (
                    await db.execute(select(ContentItem).where(*direct_where))
                ).scalars().all()

                if not ctx_items:
                    # Fallback: find items via AssessmentMap for concepts without direct ContentItems
                    am_where = [
                        ContentItem.course_id == course_id,
                        AssessmentMap.concept_id.in_(target_ids),
                        ContentItem.role != "placement",
                        ContentItem.visible == True,
                    ]
                    if exclude_cmids:
                        am_where.append(ContentItem.moodle_cmid.notin_(exclude_cmids))
                    ctx_items = (
                        await db.execute(
                            select(ContentItem)
                            .join(AssessmentMap, AssessmentMap.content_item_id == ContentItem.id)
                            .where(*am_where)
                        )
                    ).scalars().all()

                concepts_map = {
                    c.id: c
                    for c in (
                        await db.execute(
                            select(Concept).where(
                                Concept.id.in_({i.concept_id for i in ctx_items})
                            )
                        )
                    ).scalars().all()
                }
                ctx_items_sorted = sorted(
                    _dedupe_by_cmid(ctx_items),
                    key=lambda i: abs(i.difficulty - mastery_map.get(i.concept_id, 0.0)),
                )
                if ctx_items_sorted:
                    return RecommendationsOut(
                        student_id=student_id,
                        course_id=course_id,
                        method="rule_based",
                        features_used=base_features,
                        fallback_used=False,
                        recommendations=[
                            _make_rec_item(i, concepts_map[i.concept_id].name if i.concept_id in concepts_map else "", context_message)
                            for i in ctx_items_sorted[:3]
                        ],
                        **ctx_meta,
                    )
                # ctx_items empty: fall through to LightFM/rule-based below
            # ready_to_continue: fall through to LightFM/rule-based below

    lightfm_cmids = lightfm_recommend(course_id, student_id)
    if lightfm_cmids:
        # Drop already-studied content from LightFM output too
        lightfm_cmids = [c for c in lightfm_cmids if c not in exclude_cmids]
    if lightfm_cmids:
        items_by_cmid = {
            i.moodle_cmid: i
            for i in (
                await db.execute(
                    select(ContentItem).where(
                        ContentItem.course_id == course_id,
                        ContentItem.moodle_cmid.in_(lightfm_cmids),
                    )
                )
            ).scalars().all()
        }
        concepts_by_id = {
            c.id: c
            for c in (
                await db.execute(
                    select(Concept).where(
                        Concept.id.in_({i.concept_id for i in items_by_cmid.values()})
                    )
                )
            ).scalars().all()
        }
        recs = [
            _make_rec_item(
                items_by_cmid[c],
                concepts_by_id[items_by_cmid[c].concept_id].name if items_by_cmid[c].concept_id in concepts_by_id else "",
                "Рекомендовано гибридной моделью (LightFM)",
            )
            for c in lightfm_cmids
            if c in items_by_cmid
        ]
        if recs:
            return RecommendationsOut(
                student_id=student_id,
                course_id=course_id,
                method="lightfm_hybrid",
                features_used=base_features,
                fallback_used=False,
                recommendations=recs,
                **ctx_meta,
            )

    recs = await get_recommendations(db, student_id, course_id, exclude_cmids=exclude_cmids)

    # All concepts mastered — return a friendly completion message instead of empty list
    if not recs and mastery_map and all(v >= 0.7 for v in mastery_map.values()):
        ctx_meta.setdefault(
            "context_message",
            "Поздравляем! Все концепты курса освоены. Продолжайте практиковаться для закрепления.",
        )
        ctx_meta.setdefault("context", "completed")

    return RecommendationsOut(
        student_id=student_id,
        course_id=course_id,
        method="rule_based",
        features_used=base_features,
        fallback_used=model_path(course_id).exists(),
        recommendations=recs,
        **ctx_meta,
    )
