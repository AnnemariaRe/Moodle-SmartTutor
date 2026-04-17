import logging
from typing import List, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.predictor import select_optimal_difficulty
from app.prompts import BANK_TASK_PROMPT, CHECK_ANSWER_PROMPT, TASK_GENERATION_PROMPT
from app.schemas import TaskSpec
from app.settings import settings

logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=settings.openai_api_key)

# Task Generation Chain (student-specific, uses BKT difficulty)
task_prompt = ChatPromptTemplate.from_template(TASK_GENERATION_PROMPT)
task_chain = task_prompt | llm | JsonOutputParser()

# Bank Task Generation Chain (explicit difficulty, optional teacher instructions)
bank_task_prompt = ChatPromptTemplate.from_template(BANK_TASK_PROMPT)
bank_task_chain = bank_task_prompt | llm | JsonOutputParser()

# Answer Check Chain
check_prompt = ChatPromptTemplate.from_template(CHECK_ANSWER_PROMPT)
check_chain = check_prompt | llm | JsonOutputParser()


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
    teacher_instructions: Optional[str] = None,
) -> List[TaskSpec]:
    """Generate tasks for the bank with explicit difficulty and optional teacher instructions."""
    if teacher_instructions:
        instructions_block = f"Additional teacher instructions: {teacher_instructions}\n"
    else:
        instructions_block = ""
    try:
        tasks_json = await bank_task_chain.ainvoke({
            "concept_name": concept_name,
            "difficulty": difficulty,
            "variants": variants,
            "teacher_instructions_block": instructions_block,
        })
        return [TaskSpec.model_validate(t) for t in tasks_json]
    except Exception:
        logger.exception(
            "Failed to generate bank tasks for concept '%s' difficulty '%s'",
            concept_name, difficulty,
        )
        return []
