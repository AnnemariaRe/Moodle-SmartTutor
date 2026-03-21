import asyncio
import json
import logging
from collections import Counter
from typing import List

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import embedder
from app.database import get_db
from app.llm import get_llm
from app.models import AssistantLog, CourseChunk, CourseOverview
from app.query_rewrite import expand_query
from app.schemas import AskRequest, AskResponse, SourceItem

logger = logging.getLogger(__name__)
router = APIRouter()

TOP_K = 5
RETRIEVE_K = 3
MAX_CONTEXT_CHARS = 6000

SYSTEM_PROMPT = """\
Ты учебный AI-ассистент курса. Ниже тебе будут предоставлены фрагменты учебных материалов курса.

Твои задачи:
- Отвечать на вопросы студентов по содержанию курса, опираясь на предоставленные материалы.
- Разъяснять условия заданий, если студент не понимает, что от него требуется.
- Придумывать и показывать примеры, иллюстрации, аналогии — если это помогает понять тему.
- Помогать разобраться в теме шаг за шагом, если студент просит.

Правила:
- Используй предоставленные фрагменты как основной источник знаний о курсе.
- Если в материалах недостаточно информации — скажи об этом и помоги, насколько можешь.
- Никогда не решай задание за студента напрямую — направляй, объясняй, показывай похожий пример.
- Отвечай на русском языке, понятно и по существу.\
"""


async def _multi_query_retrieve(query_texts: List[str], course_id: int, db: AsyncSession) -> List[CourseChunk]:
    loop = asyncio.get_running_loop()
    embeddings: np.ndarray = await loop.run_in_executor(None, embedder.embed_batch, query_texts)

    all_chunks: dict[int, CourseChunk] = {}
    hit_counts: Counter[int] = Counter()

    for q_vec in embeddings:
        stmt = (
            select(CourseChunk)
            .where(CourseChunk.course_id == course_id)
            .order_by(CourseChunk.embedding.cosine_distance(q_vec.tolist()))
            .limit(RETRIEVE_K)
        )
        for chunk in (await db.execute(stmt)).scalars().all():
            all_chunks[chunk.id] = chunk
            hit_counts[chunk.id] += 1

    sorted_ids = sorted(all_chunks, key=lambda cid: hit_counts[cid], reverse=True)
    return [all_chunks[cid] for cid in sorted_ids[:TOP_K]]


async def _get_course_overview(course_id: int, db: AsyncSession) -> str:
    row = await db.get(CourseOverview, course_id)
    return row.overview if row else ""


def _build_user_message(question: str, chunks: List[CourseChunk], overview: str) -> str:
    context_parts = [
        f"[{i}] {chunk.title} (тип: {chunk.type}, раздел {chunk.section})\n{chunk.text}"
        for i, chunk in enumerate(chunks, 1)
    ]
    context = "\n\n---\n\n".join(context_parts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n...(обрезано)"

    overview_block = f"=== О курсе ===\n{overview}\n\n" if overview else ""
    return (
        f"{overview_block}"
        f"=== Материалы курса ===\n{context}\n\n"
        f"=== Вопрос студента ===\n{question}"
    )


@router.post("/v1/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: AsyncSession = Depends(get_db)):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым")

    expansion = await expand_query(question)
    query_texts = [question] + expansion.queries + [expansion.hyde_document]

    seen: set[str] = set()
    unique_queries: List[str] = []
    for q in query_texts:
        if q and q not in seen:
            seen.add(q)
            unique_queries.append(q)

    logger.info("Retrieval with %d query variants (course_id=%d)", len(unique_queries), request.course_id)

    chunks = await _multi_query_retrieve(unique_queries, request.course_id, db)
    if not chunks:
        return AskResponse(
            answer="По данному курсу пока нет проиндексированных материалов. Обратитесь к преподавателю.",
            sources=[],
            course_id=request.course_id,
        )

    overview = await _get_course_overview(request.course_id, db)

    history_messages = []
    for msg in request.history[-10:]:  # последние 5 обменов (10 сообщений)
        if msg.role == "user":
            history_messages.append(HumanMessage(content=msg.content))
        else:
            history_messages.append(AIMessage(content=msg.content))

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *history_messages,
        HumanMessage(content=_build_user_message(question, chunks, overview)),
    ]
    try:
        response = await get_llm(temperature=0.2).ainvoke(messages)
        answer: str = response.content
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="Ошибка обращения к AI-модели")

    seen_cmids: set[int] = set()
    sources: List[SourceItem] = []
    for chunk in chunks:
        if chunk.cmid not in seen_cmids and chunk.type not in ("assign", "quiz"):
            seen_cmids.add(chunk.cmid)
            sources.append(SourceItem(cmid=chunk.cmid, title=chunk.title, type=chunk.type))

    db.add(AssistantLog(
        student_id=request.student_id,
        course_id=request.course_id,
        question=question,
        answer=answer,
        used_chunk_ids=json.dumps([c.id for c in chunks]),
    ))
    await db.commit()

    return AskResponse(answer=answer, sources=sources, course_id=request.course_id)
