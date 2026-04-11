"""LLM service — uses langchain-ollama with native structured output.

langchain-ollama's with_structured_output() uses Ollama's format enforcement
(grammar-constrained decoding) which is far more reliable than prompt-based
JSON extraction for smaller models like Mistral.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from langchain_ollama import ChatOllama
from pydantic import BaseModel

from agent.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Module-level client — reused across calls
_client: ChatOllama | None = None


def _get_client() -> ChatOllama:
    """Return (or create) the shared Ollama client."""
    global _client
    if _client is None:
        _client = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.2,
        )
    return _client


def complete_structured(prompt_messages: list[dict], schema: type[T]) -> T:
    """Call Ollama and return a validated Pydantic model instance.

    Uses langchain-ollama's with_structured_output() which leverages Ollama's
    native JSON schema enforcement — no prompt hacks needed.

    Args:
        prompt_messages: List of {"role": "system"|"user"|"assistant", "content": str}
        schema: Pydantic model class defining the expected output shape.

    Returns:
        A validated instance of `schema`.
    """
    client = _get_client()
    structured_client = client.with_structured_output(schema)

    # Convert plain dicts to LangChain message tuples
    lc_messages = [
        (msg["role"], msg["content"]) for msg in prompt_messages
    ]

    logger.info("Calling Ollama (%s) with structured output...", settings.ollama_model)
    result = structured_client.invoke(lc_messages)
    return result


def complete_text(prompt_messages: list[dict]) -> str:
    """Call Ollama and return plain text (no schema enforcement).

    Used for free-form generation (e.g. SoW drafts, clarification questions).
    """
    client = _get_client()
    lc_messages = [
        (msg["role"], msg["content"]) for msg in prompt_messages
    ]
    response = client.invoke(lc_messages)
    return response.content
