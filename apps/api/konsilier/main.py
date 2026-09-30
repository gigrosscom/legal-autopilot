from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import (admin, auth, chat, lawyers, metrics, ops, push, questions, referral, routes, signing, smoke, support,
                  transcribe)
from .config import Settings, get_settings
from .container import Container, build_container
from .core.engine import EngineError
from .core.state_machine import InvalidTransition


def create_app(settings: Settings | None = None, container: Container | None = None,
               start_scheduler: bool = True) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        c = app.state.container
        if start_scheduler:
            c.scheduler.start(settings.scheduler_interval_seconds)
        yield
        c.scheduler.stop()

    app = FastAPI(title="Konsilier API", version="0.1.0", lifespan=lifespan)
    if settings.identity_secret == "change-me-identity" and not settings.database_url.startswith("sqlite"):
        logging.getLogger(__name__).warning("IDENTITY_SECRET is the default: set a random value in production")
    app.state.container = container or build_container(settings)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(InvalidTransition)
    async def _invalid_transition(_: Request, exc: InvalidTransition):
        return JSONResponse(status_code=409, content={"detail": {"code": "invalid_transition", "message": str(exc)}})

    @app.exception_handler(EngineError)
    async def _engine_error(_: Request, exc: EngineError):
        return JSONResponse(status_code=409, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.get("/health")
    def health() -> dict:
        c = app.state.container
        return {"ok": True, "packs": sorted(c.packs.packs), "llm": settings.llm_provider}

    app.include_router(routes.router)
    app.include_router(admin.router)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(signing.router)
    app.include_router(lawyers.router)
    app.include_router(lawyers.admin_router)
    app.include_router(questions.router)
    app.include_router(chat.router)
    app.include_router(support.router)
    app.include_router(referral.router)
    app.include_router(ops.router)
    app.include_router(smoke.router)
    app.include_router(push.router)
    app.include_router(transcribe.router)
    return app


def app_factory() -> FastAPI:  # uvicorn --factory konsilier.main:app_factory
    return create_app()
