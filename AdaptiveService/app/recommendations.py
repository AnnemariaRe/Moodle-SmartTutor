from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssessmentMap, Concept, ConceptPrereq, ContentItem, StudentConceptMastery, StudentConceptStats
from app.schemas import RecommendationItem

MASTERY_THRESHOLD = 0.7         # mastery >= this → concept is shown as "mastered" (UI)
PREREQ_UNLOCK_THRESHOLD = 0.5   # mastery >= this → concept is "good enough" to unlock downstream
MAX_RECOMMENDATIONS = 3


async def get_recommendations(
    db: AsyncSession,
    student_id: int,
    course_id: int,
    max_items: int = MAX_RECOMMENDATIONS,
    exclude_cmids: set[int] | None = None,
) -> list[RecommendationItem]:
    exclude_cmids = set(exclude_cmids) if exclude_cmids else set()
    # 1. Load all concepts for this course
    concepts = {
        c.id: c
        for c in (
            await db.execute(select(Concept).where(Concept.course_id == course_id))
        ).scalars().all()
    }
    if not concepts:
        return []

    # 2. Load current mastery for this student (default 0 for unseen concepts)
    masteries: dict[int, float] = {
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

    # 3. Load attempt stats: {concept_id: (num_attempts, num_correct)}
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

    # 4. Load prerequisite edges: {concept_id: [prereq_concept_id, ...]}
    prereqs: dict[int, list[int]] = {}
    for pr in (
        await db.execute(
            select(ConceptPrereq).where(ConceptPrereq.concept_id.in_(concepts.keys()))
        )
    ).scalars().all():
        prereqs.setdefault(pr.concept_id, []).append(pr.prereq_concept_id)

    # 5. Filter: mastery < threshold AND all prerequisites already mastered
    candidates: list[tuple[float, int, Concept]] = []
    for cid, concept in concepts.items():
        current_mastery = masteries.get(cid, 0.0)
        if current_mastery >= MASTERY_THRESHOLD:
            continue
        prereq_ids = prereqs.get(cid, [])
        all_prereqs_met = all(
            masteries.get(pid, 0.0) >= PREREQ_UNLOCK_THRESHOLD for pid in prereq_ids
        )
        if all_prereqs_met:
            candidates.append((current_mastery, cid, concept))

    if not candidates:
        # Relaxed fallback: recommend any unmastered concept ignoring prereq constraints
        for cid, concept in concepts.items():
            current_mastery = masteries.get(cid, 0.0)
            if current_mastery < MASTERY_THRESHOLD:
                candidates.append((current_mastery, cid, concept))
        if not candidates:
            return []

    # 6. Sort by urgency: struggling concepts first
    #    urgency = (1 - mastery) * (1 + fail_rate)
    def _urgency(mastery: float, concept_id: int) -> float:
        attempts, correct = stats_map.get(concept_id, (0, 0))
        fail_rate = 1.0 - (correct / attempts) if attempts > 0 else 0.0
        return (1.0 - mastery) * (1.0 + fail_rate)

    candidates.sort(key=lambda x: -_urgency(x[0], x[1]))

    # 7. Pick content items — difficulty ≈ mastery + 0.15, exclude placement items
    recommendations: list[RecommendationItem] = []
    seen_cmids: set[int] = set(exclude_cmids)

    for current_mastery, concept_id, concept in candidates:
        if len(recommendations) >= max_items:
            break

        target_difficulty = min(1.0, current_mastery + 0.15)

        attempts, correct = stats_map.get(concept_id, (0, 0))

        direct_filter = [
            ContentItem.course_id == course_id,
            ContentItem.concept_id == concept_id,
            ContentItem.role != "placement",
            ContentItem.visible == True,
        ]
        if exclude_cmids:
            direct_filter.append(ContentItem.moodle_cmid.notin_(exclude_cmids))
        items = (
            await db.execute(select(ContentItem).where(*direct_filter))
        ).scalars().all()

        if not items:
            # Fallback: find items that cover this concept via AssessmentMap
            am_filter = [
                ContentItem.course_id == course_id,
                AssessmentMap.concept_id == concept_id,
                ContentItem.role != "placement",
                ContentItem.visible == True,
            ]
            if exclude_cmids:
                am_filter.append(ContentItem.moodle_cmid.notin_(exclude_cmids))
            items = (
                await db.execute(
                    select(ContentItem)
                    .join(AssessmentMap, AssessmentMap.content_item_id == ContentItem.id)
                    .where(*am_filter)
                )
            ).scalars().all()

        if not items:
            continue

        # Sort by proximity to the target difficulty
        items_sorted = sorted(items, key=lambda i: abs(i.difficulty - target_difficulty))

        for item in items_sorted:
            if len(recommendations) >= max_items:
                break
            if item.moodle_cmid in seen_cmids:
                continue
            seen_cmids.add(item.moodle_cmid)

            if attempts > 0:
                reason = (
                    f"Изучите '{concept.name}' "
                    f"(уровень: {current_mastery:.0%}, "
                    f"попыток: {attempts}, успех: {correct/attempts:.0%})"
                )
            else:
                reason = f"Начните изучение '{concept.name}'"

            recommendations.append(
                RecommendationItem(
                    content_item_id=item.id,
                    moodle_cmid=item.moodle_cmid,
                    type=item.type,
                    concept_id=concept_id,
                    concept_name=concept.name,
                    difficulty=item.difficulty,
                    reason=reason,
                )
            )

    return recommendations
