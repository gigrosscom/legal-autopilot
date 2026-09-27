"""Wiring: builds all services from settings. Tests build it with fakes."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .core.adapters.channels import ChannelAdapter, TelegramChannel, WebChannel
from .core.adapters.payment import StubPaymentAdapter
from .core.adapters.storage import Storage, build_storage
from .core.adapters.submission import EmailSubmission, UserSubmits
from .core.db import make_engine, make_session_factory
from .core.deadlines import DbDeadlineScheduler
from .core.documents import PdfConverter, build_pdf_converter
from .core.engine import CaseEngine, EngineConfig
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


def build_container(settings: Settings, *, llm: LLMProvider | None = None, storage: Storage | None = None,
                    pdf: PdfConverter | None = None, channels: dict[str, ChannelAdapter] | None = None,
                    packs: PackRegistry | None = None) -> Container:
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
        payments=StubPaymentAdapter(),
        submissions={"user_submits": UserSubmits(),
                     "email": EmailSubmission(settings.smtp_host, settings.smtp_port, settings.smtp_from)},
        config=EngineConfig(qualify_min_confidence=settings.qualify_min_confidence,
                            approval_required_first_n=settings.approval_required_first_n,
                            self_service=settings.self_service,
                            self_service_documents=tuple(d.strip() for d in settings.self_service_documents.split(",")
                                                         if d.strip()),
                            extract_images_with_llm=settings.extract_images_with_llm),
    )
    return Container(settings, db, factory, packs, storage, scheduler, notifier, engine)
