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
    s3_region: str | None = None  # provider region name, if the S3 endpoint requires one

    llm_provider: str = "mock"  # anthropic | mock
    # Main model writes the document text; the fast model does classification and extraction.
    llm_model: str = "claude-sonnet-5"
    llm_fast_model: str = "claude-haiku-4-5"
    anthropic_api_key: str | None = None
    llm_refusal_fallback: str = "default"
    # Images cannot be PII-redacted; send them to the LLM only if explicitly enabled.
    extract_images_with_llm: bool = False

    qualify_min_confidence: float = 0.6
    approval_required_first_n: int = 50
    # Self-service: documents a person can file without a lawyer (pre-trial claim, complaint, statement, motion outside court) are
    # released at once; court documents and flagged cases still wait for a lawyer. False → the old rule
    # (every universal document and the first N cases of each scenario are approved by a lawyer).
    self_service: bool = True
    self_service_documents: str = "claim_letter,complaint,statement,motion"

    admin_token: str = "change-me-admin"
    bot_api_secret: str = "change-me-bot"

    soffice_bin: str = "soffice"
    scheduler_interval_seconds: int = 60

    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_from: str = "no-reply@konsilier.com"

    # Sign-in and identity (see konsilier/core/identity). Keep IDENTITY_SECRET stable: it keys the hashes.
    identity_secret: str = "change-me-identity"
    public_api_url: str = "http://localhost:8000"
    public_site_url: str = "http://localhost:3000"  # links in e-mails
    report_every_days: int = 3  # next-step reminder when a case has not moved
    report_max_nudges: int = 5  # then stop reminding until something changes  # eGov Mobile fetches the document to sign from here
    resend_api_key: str | None = None  # e-mail codes via Resend; otherwise SMTP_HOST; otherwise disabled
    email_from: str = "Konsilier.AI <no-reply@konsilier.com>"
    sms_provider: str = ""  # mobizon | smsc | log ("log" only for development)
    sms_api_key: str | None = None  # Mobizon API key
    smsc_login: str | None = None
    smsc_password: str | None = None
    sms_sender: str | None = None  # registered alpha name, if any
    ncanode_url: str | None = None  # e.g. http://ncanode:14579 — enables ЭЦП and eGov Mobile checks
    egov_org_bin: str | None = None  # BIN shown in eGov Mobile; eGov Mobile sign-in is off without it
    egov_org_name: str = "Konsilier.AI"
    phone_default_country_code: str = "7"  # for numbers typed without "+"
    dev_show_codes: bool = False  # tests/dev only: return the one-time code in the API response

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
