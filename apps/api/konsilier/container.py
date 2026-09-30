"""Wiring: builds all services from settings. Tests build it with fakes."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .core.adapters.channels import ChannelAdapter, TelegramChannel, WebChannel
from .core.adapters.payment import build_payments
from .core.adapters.storage import Storage, build_storage
from .core.adapters.submission import EmailSubmission, UserSubmits
from .core.db import make_engine, make_session_factory
from .core.deadlines import DbDeadlineScheduler
from .core.documents import PdfConverter, build_pdf_converter
from .core.engine import CaseEngine, EngineConfig
from .identity.ncanode import NcaNode, SignatureVerifier
from .identity.senders import Sender, build_email, build_sms
from .identity.service import Identities
from .core.llm import LLMProvider, build_provider
from .core.notify import Notifier
from .core.push import PushSender, build_push
from .core.packs import PackRegistry

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    engine_db: Engine
    session_factory: sessionmaker[Session]
    packs: PackRegistry
    storage: Storage
    scheduler: DbDeadlineScheduler
    notifier: Notifier
    engine: CaseEngine
    identities: Identities = field(default_factory=lambda: Identities("change-me-identity"))
    email_sender: Sender | None = None
    sms_sender: Sender | None = None
    push_sender: PushSender | None = None  # web push, when VAPID keys are set
    signature_verifier: SignatureVerifier | None = None
    reporter: Any = None
    law_agent: Any = None  # konsilier.lawagent.LawAgent when a real LLM is configured
    chat_agent: Any = None  # konsilier.chat.ChatAgent (fast model) when a real LLM is configured
    chat_fallback_agent: Any = None  # Claude, used when the free chat fails before the reply starts (off by default)
    transcriber: Any = None  # konsilier.transcribe.GeminiTranscriber when a Gemini key is set (voice input)
    transcribe_limits: Any = None  # (per account, per IP) konsilier.transcribe.SlidingLimiter
    official_sources: dict[str, Any] = field(default_factory=dict)  # country → konsilier.official OfficialSources
    official_library: Any = None  # konsilier.official.search.OfficialLibrary, searched by the chat

    def law_agent_for(self, case: Any) -> Any:
        """The agent reads one official portal; it serves countries whose pack lists that portal as a source."""
        if self.law_agent is None:
            return None
        pack = self.engine.pack_of(case)
        portal = self.law_agent.portal_domain
        return self.law_agent if any(portal in str(s.url) for s in pack.manifest.legal_sources) else None

    def identity_methods(self) -> dict[str, bool]:
        ecp = self.signature_verifier is not None
        return {"email": self.email_sender is not None, "phone": self.sms_sender is not None,
                "ecp": ecp, "egov": ecp and bool(self.settings.egov_org_bin)}


def free_chat_clients(settings: Settings) -> list[Any]:
    """The free chat providers of CHAT_FREE_PROVIDERS, in that order, skipping those without a key."""
    from .gemini import GeminiClient
    from .openai_compat import PROVIDERS, OpenAICompatClient

    out: list[Any] = []
    for name in (n.strip() for n in settings.chat_free_providers.split(",") if n.strip()):
        if name == "gemini":
            if settings.gemini_api_key:
                fallback = tuple(m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip())
                out.append(GeminiClient(settings.gemini_api_key, fallback_models=fallback))
        elif name in PROVIDERS:
            key = getattr(settings, f"{name}_api_key", "")
            if key:
                out.append(OpenAICompatClient(name, key, getattr(settings, f"{name}_model", "")))
        else:
            raise ValueError(f"unknown chat provider {name!r} in CHAT_FREE_PROVIDERS")
    return out


def budgeted(provider: Any, settings: Settings, factory: Any) -> Any:
    """The paid model behind the spend guard (allowed tasks, daily and monthly budgets); the free Gemini model
    takes what the guard refuses. Free providers are returned as they are."""
    if settings.llm_provider not in ("anthropic", "bedrock"):
        return provider
    from .core.llm.spend import BudgetedProvider, SpendGuard

    fallback = None
    if settings.gemini_api_key:
        from .core.llm.gemini_provider import GeminiProvider

        fallback = GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    guard = SpendGuard(factory, daily_usd=settings.llm_daily_budget_usd, monthly_usd=settings.llm_monthly_budget_usd,
                       allowed_tasks={t.strip() for t in settings.llm_allowed_tasks.split(",") if t.strip()})
    return BudgetedProvider(provider, guard, fallback)


def build_container(settings: Settings, *, llm: LLMProvider | None = None, storage: Storage | None = None,
                    pdf: PdfConverter | None = None, channels: dict[str, ChannelAdapter] | None = None,
                    packs: PackRegistry | None = None, email_sender: Sender | None = None,
                    sms_sender: Sender | None = None, signature_verifier: SignatureVerifier | None = None) -> Container:
    db = make_engine(settings.database_url)
    factory = make_session_factory(db)
    packs = packs or PackRegistry.load(settings.packs_dir)
    if settings.experimental_scenarios:
        packs.experimental = True
    storage = storage or build_storage(settings)
    channels = channels or {"web": WebChannel(), "telegram": TelegramChannel(settings.telegram_bot_token)}
    notifier = Notifier(channels, packs)
    scheduler = DbDeadlineScheduler(factory, packs, notifier)
    engine = CaseEngine(
        packs=packs,
        llm=llm or budgeted(build_provider(settings), settings, factory),
        storage=storage,
        pdf=pdf or build_pdf_converter(settings),
        scheduler=scheduler,
        notifier=notifier,
        payments=build_payments(settings),
        submissions={"user_submits": UserSubmits(),
                     "email": EmailSubmission(settings.smtp_host, settings.smtp_port, settings.smtp_from)},
        config=EngineConfig(qualify_min_confidence=settings.qualify_min_confidence,
                            approval_required_first_n=settings.approval_required_first_n,
                            self_service=settings.self_service,
                            self_service_documents=tuple(d.strip() for d in settings.self_service_documents.split(",")
                                                         if d.strip()),
                            extract_images_with_llm=settings.extract_images_with_llm,
                            case_price=settings.plan_case_price,
                            plans={"biz": (settings.plan_biz_price, settings.plan_biz_documents),
                                   "bizpro": (settings.plan_bizpro_price, settings.plan_bizpro_documents)},
                            plan_days=settings.plan_period_days, plan_currency=settings.plan_currency),
    )
    engine.defer_pdf = settings.background_jobs == "thread"
    container = Container(settings, db, factory, packs, storage, scheduler, notifier, engine,
                     identities=Identities(settings.identity_secret),
                     email_sender=email_sender or build_email(settings),
                     sms_sender=sms_sender or build_sms(settings),
                     push_sender=build_push(settings),
                     signature_verifier=signature_verifier or (NcaNode(settings.ncanode_url) if settings.ncanode_url else None))
    notifier.outbound = container  # e-mail, SMS and push go through the container's senders
    from .reports import CaseReporter

    container.reporter = CaseReporter(container)
    from .chat import ChatAgent
    from .lawagent.sources import Adilet
    from .official import load_all
    from .official.search import OfficialLibrary

    container.official_sources = load_all(packs)
    library = OfficialLibrary(factory, container.official_sources) if settings.official_search_enabled else None
    container.official_library = library
    if settings.official_crawl_enabled and container.official_sources:
        from .official.job import NightlyCrawl

        scheduler.extra_jobs.append(NightlyCrawl(factory, packs, container.official_sources,
                                                 hour=settings.official_crawl_hour,
                                                 minutes=settings.official_crawl_minutes,
                                                 max_pages=settings.official_crawl_max_pages))
    from .transcribe import GeminiTranscriber, SlidingLimiter

    container.transcribe_limits = (SlidingLimiter(settings.transcribe_per_user_hour),
                                   SlidingLimiter(settings.transcribe_per_ip_hour))
    if settings.gemini_api_key:  # speech to text only ever uses the free Gemini models
        container.transcriber = GeminiTranscriber(settings.gemini_api_key, (
            settings.gemini_model, *(m.strip() for m in settings.gemini_fallback_models.split(","))))
    adilet = Adilet()
    if settings.llm_provider == "anthropic":
        import anthropic

        from .lawagent.agent import LawAgent

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else anthropic.Anthropic()
        if settings.anthropic_for_questions:  # off by default: questions on a case go to the free chat
            container.law_agent = LawAgent(client, settings.llm_model, adilet)
        if settings.anthropic_for_chat:  # off by default: the chat never spends the paid model's budget
            claude_chat = ChatAgent(client, settings.llm_fast_model, adilet, library=library)
            if settings.chat_provider == "anthropic":
                container.chat_agent = claude_chat
            elif settings.chat_fallback_to_anthropic:
                container.chat_fallback_agent = claude_chat
        elif settings.chat_provider == "anthropic" or settings.chat_fallback_to_anthropic:
            log.warning("chat on the paid model is off (ANTHROPIC_FOR_CHAT=false): the chat uses the free models")
    if settings.chat_provider == "gemini" and settings.gemini_api_key:
        from .gemini import GeminiClient

        fallback = tuple(m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip())
        container.chat_agent = ChatAgent(GeminiClient(settings.gemini_api_key, fallback_models=fallback),
                                         settings.gemini_model, adilet, web_search=False, library=library)
    if settings.chat_provider == "free":
        clients = free_chat_clients(settings)
        if clients:
            from .openai_compat import ChainClient

            container.chat_agent = ChatAgent(ChainClient(clients), settings.gemini_model, adilet, web_search=False,
                                             library=library)
    def approval_needed(session: Any, case: Any, action: Any) -> None:
        from .core.models import User
        from .team import notify_team

        owner = session.get(User, case.owner_id)
        notify_team(container, f"Документ ждёт проверки: {action.action_id}",
                    f"Клиент ждёт документ по делу {case.id} (сценарий {case.scenario_id}). "
                    f"Уверенность классификации: {case.qualification_confidence}.\n\n"
                    f"Проверьте и одобрите или верните: {settings.public_site_url.rstrip('/')}/admin",
                    desk="lawyers", test=bool(owner and owner.is_test))
    engine.on_approval_needed = approval_needed
    guard = getattr(engine.llm_provider, "guard", None)
    if guard is not None:
        from .team import notify_team

        guard.on_exhausted = lambda what: notify_team(
            container, "Лимит Claude исчерпан", f"{what}. До конца периода документы пишет бесплатная модель.",
            desk="lawyers")
    scheduler.extra_jobs.append(container.reporter.tick)
    scheduler.extra_jobs.append(container.engine.prepare_paid_documents)
    return container
