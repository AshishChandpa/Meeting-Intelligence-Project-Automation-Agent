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
from agent.streaming import emit_stream_event

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _get_chat_model(temperature: float | None = None):
    """Return the appropriate LangChain chat model based on LLM_PROVIDER.

    Args:
        temperature: Optional temperature override. If None, uses default 0.2.
    """
    provider = settings.llm_provider
    temp = temperature if temperature is not None else 0.2

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temp,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,
            temperature=temp,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=settings.anthropic_api_key,
            temperature=temp,
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.gemini_api_key,
            temperature=temp,
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
    emit_stream_event(
        "llm_start",
        {
            "provider": settings.llm_provider,
            "mode": "structured",
            "schema": schema.__name__,
            "message": f"Running structured extraction for {schema.__name__}...",
        },
    )
    response = structured.invoke(lc_messages)
    emit_stream_event(
        "llm_complete",
        {
            "provider": settings.llm_provider,
            "mode": "structured",
            "schema": schema.__name__,
            "message": f"Structured extraction complete for {schema.__name__}.",
        },
    )
    return response


def complete_text(prompt_messages: list[dict], temperature: float | None = None) -> str:
    """Call the configured LLM and return plain text.

    Used for free-form generation (SoW drafts, follow-up responses, etc.)

    Args:
        prompt_messages: [{"role": "system"|"user"|"assistant", "content": str}]
        temperature: Optional temperature override. Lower = more deterministic.

    Returns:
        Plain text response from the LLM.
    """
    model = _get_chat_model(temperature=temperature)
    lc_messages = [(msg["role"], msg["content"]) for msg in prompt_messages]

    temp_str = f" (temp={temperature})" if temperature is not None else ""
    logger.info("Calling %s for text completion%s", settings.llm_provider, temp_str)
    emit_stream_event(
        "llm_start",
        {
            "provider": settings.llm_provider,
            "mode": "text",
            "message": "Generating text output...",
            "temperature": temperature,
        },
    )
    response = model.invoke(lc_messages)
    content = response.content
    emit_stream_event(
        "llm_complete",
        {
            "provider": settings.llm_provider,
            "mode": "text",
            "message": "Text generation complete.",
            "preview": str(content)[:180],
            "temperature": temperature,
        },
    )
    return content
