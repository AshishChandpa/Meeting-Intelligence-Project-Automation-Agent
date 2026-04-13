"""LLM service — supports Ollama (local) and cloud providers (Gemini, OpenAI, Anthropic).

- Ollama: uses langchain-ollama with native with_structured_output() (schema-enforced)
- Cloud: uses langchain-google-genai / langchain-openai / langchain-anthropic
         with their own with_structured_output() implementations
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel

from agent.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _get_chat_model():
    """Return the appropriate LangChain chat model based on LLM_PROVIDER."""
    provider = settings.llm_provider

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.2,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,
            temperature=0.2,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=settings.anthropic_api_key,
            temperature=0.2,
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.2,
        )

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Use ollama | openai | anthropic | gemini")


def complete_structured(prompt_messages: list[dict], schema: type[T]) -> T:
    """Call the configured LLM and return a validated Pydantic model instance.

    Uses each provider's native with_structured_output() — no prompt hacks.

    Args:
        prompt_messages: [{"role": "system"|"user"|"assistant", "content": str}]
        schema: Pydantic model class defining the expected output shape.

    Returns:
        A validated instance of `schema`.
    """
    model = _get_chat_model()
    structured = model.with_structured_output(schema)

    lc_messages = [(msg["role"], msg["content"]) for msg in prompt_messages]

    logger.info(
        "Calling %s with structured output → %s",
        settings.llm_provider,
        schema.__name__,
    )
    return structured.invoke(lc_messages)


def complete_text(prompt_messages: list[dict]) -> str:
    """Call the configured LLM and return plain text.

    Used for free-form generation (SoW drafts, follow-up responses, etc.)
    """
    model = _get_chat_model()
    lc_messages = [(msg["role"], msg["content"]) for msg in prompt_messages]

    logger.info("Calling %s for text completion", settings.llm_provider)
    response = model.invoke(lc_messages)
    return response.content
