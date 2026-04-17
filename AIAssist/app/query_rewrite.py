import logging
from typing import List

from pydantic import BaseModel, Field

from app.llm import get_llm
from app.prompts import QUERY_REWRITE_PROMPT

logger = logging.getLogger(__name__)


class QueryExpansion(BaseModel):
    queries: List[str] = Field(
        description="3 альтернативных поисковых запроса: явные, насыщенные ключевыми словами перефразировки исходного вопроса"
    )
    hyde_document: str = Field(
        description="Гипотетический фрагмент учебного материала (~100 слов), который отвечал бы на вопрос студента"
    )


async def expand_query(question: str) -> QueryExpansion:
    try:
        result: QueryExpansion = await get_llm().with_structured_output(QueryExpansion).ainvoke([
            {"role": "system", "content": QUERY_REWRITE_PROMPT},
            {"role": "user",   "content": question},
        ])
        return result
    except Exception as exc:
        logger.warning("Query expansion failed, using original question: %s", exc)
        return QueryExpansion(queries=[], hyde_document=question)
