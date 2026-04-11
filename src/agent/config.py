"""Configuration — loads from .env or environment variables."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # LLM provider: "ollama" | "openai" | "anthropic" | "gemini"
    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama")
    )

    # Ollama
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    )

    # API keys (optional — only needed for cloud providers)
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )

    @property
    def litellm_model(self) -> str:
        """Return the model string LiteLLM expects."""
        model_map = {
            "ollama": f"ollama/{self.ollama_model}",
            "openai": "gpt-4o",
            "anthropic": "claude-sonnet-4-20250514",
            "gemini": "gemini/gemini-2.0-flash",
        }
        return model_map.get(self.llm_provider, model_map["ollama"])


settings = Settings()
