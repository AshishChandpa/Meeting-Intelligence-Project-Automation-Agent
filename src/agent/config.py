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

    # Jira (optional — can also be set via state at runtime)
    jira_domain: str = field(
        default_factory=lambda: os.getenv("JIRA_DOMAIN", "")
    )
    jira_email: str = field(
        default_factory=lambda: os.getenv("JIRA_EMAIL", "")
    )
    jira_api_token: str = field(
        default_factory=lambda: os.getenv("JIRA_API_TOKEN", "")
    )
    jira_project_key: str = field(
        default_factory=lambda: os.getenv("JIRA_PROJECT_KEY", "")
    )

    @property
    def jira_config_from_env(self) -> dict:
        """Return Jira config dict if all env vars are set, else empty dict."""
        if all([self.jira_domain, self.jira_email, self.jira_api_token, self.jira_project_key]):
            return {
                "domain": self.jira_domain,
                "email": self.jira_email,
                "api_token": self.jira_api_token,
                "project_key": self.jira_project_key,
            }
        return {}

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
