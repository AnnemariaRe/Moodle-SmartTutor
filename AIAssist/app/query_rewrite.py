import logging
from typing import List

from pydantic import BaseModel, Field

from app.llm import get_llm

logger = logging.getLogger(__name__)


class QueryExpansion(BaseModel):
    queries: List[str] = Field(
        description="3 альтернативных поисковых запроса: явные, насыщенные ключевыми словами перефразировки исходного вопроса"
    )
    hyde_document: str = Field(
        description="Гипотетический фрагмент учебного материала (~100 слов), который отвечал бы на вопрос студента"
    )


_SYSTEM_PROMPT = """\
Ты оптимизатор поисковых запросов для учебного ассистента курса.

По вопросу студента сформируй:
1. Три альтернативных запроса для векторного поиска — насыщенных ключевыми словами, конкретных, ориентированных на понятия курса.
   Каждый запрос должен точно отражать тему без местоимений и размытых формулировок.
2. Гипотетический документ-ответ (~100 слов), написанный как реальный фрагмент лекции,
   который идеально отвечает на вопрос студента (техника Hypothetical Document Embedding / HyDE).

Отвечай на том же языке, на котором задан вопрос студента.\
"""


async def expand_query(question: str) -> QueryExpansion:
    try:
        result: QueryExpansion = await get_llm().with_structured_output(QueryExpansion).ainvoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": question},
        ])
        return result
    except Exception as exc:
        logger.warning("Query expansion failed, using original question: %s", exc)
        return QueryExpansion(queries=[], hyde_document=question)
