import logging
from typing import List, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiassist_client import fetch_course_context
from app.predictor import select_optimal_difficulty
from app.prompts import (
    BANK_TASK_PROMPT,
    BANK_TASK_PROMPT_NO_CONTEXT,
    CHECK_ANSWER_PROMPT,
    TASK_GENERATION_PROMPT,
)
from app.schemas import TaskSpec
from app.settings import settings

logger = logging.getLogger(__name__)

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url or None,
)

# Task Generation Chain (student-specific, uses BKT difficulty)
task_prompt = ChatPromptTemplate.from_template(TASK_GENERATION_PROMPT)
task_chain = task_prompt | llm | JsonOutputParser()

# Answer Check Chain
check_prompt = ChatPromptTemplate.from_template(CHECK_ANSWER_PROMPT)
check_chain = check_prompt | llm | JsonOutputParser()


def _build_bank_chain(has_context: bool):
    tpl = BANK_TASK_PROMPT if has_context else BANK_TASK_PROMPT_NO_CONTEXT
    return ChatPromptTemplate.from_template(tpl) | llm | JsonOutputParser()


async def generate_tasks(
    concept_name: str,
    mastery: float,
    student_id: int,
    concept_id: int,
    db: AsyncSession,
    variants: int = 2,
) -> List[TaskSpec]:
    """Generate tasks using BKT + recent_avg for adaptive difficulty selection."""
    difficulty, p_success = await select_optimal_difficulty(db, student_id, concept_id, mastery)
    try:
        tasks_json = await task_chain.ainvoke({
            "concept_name": concept_name,
            "mastery": mastery,
            "p_success": p_success,
            "variants": variants,
            "difficulty": difficulty,
        })
        return [TaskSpec.model_validate(t) for t in tasks_json]
    except Exception:
        logger.exception("Failed to generate tasks for concept '%s'", concept_name)
        return []


async def generate_tasks_for_bank(
    concept_name: str,
    difficulty: str,
    variants: int,
    course_id: int,
    teacher_instructions: Optional[str] = None,
    course_context: Optional[str] = None,
) -> List[TaskSpec]:
    """Generate bank tasks grounded in course materials (RAG via AIAssist).
    If `course_context` is provided (e.g. cached by caller), reuse it; otherwise fetch."""
    if course_context is None:
        course_context = await fetch_course_context(course_id, concept_name, top_k=5)

    has_context = bool(course_context)
    if not has_context:
        logger.warning(
            "No RAG context for concept '%s' (course=%d) — generating without course materials",
            concept_name, course_id,
        )

    instructions_block = (
        f"Additional teacher instructions: {teacher_instructions}\n"
        if teacher_instructions else ""
    )

    params = {
        "concept_name": concept_name,
        "difficulty": difficulty,
        "variants": variants,
        "teacher_instructions_block": instructions_block,
    }
    if has_context:
        params["course_context"] = course_context

    try:
        chain = _build_bank_chain(has_context)
        tasks_json = await chain.ainvoke(params)
        return [TaskSpec.model_validate(t) for t in tasks_json]
    except Exception:
        logger.exception(
            "Failed to generate bank tasks for concept '%s' difficulty '%s'",
            concept_name, difficulty,
        )
        return []
