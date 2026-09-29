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

    llm_provider: str = "mock"  # anthropic | bedrock | gemini | mock
    # Claude on Amazon Bedrock (LLM_PROVIDER=bedrock), e.g. paid from AWS Activate credits.
    # Keys may be left empty to use the standard AWS credential chain.
    bedrock_region: str = "eu-central-1"
    bedrock_access_key: str | None = None
    bedrock_secret_key: str | None = None
    # Main model writes the document text; the fast model does classification and extraction.
    llm_model: str = "claude-sonnet-5"
    llm_fast_model: str = "claude-haiku-4-5"
    # The model behind the consultation chat: gemini (free tier) | anthropic (paid) | free (CHAT_FREE_PROVIDERS in turn)
    chat_provider: str = "gemini"
    # Free providers tried in turn when CHAT_PROVIDER=free; those without a key are skipped.
    chat_free_providers: str = "cerebras,gemini,groq"
    cerebras_api_key: str = ""
    cerebras_model: str = ""  # empty: the default in konsilier/openai_compat.py
    groq_api_key: str = ""
    groq_model: str = ""
    nvidia_api_key: str = ""
    nvidia_model: str = ""
    mistral_api_key: str = ""
    mistral_model: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    # Tried in turn when the model above is overloaded (503/429): free-tier quotas are counted per model.
    gemini_fallback_models: str = "gemini-3.5-flash-lite,gemini-flash-lite-latest,gemini-3-flash-preview"
    # When every Gemini model fails before the reply starts, answer with Claude (fast model) if it is configured.
    # Off by default: the free chat does not fall back to a paid model unless this is switched on explicitly.
    chat_fallback_to_anthropic: bool = False
    # Daily cap (UTC day) on the estimated cost of chat replies written by Claude. Once reached, the fallback is
    # off until the next day and the person is asked to retry in a minute. 0 → the fallback is never used.
    chat_fallback_daily_budget_usd: float = 10.0
    # Prices of the fast model (LLM_FAST_MODEL, claude-haiku-4-5) used for the estimate, USD.
    anthropic_price_input_per_mtok: float = 1.0
    anthropic_price_output_per_mtok: float = 5.0
    anthropic_price_web_search: float = 0.01  # per search ($10 per 1000)
    team_email: str = "info@konsilier.com"  # fallback address for desk notifications
    # Operations centre: e-mails (comma-separated) of the operators of each desk. They sign in with an e-mail code;
    # new items of the desk are also e-mailed to these addresses.
    ops_lawyers_emails: str = "info@konsilier.com"  # lawyers desk: applications of advocates and lawyers
    ops_clients_emails: str = "info@konsilier.com"  # clients desk: questions, complaints, suggestions, lawyer requests
    terms_version: str = "2026-09-29"  # current wording of the Terms of Use (apps/web/lib/legal/terms.ts)
    # Document payment (konsilier/core/adapters/payment.py): manual_transfer — a transfer to the Kaspi number below,
    # confirmed by the clients desk in /ops; stub — every invoice is paid at once (tests, development only).
    # Recipient and number live only in the server's .env; while either is empty, documents are not issued.
    payment_mode: str = "manual_transfer"
    payment_recipient_name: str = ""  # recipient's name as the payer's banking app shows it
    payment_kaspi_phone: str = ""  # Kaspi number to transfer to
    payment_comment_prefix: str = ""  # optional prefix of the payment code in the transfer comment
    payment_notify_emails: str = ""  # also get «клиент оплатил» letters (comma-separated), without access to /ops
    # Before a document / «Дело под ключ» bill: the case owner confirms a phone by SMS code (an e-mail code when SMS
    # sign-in is not configured), so the case is never lost with the browser and the document and reminders reach
    # them. Telegram users are reachable in the bot and are not asked.
    payment_requires_contact: bool = True
    # Plans. A document costs the scenario price (1 990 ₸) and unlocks one document; «Дело под ключ» unlocks every
    # document of one case; «Бизнес» / «Бизнес Про» are subscriptions of PLAN_PERIOD_DAYS with a document limit.
    plan_case_price: int = 9990
    plan_biz_price: int = 29990
    plan_biz_documents: int = 20
    plan_bizpro_price: int = 59990
    plan_bizpro_documents: int = 60
    plan_period_days: int = 30
    plan_currency: str = ""  # empty: the currency of the jurisdiction pack
    # Library of official pages (konsilier/official, docs/official-library.md): the domains and seed pages of each
    # country pack (packs/<cc>/sources/official.yaml) are refreshed every night at OFFICIAL_CRAWL_HOUR (pack local
    # time) for at most OFFICIAL_CRAWL_MINUTES; the chat searches what is stored. Off by default (tests, dev):
    # production sets OFFICIAL_CRAWL_ENABLED=true. Search works whenever pages are stored.
    official_crawl_enabled: bool = False
    official_crawl_hour: int = 3
    official_crawl_minutes: int = 20
    official_crawl_max_pages: int = 400  # per domain; a pack may set lower caps
    official_search_enabled: bool = True
    chat_daily_limit: int = 40  # free consultation chat: messages per person per day (each one is a paid API call)
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
    # work after a request (document text ahead, paid document, PDF): thread | inline | off (tests)
    background_jobs: str = "thread"
    # production smoke checks (deploy/smoke.py): X-Smoke-Token opens /v1/smoke/* — a marked test user and the
    # confirmation of that user's own bills; empty = the endpoints are off
    smoke_token: str = ""

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
    email_from: str = "Konsiliér AI <no-reply@konsilier.com>"
    sms_provider: str = ""  # mobizon | smsc | log ("log" only for development)
    sms_api_key: str | None = None  # Mobizon API key
    smsc_login: str | None = None
    smsc_password: str | None = None
    sms_sender: str | None = None  # registered alpha name, if any
    ncanode_url: str | None = None  # e.g. http://ncanode:14579 — enables ЭЦП and eGov Mobile checks
    egov_org_bin: str | None = None  # BIN shown in eGov Mobile; eGov Mobile sign-in is off without it
    egov_org_name: str = "Konsiliér AI"
    phone_default_country_code: str = "7"  # for numbers typed without "+"
    dev_show_codes: bool = False  # tests/dev only: return the one-time code in the API response

    telegram_bot_token: str | None = None
    # Web push (notifications on the phone / computer, the installed app included): a VAPID key pair printed by
    # deploy/vapid_keys.py. Empty → push is off (GET /v1/push/key answers 404 and nothing is sent).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:support@konsilier.com"  # the push services' contact for this sender
    # Beta scenarios (tender bid, admission, visa, business…): off in production, on in dev and tests.
    experimental_scenarios: bool = False
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
