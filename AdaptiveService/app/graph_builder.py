import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import ConceptSuggestion, extract_concepts_batch
from app.moodle_client import MoodleClient
from app.models import AssessmentMap, Concept, ConceptPrereq, ContentItem, StudentConceptMastery, StudentConceptStats

logger = logging.getLogger(__name__)


async def auto_extract_graph(
    db: AsyncSession,
    course_id: int,
    moodle_url: str,
    moodle_token: str,
    replace_drafts: bool = True,
    course_name: str = "",
) -> dict:
    client = MoodleClient(url=moodle_url, token=moodle_token)

    if not course_name:
        try:
            info = await client.get_course_info(course_id)
            course_name = info.get("fullname", "")
        except Exception:
            pass

    activities = await client.fetch_activities(course_id)
    if not activities:
        return {"activities_processed": 0, "concepts_total": 0, "concepts_new": 0, "content_items_created": 0}

    if replace_drafts:
        await _clear_drafts(db, course_id)
        await db.flush()

    # Batched LLM extraction (sequential, no rate-limit pressure)
    suggestions_by_cmid: dict[int, list[ConceptSuggestion]] = (
        await extract_concepts_batch(activities, course_name)
    )
    suggestions_per_activity: list[list[ConceptSuggestion]] = [
        suggestions_by_cmid.get(a.cmid, []) for a in activities
    ]

    existing_q = await db.execute(
        select(Concept).where(Concept.course_id == course_id)
    )
    concept_map: dict[str, int] = {
        c.name.lower().strip(): c.id for c in existing_q.scalars().all()
    }

    new_concepts: dict[str, Concept] = {}
    for suggestions in suggestions_per_activity:
        for s in suggestions:
            norm = s.name.lower().strip()
            if norm not in concept_map and norm not in new_concepts:
                c = Concept(
                    course_id=course_id,
                    name=s.name,
                    difficulty=0.5,
                    is_approved=False,
                )
                db.add(c)
                new_concepts[norm] = c

    await db.flush()  # populate new concept IDs
    for norm, c in new_concepts.items():
        concept_map[norm] = c.id

    logger.info(
        "Concepts for course %s: %d total (%d new)",
        course_id, len(concept_map), len(new_concepts),
    )

    # concept_id → (section, position) of first appearance — for prereq ordering
    concept_first_pos: dict[int, tuple[int, int]] = {}
    content_items_created = 0

    for activity, suggestions in zip(activities, suggestions_per_activity):
        if not suggestions:
            continue

        # Primary concept = highest weight
        primary = max(suggestions, key=lambda s: s.weight)
        primary_concept_id = concept_map.get(primary.name.lower().strip())
        if not primary_concept_id:
            continue

        # Difficulty ≈ section position (capped at 0.9)
        difficulty = min(0.9, 0.15 + activity.section * 0.12)

        existing_item = (
            await db.execute(
                select(ContentItem).where(
                    ContentItem.course_id == course_id,
                    ContentItem.moodle_cmid == activity.cmid,
                )
            )
        ).scalars().first()

        if existing_item is None:
            item = ContentItem(
                course_id=course_id,
                moodle_cmid=activity.cmid,
                concept_id=primary_concept_id,
                type=activity.type,
                difficulty=difficulty,
            )
            db.add(item)
            await db.flush()
            content_items_created += 1
        else:
            item = existing_item

        # Track first appearance of every mentioned concept
        for s in suggestions:
            cid = concept_map.get(s.name.lower().strip())
            if cid and cid not in concept_first_pos:
                concept_first_pos[cid] = (activity.section, activity.position)

        # AssessmentMap for quiz / assign (multi-concept assessment)
        if activity.type in ("quiz", "assign"):
            for s in suggestions:
                cid = concept_map.get(s.name.lower().strip())
                if not cid:
                    continue
                already = (
                    await db.execute(
                        select(AssessmentMap).where(
                            AssessmentMap.content_item_id == item.id,
                            AssessmentMap.concept_id == cid,
                        )
                    )
                ).scalars().first()
                if already is None:
                    db.add(AssessmentMap(
                        content_item_id=item.id,
                        concept_id=cid,
                        weight=s.weight,
                    ))

    await db.flush()

    # Prerequisite chain by first appearance
    ordered = sorted(concept_first_pos.items(), key=lambda x: x[1])  # (section, pos)
    for i in range(1, len(ordered)):
        later_id = ordered[i][0]
        earlier_id = ordered[i - 1][0]
        already = (
            await db.execute(
                select(ConceptPrereq).where(
                    ConceptPrereq.concept_id == later_id,
                    ConceptPrereq.prereq_concept_id == earlier_id,
                )
            )
        ).scalars().first()
        if already is None:
            db.add(ConceptPrereq(concept_id=later_id, prereq_concept_id=earlier_id))

    await db.commit()

    return {
        "activities_processed": len(activities),
        "concepts_total": len(concept_map),
        "concepts_new": len(new_concepts),
        "content_items_created": content_items_created,
    }


async def _clear_drafts(db: AsyncSession, course_id: int) -> None:
    """Remove all unapproved concepts and their associated rows for this course."""
    draft_ids = (
        await db.execute(
            select(Concept.id).where(
                Concept.course_id == course_id,
                Concept.is_approved == False,  # noqa: E712
            )
        )
    ).scalars().all()

    if not draft_ids:
        return

    # Student mastery/stats for draft concepts (FK may not have DB-level CASCADE)
    await db.execute(
        delete(StudentConceptMastery).where(StudentConceptMastery.concept_id.in_(draft_ids))
    )
    await db.execute(
        delete(StudentConceptStats).where(StudentConceptStats.concept_id.in_(draft_ids))
    )
    # AssessmentMaps referencing draft concepts (even under approved items)
    await db.execute(
        delete(AssessmentMap).where(AssessmentMap.concept_id.in_(draft_ids))
    )
    # ContentItems whose primary concept is a draft
    await db.execute(
        delete(ContentItem).where(
            ContentItem.course_id == course_id,
            ContentItem.concept_id.in_(draft_ids),
        )
    )
    # ConceptPrereq edges
    await db.execute(
        delete(ConceptPrereq).where(
            ConceptPrereq.concept_id.in_(draft_ids)
        )
    )
    await db.execute(
        delete(ConceptPrereq).where(
            ConceptPrereq.prereq_concept_id.in_(draft_ids)
        )
    )
    # Draft concepts themselves
    await db.execute(delete(Concept).where(Concept.id.in_(draft_ids)))
    logger.info("Cleared %d draft concepts for course_id=%s", len(draft_ids), course_id)
