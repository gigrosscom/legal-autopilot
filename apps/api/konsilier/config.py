from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/konsilier.db"
    packs_dir: Path = REPO_ROOT / "packs"

    storage_backend: str = "local"  # local | s3
    storage_local_dir: Path = Path("./data/files")
    s3_endpoint_url: str | None = None
    s3_bucket: str = "konsilier"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    llm_provider: str = "mock"  # anthropic | mock
    llm_model: str = "claude-opus-5"
    anthropic_api_key: str | None = None
    llm_refusal_fallback: str = "default"
    # Images cannot be PII-redacted; send them to the LLM only if explicitly enabled.
    extract_images_with_llm: bool = False

    qualify_min_confidence: float = 0.6
    approval_required_first_n: int = 50

    admin_token: str = "change-me-admin"
    bot_api_secret: str = "change-me-bot"

    soffice_bin: str = "soffice"
    scheduler_interval_seconds: int = 60

    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_from: str = "no-reply@konsilier.com"

    telegram_bot_token: str | None = None
    cors_origins: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        # Hosting providers (Railway, Heroku, ...) hand out postgres:// URLs; we use psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
