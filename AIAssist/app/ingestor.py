import asyncio
import html
import logging
import re
from typing import Dict, List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import embedder, moodle_client
from app.llm import get_llm
from app.models import CourseChunk, CourseOverview

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64
SUPPORTED_TYPES = {"page", "book", "lesson", "assign", "quiz", "url"}

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],
)

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NL    = re.compile(r"\n{3,}")

_OVERVIEW_PROMPT = """\
Ты ассистент преподавателя. Ниже — полная структура учебного курса (разделы и модули).
Напиши краткую аннотацию курса (150–200 слов) на русском языке:
- Тематика и название курса
- Основные разделы и ключевые темы
- Что студент узнает / научится делать

Структура курса:
{structure}

Аннотация:\
"""


def _clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


async def _fetch_rich_content(
    course_id: int,
    sections: list,
) -> tuple[Dict[int, str], Dict[int, str], Dict[int, str]]:
    # --- lessons ---
    lesson_texts: Dict[int, str] = {}
    for section in sections:
        for mod in section.get("modules", []):
            if mod.get("modname") != "lesson":
                continue
            cmid        = mod["id"]
            instance_id = mod.get("instance", 0)
            if not instance_id:
                continue
            try:
                pages = await moodle_client.get_lesson_pages(instance_id)
                parts: List[str] = []
                for page in pages:
                    if title := page.get("title", ""):
                        parts.append(f"### {title}")
                    if content := _clean_html(page.get("contents", "")):
                        parts.append(content)
                if parts:
                    lesson_texts[cmid] = "\n\n".join(parts)
            except Exception as exc:
                logger.warning("Failed to fetch lesson pages (cmid=%d): %s", cmid, exc)

    # --- pages ---
    page_texts: Dict[int, str] = {}
    try:
        raw = await moodle_client.get_page_contents_by_course(course_id)
        page_texts = {cmid: _clean_html(html_) for cmid, html_ in raw.items() if html_}
    except Exception as exc:
        logger.warning("Failed to fetch page contents: %s", exc)

    # --- quizzes ---
    quiz_texts: Dict[int, str] = {}
    try:
        raw = await moodle_client.get_quiz_intros_by_course(course_id)
        quiz_texts = {cmid: _clean_html(html_) for cmid, html_ in raw.items() if html_}
    except Exception as exc:
        logger.warning("Failed to fetch quiz intros: %s", exc)

    return lesson_texts, page_texts, quiz_texts


def _extract_base_text(module: dict) -> str:
    parts: List[str] = []
    if desc := _clean_html(module.get("description") or ""):
        parts.append(desc)
    for item in module.get("contents", []):
        if item.get("type") == "content":
            if cleaned := _clean_html(item.get("content") or ""):
                parts.append(cleaned)
    return "\n\n".join(parts)


def _parse_modules(
    sections: list,
    lesson_texts: Dict[int, str],
    page_texts: Dict[int, str],
    quiz_texts: Dict[int, str],
) -> List[Document]:
    docs: List[Document] = []
    for section in sections:
        section_num = section.get("section", 0)
        for mod in section.get("modules", []):
            mod_type = mod.get("modname", "")
            if mod_type not in SUPPORTED_TYPES:
                continue
            cmid  = mod["id"]
            title = mod.get("name", "")

            rich = (
                lesson_texts.get(cmid)
                or page_texts.get(cmid)
                or quiz_texts.get(cmid)
            )
            text = rich or _extract_base_text(mod) or title

            docs.append(Document(
                page_content=text,
                metadata={"cmid": cmid, "type": mod_type, "section": section_num, "title": title},
            ))
    return docs


def _split_modules(module_docs: List[Document]) -> List[Document]:
    chunks: List[Document] = []
    for doc in module_docs:
        splits = _splitter.split_documents([doc])
        if not splits:
            splits = [Document(page_content=doc.metadata["title"], metadata=doc.metadata)]
        for position, chunk in enumerate(splits):
            chunk.metadata["position_in_module"] = position
        chunks.extend(splits)
    return chunks


def _build_course_structure(sections: list) -> str:
    lines: List[str] = []
    for section in sections:
        section_name = (section.get("name") or f"Раздел {section.get('section', 0)}").strip()
        modules = [m for m in section.get("modules", []) if m.get("modname", "") in SUPPORTED_TYPES]
        if not modules:
            continue
        lines.append(f"\n{section_name}:")
        for mod in modules:
            lines.append(f"  [{mod.get('modname', '?')}] {mod.get('name', '').strip()}")
    return "\n".join(lines)


async def _generate_course_overview(course_id: int, sections: list, db: AsyncSession) -> None:
    structure = _build_course_structure(sections)
    if not structure.strip():
        return
    try:
        response = await get_llm().ainvoke(_OVERVIEW_PROMPT.format(structure=structure))
        overview_text: str = response.content.strip()
    except Exception as exc:
        logger.warning("Course overview generation failed (course_id=%d): %s", course_id, exc)
        return

    stmt = (
        pg_insert(CourseOverview)
        .values(course_id=course_id, overview=overview_text)
        .on_conflict_do_update(index_elements=["course_id"], set_={"overview": overview_text})
    )
    await db.execute(stmt)
    logger.info("Course overview stored (course_id=%d, %d chars)", course_id, len(overview_text))


async def reindex_course(course_id: int, db: AsyncSession) -> int:
    logger.info("Reindex started: course_id=%d", course_id)

    sections = await moodle_client.get_course_contents(course_id)
    lesson_texts, page_texts, quiz_texts = await _fetch_rich_content(course_id, sections)
    logger.info(
        "Rich content fetched: lessons=%d pages=%d quizzes=%d",
        len(lesson_texts), len(page_texts), len(quiz_texts),
    )

    module_docs = _parse_modules(sections, lesson_texts, page_texts, quiz_texts)
    chunk_docs  = _split_modules(module_docs)

    logger.info("Modules: %d → Chunks: %d", len(module_docs), len(chunk_docs))
    if not chunk_docs:
        return 0

    new_chunks = [
        CourseChunk(
            course_id=course_id,
            cmid=doc.metadata["cmid"],
            type=doc.metadata["type"],
            section=doc.metadata["section"],
            title=doc.metadata["title"],
            text=doc.page_content,
            position_in_module=doc.metadata["position_in_module"],
        )
        for doc in chunk_docs
    ]

    loop = asyncio.get_running_loop()
    texts = [c.text for c in new_chunks]
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch_embs = await loop.run_in_executor(None, embedder.embed_batch, texts[i : i + EMBED_BATCH_SIZE])
        for chunk, emb in zip(new_chunks[i:], batch_embs):
            chunk.embedding = emb.tolist()

    await db.execute(delete(CourseChunk).where(CourseChunk.course_id == course_id))
    db.add_all(new_chunks)
    await db.commit()

    logger.info("Reindex complete: %d chunks stored (course_id=%d)", len(new_chunks), course_id)

    await _generate_course_overview(course_id, sections, db)
    await db.commit()

    return len(new_chunks)
