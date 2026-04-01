"""
LLM-based concept extraction with batching.
"""
import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from openai import AsyncOpenAI, RateLimitError, APIError

if TYPE_CHECKING:
    from app.moodle_client import ActivityData

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "gpt-4o-mini"
BATCH_SIZE = 6          # activities per LLM call
TEXT_PER_ACTIVITY = 1500  # chars per activity inside a batch prompt
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 15  # wait = RETRY_BASE_SECONDS * 2^attempt on 429

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


@dataclass
class ConceptSuggestion:
    name: str
    weight: float


# Public API
async def extract_concepts_batch(
    activities: "list[ActivityData]",
    course_name: str = "",
) -> dict[int, list[ConceptSuggestion]]:
    """Process all activities in sequential batches.

    Returns {cmid: [ConceptSuggestion]}.
    Sequential (not parallel) to stay within rate limits.
    """
    if not activities:
        return {}

    batches = [
        activities[i : i + BATCH_SIZE]
        for i in range(0, len(activities), BATCH_SIZE)
    ]
    logger.info(
        "LLM extraction: %d activities → %d batches of ≤%d",
        len(activities), len(batches), BATCH_SIZE,
    )

    results: dict[int, list[ConceptSuggestion]] = {}
    for idx, batch in enumerate(batches, start=1):
        logger.info("Batch %d/%d (%d activities)…", idx, len(batches), len(batch))
        batch_result = await _extract_one_batch(batch, course_name)
        results.update(batch_result)

    found = sum(1 for v in results.values() if v)
    logger.info("Extraction done: %d/%d activities got concepts", found, len(activities))
    return results


# Internals
_TYPE_LABELS = {
    "page": "страница",
    "quiz": "квиз/тест",
    "assign": "задание",
    "book": "книга",
    "lesson": "интерактивный урок",
}


async def _extract_one_batch(
    activities: "list[ActivityData]",
    course_name: str,
) -> dict[int, list[ConceptSuggestion]]:
    course_hint = f' курса «{course_name}»' if course_name else ""
    cmid_list = ", ".join(str(a.cmid) for a in activities)

    items_text = "\n\n".join(
        f"=== Активность {i + 1} "
        f"(cmid={a.cmid}, тип: {_TYPE_LABELS.get(a.type, a.type)}, "
        f"название: «{a.name}») ===\n{a.text[:TEXT_PER_ACTIVITY]}"
        for i, a in enumerate(activities)
    )

    prompt = f"""Ты — ассистент по анализу учебного контента{course_hint}.

Ниже {len(activities)} учебных активностей. Для каждой выдели 3–7 ключевых учебных концептов (тем), которые в ней объясняются или проверяются.

Требования к концептам:
- Краткие (2–5 слов), как в учебном плане: «циклы for», «условия if/else», «списки Python».
- Упорядочены от наиболее важного к наименее важному для данной активности.
- Первый концепт — главная тема, остальные — вспомогательные.

{items_text}

Ответ строго JSON без пояснений и markdown-блоков. Верни результаты ровно для cmid: {cmid_list}.
{{"results": [{{"cmid": <число>, "concepts": ["главная тема", "вторая тема", "третья тема"]}}]}}"""

    raw = await _call_with_retry(prompt)
    if not raw:
        return {}
    return _parse_batch(raw, activities)


async def _call_with_retry(prompt: str) -> str:
    for attempt in range(MAX_RETRIES):
        try:
            response = await _get_client().chat.completions.create(
                model=EXTRACTION_MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
        except RateLimitError:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "Rate limit hit (attempt %d/%d) — waiting %ds",
                    attempt + 1, MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Rate limit exceeded after %d attempts", MAX_RETRIES)
                return ""
        except APIError as exc:
            logger.error("LLM API error: %s", exc)
            return ""
    return ""


def _parse_batch(
    raw: str,
    activities: "list[ActivityData]",
) -> dict[int, list[ConceptSuggestion]]:
    valid_cmids = {a.cmid for a in activities}
    results: dict[int, list[ConceptSuggestion]] = {}

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        logger.warning("No JSON in batch response: %.150s", raw)
        return results

    try:
        data = json.loads(match.group())
        for item in data.get("results", []):
            cmid = int(item.get("cmid", 0))
            if cmid not in valid_cmids:
                continue
            concepts = []
            for rank, c in enumerate(item.get("concepts", [])):
                # LLM returns ordered list of strings; weight = rank-based decay
                # rank 0 → 1.0, rank 1 → 0.7, rank 2 → 0.5, rank 3 → 0.4, ...
                name = str(c).strip() if isinstance(c, str) else str(c.get("name", "")).strip()
                weight = round(1.0 / (1.0 + rank * 0.5), 2)
                if name:
                    concepts.append(ConceptSuggestion(name=name, weight=weight))
            if concepts:
                results[cmid] = concepts
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Batch parse error: %s — raw: %.300s", exc, raw)

    return results
