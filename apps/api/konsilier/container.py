"""Wiring: builds all services from settings. Tests build it with fakes."""

from __future__ import annotations

from dataclasses import dataclass, field
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
from .core.packs import PackRegistry


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
    signature_verifier: SignatureVerifier | None = None
    reporter: Any = None
    law_agent: Any = None  # konsilier.lawagent.LawAgent when a real LLM is configured
    chat_agent: Any = None  # konsilier.chat.ChatAgent (fast model) when a real LLM is configured
    chat_fallback_agent: Any = None  # Claude, used when the Gemini chat fails before the reply starts

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


def build_container(settings: Settings, *, llm: LLMProvider | None = None, storage: Storage | None = None,
                    pdf: PdfConverter | None = None, channels: dict[str, ChannelAdapter] | None = None,
                    packs: PackRegistry | None = None, email_sender: Sender | None = None,
                    sms_sender: Sender | None = None, signature_verifier: SignatureVerifier | None = None) -> Container:
    db = make_engine(settings.database_url)
    factory = make_session_factory(db)
    packs = packs or PackRegistry.load(settings.packs_dir)
    storage = storage or build_storage(settings)
    channels = channels or {"web": WebChannel(), "telegram": TelegramChannel(settings.telegram_bot_token)}
    notifier = Notifier(channels)
    scheduler = DbDeadlineScheduler(factory, packs, notifier)
    engine = CaseEngine(
        packs=packs,
        llm=llm or build_provider(settings),
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
                            extract_images_with_llm=settings.extract_images_with_llm),
    )
    container = Container(settings, db, factory, packs, storage, scheduler, notifier, engine,
                     identities=Identities(settings.identity_secret),
                     email_sender=email_sender or build_email(settings),
                     sms_sender=sms_sender or build_sms(settings),
                     signature_verifier=signature_verifier or (NcaNode(settings.ncanode_url) if settings.ncanode_url else None))
    from .reports import CaseReporter

    container.reporter = CaseReporter(container)
    from .chat import ChatAgent
    from .lawagent.sources import Adilet

    adilet = Adilet()
    if settings.llm_provider == "anthropic":
        import anthropic

        from .lawagent.agent import LawAgent

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else anthropic.Anthropic()
        container.law_agent = LawAgent(client, settings.llm_model, adilet)
        claude_chat = ChatAgent(client, settings.llm_fast_model, adilet)
        if settings.chat_provider == "anthropic":
            container.chat_agent = claude_chat
        elif settings.chat_fallback_to_anthropic:
            container.chat_fallback_agent = claude_chat
    if settings.chat_provider == "gemini" and settings.gemini_api_key:
        from .gemini import GeminiClient

        fallback = tuple(m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip())
        container.chat_agent = ChatAgent(GeminiClient(settings.gemini_api_key, fallback_models=fallback),
                                         settings.gemini_model, adilet, web_search=False)
    scheduler.extra_jobs.append(container.reporter.tick)
    return container
