"""Minimal tests for RAG context integration (AIAssist client + prompt selection)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.aiassist_client import fetch_course_context
from app.chains import _build_bank_chain
from app.prompts import BANK_TASK_PROMPT, BANK_TASK_PROMPT_NO_CONTEXT


@pytest.mark.asyncio
async def test_fetch_context_returns_empty_on_error():
    """When AIAssist is unavailable, client returns empty string (graceful fallback)."""
    with patch("app.aiassist_client.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("connection refused")
        )
        result = await fetch_course_context(course_id=10, concept_name="Atbash")
    assert result == ""


@pytest.mark.asyncio
async def test_fetch_context_formats_chunks():
    """Client joins chunks with '---' separator and includes module names."""
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "chunks": [
            {"text": "Атбаш — древний шифр.", "source_module_name": "Лекция 1", "score": 0.9},
            {"text": "А↔Я, Б↔Ю.", "source_module_name": "Лекция 2", "score": 0.8},
        ]
    }
    with patch("app.aiassist_client.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        result = await fetch_course_context(course_id=10, concept_name="Atbash")
    assert "Атбаш — древний шифр." in result
    assert "А↔Я, Б↔Ю." in result
    assert "Лекция 1" in result
    assert "---" in result


def test_build_bank_chain_selects_context_prompt():
    """_build_bank_chain uses BANK_TASK_PROMPT when context is available."""
    chain = _build_bank_chain(has_context=True)
    # The prompt template is the first element of the chain pipeline
    template_text = chain.first.messages[0].prompt.template
    assert "COURSE MATERIALS" in template_text
    assert template_text == BANK_TASK_PROMPT


def test_build_bank_chain_selects_fallback_prompt():
    """_build_bank_chain uses BANK_TASK_PROMPT_NO_CONTEXT when context is missing."""
    chain = _build_bank_chain(has_context=False)
    template_text = chain.first.messages[0].prompt.template
    assert "CONTEXT UNAVAILABLE" in template_text
    assert template_text == BANK_TASK_PROMPT_NO_CONTEXT
