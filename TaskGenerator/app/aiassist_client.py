"""HTTP client for fetching course context chunks from AIAssist."""

import logging

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 800
REQUEST_TIMEOUT = 10.0


async def fetch_course_context(
    course_id: int,
    concept_name: str,
    top_k: int = 5,
) -> str:
    """Ask AIAssist for top-K relevant chunks on the given concept.
    Returns a formatted string with chunks separated by '---' or empty string on failure."""
    # Query expansion: improves retrieval for short concept names
    expanded_query = f"{concept_name}. Определение, примеры, применение"

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.aiassist_url}/v1/internal/search",
                json={
                    "course_id": course_id,
                    "query": expanded_query,
                    "top_k": top_k,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning(
            "AIAssist unavailable for concept '%s' (course=%d): %s",
            concept_name, course_id, exc,
        )
        return ""

    chunks = data.get("chunks", [])
    if not chunks:
        return ""

    formatted = []
    for i, ch in enumerate(chunks, 1):
        text = (ch.get("text") or "")[:MAX_CHUNK_CHARS]
        module_name = ch.get("source_module_name", "курса")
        formatted.append(f"[Фрагмент {i} из «{module_name}»]\n{text}")

    return "\n\n---\n\n".join(formatted)
