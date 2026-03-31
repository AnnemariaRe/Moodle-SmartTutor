import logging
from typing import List, Tuple

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.predictor import select_optimal_difficulty
from app.schemas import TaskSpec
from app.settings import settings

logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=settings.openai_api_key)

# 1. Query Rewrite Chain
rewrite_prompt = ChatPromptTemplate.from_template("""
Переформулируй запрос для поиска слабых концептов курса:
Запрос: {question}

Дай 3 варианта:
1) основной — с ключевыми терминами концепта
2) подтемы — специфические аспекты
3) синонимы — альтернативные формулировки

Формат: нумерованный список.
""")

rewrite_chain = rewrite_prompt | llm | StrOutputParser()

# 2. Task Generation Chain
task_prompt = ChatPromptTemplate.from_template("""
Сгенерируй {variants} уникальных учебных заданий по концепту "{concept_name}".

ВАЖНО: ВСЕ задания должны быть ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ!
Задание, вопрос, варианты ответов, правильный ответ и объяснение — ВСЕ НА РУССКОМ!

Контекст студента:
- Mastery (долгосрочный): {mastery:.2f}
- BKT P(знает концепт): {p_success:.2f}
- Целевая сложность: {difficulty}

Правила:
- Тип: mcq (3–4 варианта ответа) или open (короткий текстовый ответ)
- Анти-списывание: разные числа, контексты, примеры в каждом задании
- Каждое задание должно содержать правильный ответ и объяснение
- При сложности "easy" — проверяй базовые определения
- При "medium" — применение на примерах
- При "hard" — анализ, нестандартные случаи

Верни JSON-массив объектов со строго следующими полями:
- type: "mcq" или "open"
- difficulty: "{difficulty}"
- question: текст вопроса (НА РУССКОМ)
- options: список вариантов (только для mcq, иначе null; ВСЕ НА РУССКОМ)
- correct_index: индекс правильного варианта 0-based (только для mcq, иначе null)
- correct_answer: правильный ответ текстом (только для open, иначе null; НА РУССКОМ)
- explanation: объяснение правильного ответа (НА РУССКОМ)

Только JSON-массив, без markdown, без комментариев.
""")

task_chain = task_prompt | llm | JsonOutputParser()

# 3. Answer Check Chain
check_prompt = ChatPromptTemplate.from_template("""
Проверь ответ студента на учебное задание.

Задание: {task_spec}
Ответ студента: {student_answer}

Верни строго JSON-объект:
{{"score": 0.8, "correct": true, "explanation": "Краткое объяснение оценки НА РУССКОМ"}}

Где score — число от 0 до 1, correct — true если score >= 0.7.
Объяснение должно быть НА РУССКОМ ЯЗЫКЕ!
Только JSON, без markdown.
""")

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
