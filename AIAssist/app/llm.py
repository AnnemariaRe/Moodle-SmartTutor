import os
from functools import lru_cache

from langchain_openai import ChatOpenAI


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
