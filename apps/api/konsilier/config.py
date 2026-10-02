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
    # Chat speed. Gemini 3 thinks before it writes; the chat asks for the least thinking so the first words come at
    # once (minimal | low | medium | high; empty → the model's default). A model that refuses it is asked again
    # without it.
    gemini_chat_thinking_level: str = "minimal"
    # The OpenAI-compatible free providers (Cerebras, Groq …): their models' thinking, sent as reasoning_effort.
    # "none" (P0 01.10): qwen on Cerebras otherwise spent the whole token limit thinking — a chat answer cut mid-word.
    chat_reasoning_effort: str = "none"
    # Token limit of one chat model round. Large on purpose: the answer's length is set by the prompt, the limit only
    # must never cut it (thinking tokens count against it too).
    chat_max_tokens: int = 4096
    # Chat speed: when GEMINI_MODEL has not started answering after this many seconds, the fallback models are asked
    # in parallel and the first to answer is used (0 → only after a failure). Measured 30.09: gemini-3.1-flash-lite
    # answered after 2–8 s (median ≈5 s), gemini-3.5-flash-lite and gemini-flash-lite-latest after ≈0.5–1 s. Shorter
    # than CHAT_FIRST_TOKEN_TIMEOUT, so a slow Gemini model is replaced by another Gemini model (the same answer
    # quality) before the next provider of the chain is asked. With a fast GEMINI_MODEL raise it to ≈1.
    gemini_hedge_after: float = 0.5
    # CHAT_PROVIDER=free: when the provider asked first has not started answering after this many seconds, the next
    # one is asked in parallel and the first to answer is used (0 → one after another, only after a failure).
    chat_first_token_timeout: float = 1.5
    # Articles of the law are cut from the Zann corpus copy (konsilier/zann/corpus.py) when it has the act; the
    # live portal is read only for acts not collected yet.
    law_texts_local: bool = True
    # Voice input for browsers without built-in speech recognition (POST /v1/transcribe, free Gemini only):
    # uploads per account and per IP address in a rolling hour.
    transcribe_per_user_hour: int = 30
    transcribe_per_ip_hour: int = 60
    # Live text while the person speaks (iOS app, browsers without speech recognition): the recording so far is sent
    # every ~1.5 s with partial=1 — Whisper on Groq when GROQ_API_KEY is set (its own free quota), else Gemini.
    transcribe_partial_per_user_hour: int = 900
    transcribe_partial_per_ip_hour: int = 1800
    groq_whisper_model: str = "whisper-large-v3-turbo"
    # When every Gemini model fails before the reply starts, answer with Claude (fast model) if it is configured.
    # Off by default: the free chat does not fall back to a paid model unless this is switched on explicitly.
    chat_fallback_to_anthropic: bool = False
    # The paid model (Claude) is used only for what documents need; everything else stays on free models.
    # Chat and "questions on the case" never use it unless switched on here explicitly.
    anthropic_for_chat: bool = False
    anthropic_for_questions: bool = False
    # Spend guard for documents: tasks allowed on the paid model and hard budgets (USD, UTC day / month). Over a
    # budget the free model (Gemini) takes over and the operators are e-mailed once a day.
    llm_allowed_tasks: str = "qualify,classify_taxonomy,extract_fields,extract_evidence,narrative,generic_demands,classify_response"
    llm_daily_budget_usd: float = 3.0
    llm_monthly_budget_usd: float = 50.0
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
    # Command centre (/ops, konsilier/api/command.py): the team's files (team/*.md, *.csv — sessions, decisions,
    # backlog, reports) live in a git branch, not on the server. TEAM_DIR: read them from a local folder (a checkout
    # of that branch; the folder that holds team/). Otherwise they are fetched from GitHub (TEAM_GITHUB_REPO at
    # TEAM_GITHUB_REF) — with TEAM_GITHUB_TOKEN (read-only, contents) when the repository is private — and cached.
    team_dir: str = ""
    team_github_repo: str = "gigrosscom/legal-autopilot"
    team_github_ref: str = "claude/ai-team"
    team_github_token: str = ""
    team_cache_seconds: int = 300
    terms_version: str = "2026-09-29"  # current wording of the Terms of Use (apps/web/lib/legal/terms.ts)
    # Document payment (konsilier/core/adapters/payment.py): manual_transfer — a transfer to the Kaspi number below,
    # confirmed by the clients desk in /ops; stub — every invoice is paid at once (tests, development only).
    # Recipient and number live only in the server's .env; while either is empty, documents are not issued.
    payment_mode: str = "manual_transfer"
    payment_recipient_name: str = ""  # recipient's name as the payer's banking app shows it
    payment_kaspi_phone: str = ""  # Kaspi number to transfer to
    payment_comment_prefix: str = ""  # optional prefix of the payment code in the transfer comment
    payment_notify_emails: str = ""  # also get «клиент оплатил» letters (comma-separated), without access to /ops
    # More ways to pay, all confirmed by the desk as today (docs/kaspi-pay-plan.md). Off while empty; comma-separated:
    # kaspi_link, kaspi_qr, kaspi_invoice, bank_invoice. A way shows only once what it needs is set below.
    payment_methods: str = ""
    payment_kaspi_pay_link: str = ""  # «Ссылка для оплаты» from the Kaspi Pay app (https://…)
    payment_kaspi_qr_image: str = ""  # URL of the printed Kaspi QR image of the point of sale
    # «Счёт на оплату» for companies / ИП (bank_invoice): the company's requisites, values only in the server's .env
    payment_llp_name: str = ""  # full name as registered, e.g. ТОО «…»
    payment_llp_bin: str = ""
    payment_llp_address: str = ""
    payment_llp_bank: str = ""
    payment_llp_iik: str = ""  # IBAN KZ…
    payment_llp_bik: str = ""
    payment_llp_kbe: str = "17"
    payment_llp_knp: str = "859"
    payment_llp_director: str = ""  # «Директор И. Фамилия» under the bill
    payment_llp_vat: bool = False  # VAT payer: «в т. ч. НДС», else «Без НДС»
    payment_invoice_due_days: int = 5
    # After the desk confirms: a letter with amount, date, what was bought and the link (not a fiscal receipt).
    payment_receipt_email: bool = False
    payment_kaspi_kassa: bool = False  # Kaspi Касса is on: the letter says Kaspi sends the fiscal receipt
    # Automatic confirmation, for when Kaspi issues its protocol under a contract: /v1/payments/kaspi/webhook
    # answers 404 until this is on and the secret is set (HMAC-SHA256 of the body in X-Konsilier-Signature).
    payment_kaspi_webhook: bool = False
    payment_kaspi_webhook_secret: str = ""
    # Kaspi Pay pushes (konsilier/kaspi_parse.py): a separate Android phone with the company's Kaspi Pay app and
    # MacroDroid posts every Kaspi Pay notification to /v1/payments/kaspi/push with this token in X-Konsilier-Token;
    # one push of the bill's amount within 60 min of «Оплатить» marks it paid at once. Empty → the endpoint is 404,
    # no 15-minute reminder and no stop on new bills (the desk confirms by hand, as before).
    payment_kaspi_push_token: str = ""
    # «Юрист по кнопке» (closed pilot): the client pays the lawyer's price to the COMPANY's account only — the Kaspi
    # Pay link of the ТОО (PAYMENT_KASPI_PAY_LINK, https://…) or the company's requisites below (name, tax number, IBAN,
    # bank as plain text). Never the Kaspi Gold of PAYMENT_KASPI_PHONE: with neither set, lawyer payment is off.
    # The platform keeps LAWYER_COMMISSION_PCT of the price; payouts to lawyers are manual in the pilot.
    lawyer_payment_account: str = ""
    lawyer_commission_pct: float = 15.0
    # «Юрист по кнопке», owner 01.10 «15 % по счёту ТОО раз в месяц»: the client pays the lawyer directly (the lawyer
    # sends the contract and the bill); the lawyer marks «оплачено клиентом» and pays the platform 15 % monthly by the
    # company's bill. Off — the client pays the lawyer's price to the company's account (PR #105).
    lawyer_pay_direct: bool = False
    # Before a document / «Дело под ключ» bill: the case owner confirms a phone by SMS code (an e-mail code when SMS
    # sign-in is not configured), so the case is never lost with the browser and the document and reminders reach
    # them. Telegram users are reachable in the bot and are not asked.
    # owner 01.10 («3 клика»): no separate contact code before paying — the person is identified by the ЭЦП /
    # eGov Mobile signature of the document; true brings the code back
    payment_requires_contact: bool = False
    # Plans. A document costs the scenario price (1 990 ₸) and unlocks one document; «Дело под ключ» unlocks every
    # document of one case; «Бизнес» / «Бизнес Про» are subscriptions of PLAN_PERIOD_DAYS with a document limit.
    plan_case_price: int = 9990
    # owner 01.10: with the Kaspi Pay link «Оплатить» gives the document at once; the desk matches the payment in /ops
    # («Не найдена» → the person owes it and gets no new document until paid). false → only after the desk confirms
    payment_trust_kaspi_link: bool = True
    # owner 02.10 «пока не настроим платёжку — выдаём документы на доверии»: «Я оплатил(а)» gives the document at once
    # for EVERY way to pay (transfer, Kaspi QR, Kaspi bill, company bill), not only the Kaspi Pay link; the desk still
    # matches each bill in /ops. false → only the Kaspi Pay link is trusted (PAYMENT_TRUST_KASPI_LINK)
    payment_trust_all: bool = True
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
    # Zann law corpus (konsilier/zann/corpus.py, docs/zann-llm-plan.md «Сбор корпуса»): every act of old.adilet.zan.kz,
    # ru + kk, gzip texts in the storage under zann/corpus/. Off by default. ZANN_CORPUS_HOUR: local hour
    # (ZANN_CORPUS_TZ) of the nightly run, which lasts at most ZANN_CORPUS_MINUTES (2:00–2:50, before the 03:00 official crawl);
    # -1 = continuous: time-boxed runs back to back around the clock. Pause between one worker's requests ≥ 2 s.
    # ZANN_CORPUS_CONCURRENCY workers (1 = one request at a time, as before) share one limit of ZANN_CORPUS_RATE
    # requests a second in all (capped at 3; the robots Crawl-delay if longer); a 429/503 pauses every worker.
    zann_corpus_enabled: bool = False
    zann_corpus_hour: int = 2
    zann_corpus_minutes: int = 50
    zann_corpus_pause: float = 3.0
    zann_corpus_concurrency: int = 1
    zann_corpus_rate: float = 0.5
    zann_corpus_langs: str = "ru,kk"
    zann_corpus_statuses: str = "in_force"  # in_force | in_force,lost (acts that lost force, after all in force)
    zann_corpus_refresh_days: int = 30  # walk the listings again and re-read texts older than this (0 = never)
    zann_corpus_tz: str = "Asia/Almaty"  # the portal's time zone: ZANN_CORPUS_HOUR is local time there
    # Nightly pass over recently changed acts (the index sorted by the date of change): once a day, the first run
    # after ZANN_CORPUS_RECENT_HOUR local time (-1 = off) reads at most ZANN_CORPUS_RECENT_PAGES pages of 100 acts
    # and puts new and changed acts at the head of the queue; the 30-day walk (ZANN_CORPUS_REFRESH_DAYS) stays.
    zann_corpus_recent_hour: int = 2
    zann_corpus_recent_pages: int = 20
    # Zann court practice (konsilier/zann/court.py, docs/zann-court.md; owner 01.10.2026): what a country's courts
    # publish openly — sources, categories and anonymisation rules are pack data (packs/<cc>/zann/court.yaml,
    # anonymize.yaml); originals and texts gzip under zann/court/ in our storage only. Off by default.
    # ZANN_COURT_COUNTRY: the pack (empty: the only pack with zann/court.yaml). ZANN_COURT_SOURCES: empty = all the
    # pack's sources. ZANN_COURT_HOUR: local hour of the nightly run (4:00–4:50, after the corpus and the official
    # crawl), -1 = continuous. ZANN_COURT_PAUSE: seconds between requests (≥ 0.5); a site's robots.txt Crawl-delay
    # is applied on top. ZANN_COURT_MAX_MB: larger files are skipped.
    zann_court_enabled: bool = False
    zann_court_country: str = ""
    zann_court_hour: int = 4
    zann_court_minutes: int = 50
    zann_court_pause: float = 1.0
    zann_court_sources: str = ""
    zann_court_refresh_days: int = 30  # walk the pages again for new documents (0 = never)
    zann_court_max_mb: float = 60.0
    zann_court_tz: str = "Asia/Almaty"
    chat_daily_limit: int = 40  # free consultation chat: messages per person per day (each one is a paid API call)
    anthropic_api_key: str | None = None
    llm_refusal_fallback: str = "default"
    # Images cannot be PII-redacted; send them to the LLM only if explicitly enabled.
    # owner 01.10: photos and scans of documents are read by the model (they cannot be anonymised; the owner agreed)
    extract_images_with_llm: bool = True

    qualify_min_confidence: float = 0.6
    # PM 01.10: the draft after at most this many interview questions (the rest are blanks); 0 = no cap
    intake_max_questions: int = -1  # -1: the draft at once on the site (owner 01.10, «3 клика»)
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
    # «Отправить по e-mail» from a case (owner 01.10.2026): the client's paid document goes to the other side from
    # this address, Reply-To and a copy to the client. Needs RESEND_API_KEY and the domain verified in Resend.
    claims_email_from: str = "Konsiliér AI <claims@konsilier.com>"
    # Resend delivery webhooks (/v1/webhooks/resend, Svix signature): the «whsec_…» signing secret; empty → 404
    resend_webhook_secret: str = ""
    # replies from the other side into the case: Reply-To also claims+<token>@<domain of CLAIMS_EMAIL_FROM> and
    # «[K-<token>]» in the subject; Resend's «email.received» webhook attaches the reply. Needs receiving turned on
    # for that domain in Resend (MX record) — off until then.
    claims_inbound: bool = False
    # where replies are received (e.g. reply.konsilier.com): a subdomain keeps the main domain's mailbox untouched;
    # empty → the domain of CLAIMS_EMAIL_FROM
    claims_reply_domain: str = ""
    email_send_per_document: int = 3  # letters per document (failed attempts do not count)
    email_send_per_case_day: int = 5  # letters per case in 24 hours
    email_send_per_user_hour: int = 10  # attempts per person in an hour
    send_followup_hours: float = 2.0  # «Ответили?» this long after sending (owner 01.10: 2–3 hours, not a day)
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
    # «Войти через Google» / «Войти через Apple» (docs/auth-google-apple.md). Public ids, not secrets; empty → the
    # button is hidden. GOOGLE_CLIENT_ID: OAuth client (Web) of Google Cloud. APPLE_SERVICES_ID: the Services ID of
    # Sign in with Apple (e.g. com.konsilier.web); APPLE_REDIRECT_URI: its return URL, empty → PUBLIC_SITE_URL/account.
    google_client_id: str | None = None
    apple_services_id: str | None = None
    apple_redirect_uri: str | None = None

    telegram_bot_token: str | None = None
    # Web push (notifications on the phone / computer, the installed app included): a VAPID key pair printed by
    # deploy/vapid_keys.py. Empty → push is off (GET /v1/push/key answers 404 and nothing is sent).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:support@konsilier.com"  # the push services' contact for this sender
    # Beta scenarios (tender bid, admission, visa, business…): off in production, on in dev and tests.
    experimental_scenarios: bool = False
    # Beta scenarios kept off even with EXPERIMENTAL_SCENARIOS=true (owner 30.09: no study and visas, legal ones only)
    beta_scenarios_off: str = ("kz.services.university_admission,kz.services.study_abroad,kz.services.visa_schengen_de,"
                               "kz.services.visa_uk,kz.services.visa_us")
    cors_origins: str = "http://localhost:3000"

    @property
    def apple_return_url(self) -> str:
        return self.apple_redirect_uri or f"{self.public_site_url.rstrip('/')}/account"

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
