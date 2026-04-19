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

    # Project persistence backend: "memory" | "mongo"
    project_storage_backend: str = field(
        default_factory=lambda: os.getenv("PROJECT_STORAGE_BACKEND", "memory")
    )
    mongodb_uri: str = field(
        default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    )
    mongodb_database: str = field(
        default_factory=lambda: os.getenv("MONGODB_DATABASE", "meeting_intelligence")
    )
    mongodb_collection: str = field(
        default_factory=lambda: os.getenv("MONGODB_COLLECTION", "projects")
    )

    # Local app networking
    api_host: str = field(
        default_factory=lambda: os.getenv("API_HOST", "127.0.0.1")
    )
    api_port: int = field(
        default_factory=lambda: int(os.getenv("API_PORT", "8000"))
    )
    frontend_port: int = field(
        default_factory=lambda: int(os.getenv("VITE_PORT", "5173"))
    )
    cors_allowed_origins_raw: str = field(
        default_factory=lambda: os.getenv("CORS_ALLOWED_ORIGINS", "")
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

    @property
    def cors_allowed_origins(self) -> list[str]:
        if self.cors_allowed_origins_raw.strip():
            return [origin.strip() for origin in self.cors_allowed_origins_raw.split(",") if origin.strip()]
        return [
            f"http://localhost:{self.frontend_port}",
            f"http://127.0.0.1:{self.frontend_port}",
            "http://localhost:3000",
        ]


settings = Settings()
