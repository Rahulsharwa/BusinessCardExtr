"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment / .env file."""

    # ── Server ──────────────────────────────────────
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ── OpenRouter ──────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL_DEFAULT: str = "anthropic/claude-3.5-sonnet"
    OPENROUTER_MODEL_ALLOWLIST: str = (
        "anthropic/claude-3.5-sonnet,openai/gpt-4o,google/gemini-2.0-flash-001"
    )

    # ── Google Cloud ────────────────────────────────
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""

    # ── Google Sheets Defaults ──────────────────────
    DEFAULT_SHEET_ID: str | None = None
    DEFAULT_SHEET_NAME: str | None = None

    # ── Processing Defaults ─────────────────────────
    MAX_FILES_DEFAULT: int = 200
    CONCURRENCY_DEFAULT: int = 3

    # ── Derived helpers ─────────────────────────────
    @property
    def allowed_models(self) -> List[str]:
        """Parse the comma-separated model allowlist."""
        return [m.strip() for m in self.OPENROUTER_MODEL_ALLOWLIST.split(",") if m.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
