"""Free consultation chat of a case: history, and a streamed reply from the fast model (konsilier/chat.py)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..container import Container
from ..core.models import Case, ChatMessage, Evidence, User
from ..core.pii import PiiVault
from ..gemini import EmptyReply
from .deps import current_user, get_container, get_session
from .questions import _case_for, _context

router = APIRouter(prefix="/v1")
log = logging.getLogger(__name__)


# Shown when no model can answer right now (Gemini over quota, Claude off or over its daily budget).
BUSY = {
    "ru": "Сейчас большая нагрузка, повторите через минуту.",
    "kk": "Қазір жүктеме көп, бір минуттан кейін қайталаңыз.",
    "en": "We're under heavy load right now. Please try again in a minute.",
    "tr": "Şu anda yoğunluk var, lütfen bir dakika sonra tekrar deneyin.",
    "ar": "الضغط كبير الآن، يرجى المحاولة مرة أخرى بعد دقيقة.",
}


def provider_of(agent: Any) -> str:
    """For metrics and the Claude budget only; never shown to clients."""
    kind = type(getattr(agent, "client", None)).__name__
    return {"GeminiClient": "gemini", "ChainClient": "free"}.get(kind, "anthropic")


def _day_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def reply_cost_usd(usage: dict[str, Any], settings: Settings) -> float:
    """Estimated cost of one Claude reply from the token counts the API returned."""
    return (usage.get("input_tokens", 0) * settings.anthropic_price_input_per_mtok / 1e6
            + usage.get("output_tokens", 0) * settings.anthropic_price_output_per_mtok / 1e6
            + usage.get("web_search_requests", 0) * settings.anthropic_price_web_search)


def chat_usage_today(session: Session, settings: Settings) -> dict[str, Any]:
    """Replies by provider, refusals and the estimated Claude spend since 00:00 UTC (stored messages only, so the
    count survives restarts and is shared by all API workers)."""
    start = _day_start()
    rows = session.execute(select(ChatMessage.role, ChatMessage.meta)
                           .where(ChatMessage.created_at >= start)).all()
    out = {"gemini": 0, "free": 0, "anthropic": 0, "unavailable": 0}
    cost = 0.0
    for role, meta in rows:
        meta = meta or {}
        if role == "assistant" and meta.get("provider") in ("gemini", "free", "anthropic"):
            out[meta["provider"]] += 1
            if meta["provider"] == "anthropic":
                cost += reply_cost_usd(meta.get("usage") or {}, settings)
        elif role == "user" and meta.get("failed"):
            out["unavailable"] += 1
    budget = settings.chat_fallback_daily_budget_usd
    return {"day": start.date().isoformat(), **out, "anthropic_cost_usd": round(cost, 4),
            "anthropic_budget_usd": budget, "fallback_open": budget > 0 and cost < budget}


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, max(0, round(q * (len(v) - 1))))]


def chat_latency(session: Session, hours: int = 24) -> dict[str, Any]:
    """Time to the first words of chat replies over the last ``hours`` (ms, the reply's ``first_ms``): p50 / p95
    overall and by the provider that answered (``served_by``: cerebras, gemini … inside the free chain)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = session.scalars(select(ChatMessage.meta).where(ChatMessage.role == "assistant",
                                                          ChatMessage.created_at >= since)).all()
    by: dict[str, list[int]] = {}
    for meta in rows:
        meta = meta or {}
        if isinstance(meta.get("first_ms"), (int, float)):
            by.setdefault(str(meta.get("served_by") or meta.get("provider") or "?"), []).append(int(meta["first_ms"]))
    every = [v for vs in by.values() for v in vs]
    return {"hours": hours, "n": len(every), "p50_ms": _percentile(every, 0.5), "p95_ms": _percentile(every, 0.95),
            "by_provider": {k: {"n": len(v), "p50_ms": _percentile(v, 0.5), "p95_ms": _percentile(v, 0.95)}
                            for k, v in sorted(by.items())}}


def warm_chat(container: Container) -> None:
    """Open the chat providers' connections in the background (the chat page opened, a case is being created), so
    the person's message does not wait for a TLS handshake. Each client does it at most once a minute."""
    clients = [getattr(a, "client", None) for a in (container.chat_agent, container.chat_fallback_agent)]
    warm = [c.warm for c in clients if c is not None and callable(getattr(c, "warm", None))]
    if warm:
        threading.Thread(target=lambda: [w() for w in warm], name="chat-warm", daemon=True).start()


def _reason(provider: str, e: Exception) -> str:
    status = getattr(e, "status_code", None)
    if status is None and (m := re.match(r"gemini (\d{3})", str(e))):
        status = m.group(1)
    return f"{provider}_{status or type(e).__name__}"


def _view(m: ChatMessage) -> dict[str, Any]:
    return {"id": str(m.id), "role": m.role, "text": m.text, "created_at": m.created_at.isoformat(),
            "attachments": m.meta.get("attachments", []), "norms": m.meta.get("norms", []),
            "sources": m.meta.get("sources", []), "offer_document": bool(m.meta.get("offer_document"))}


def _evidence_note(session: Session, case: Case, vault: PiiVault) -> list[dict[str, Any]]:
    rows = session.scalars(select(Evidence).where(Evidence.case_id == case.id)).all()
    return [vault.redact_obj({"file": e.filename, "kind": e.kind, "facts": e.extracted_facts or {},
                              "text": (e.text or "")[:1500]}) for e in rows]


@router.get("/chat/info")
def info(container: Container = Depends(get_container)) -> dict[str, Any]:
    """Whether the chat is available and its daily limit; which AI answers is not disclosed to clients. The chat page
    asks this when it opens: the providers' connections are opened meanwhile."""
    warm_chat(container)
    return {"available": container.chat_agent is not None, "daily_limit": container.settings.chat_daily_limit}


@router.get("/cases/{case_id}/chat")
def history(case_id: uuid.UUID, user: User = Depends(current_user),
            session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    case = _case_for(session, case_id, user)
    rows = session.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id)
                           .order_by(ChatMessage.created_at, ChatMessage.id)).all()
    return [_view(m) for m in rows]


REPLY_LANGS = ("ru", "kk", "en", "tr", "ar")  # the web interface languages
# the person asks for a document themselves: then it may be offered in the very first reply
ASKS_FOR_DOCUMENT = re.compile(
    r"документ|претензи|жалоб|\bиск|заявлени|составь|составить|напиши|напишите|"
    r"құжат|талап|шағым|арыз|document|claim|complaint|lawsuit|letter|draft|belge|dilekçe|şikâyet|şikayet|"
    r"مستند|شكوى|دعوى|مطالبة", re.IGNORECASE)


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    attachments: list[str] = Field(default_factory=list, max_length=10)  # evidence ids uploaded with this message
    language: str | None = Field(default=None, max_length=5)  # the interface language: the reply is written in it


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/cases/{case_id}/chat")
def send(case_id: uuid.UUID, body: ChatIn, user: User = Depends(current_user),
         session: Session = Depends(get_session), container: Container = Depends(get_container)) -> StreamingResponse:
    case = _case_for(session, case_id, user)
    agent = container.chat_agent
    if agent is None:
        raise HTTPException(503, {"code": "agent_unavailable", "message": "agent_unavailable"})
    since = datetime.now(timezone.utc) - timedelta(days=1)
    # messages nobody could answer (overload) do not use up the daily limit
    metas = session.scalars(select(ChatMessage.meta).where(
        ChatMessage.user_id == user.id, ChatMessage.role == "user", ChatMessage.created_at > since)).all()
    sent = sum(1 for m in metas if not (m or {}).get("failed"))
    daily_limit = container.settings.chat_daily_limit
    if sent >= daily_limit:
        raise HTTPException(429, {"code": "too_many_messages", "message": "too_many_messages",
                                  "limit": daily_limit, "remaining": 0, "window_hours": 24})

    names = {str(e.id): e.filename for e in case.evidence}
    attachments = [{"id": a, "filename": names[a]} for a in body.attachments if a in names]
    asked = ChatMessage(case_id=case.id, user_id=user.id, role="user", text=body.text,
                        meta={"attachments": attachments})
    session.add(asked)
    session.flush()
    asked_pk = asked.id
    rows = session.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id)
                           .order_by(ChatMessage.created_at, ChatMessage.id)).all()
    ctx = _context(container, case)
    vault: PiiVault = ctx.pop("vault")
    pack = ctx["pack"]
    ctx["case"] = {**ctx["case"], "files": _evidence_note(session, case, vault)}
    turns = [{"role": m.role, "text": vault.redact(m.text)} for m in rows]
    lang = pack.lang(case.language)  # the pack's language for its titles (KZ: ru, kk)
    # the reply follows the person: the interface language they write from, else the case's language — not the pack's
    # fallback (an English page got Russian answers because the KZ pack has only ru and kk)
    reply_lang = (body.language or case.language or lang).split("-")[0].lower()
    if reply_lang not in REPLY_LANGS:
        reply_lang = lang
    country = pack.localized(pack.manifest.name, "en") or pack.country
    portal = [s for s in pack.manifest.legal_sources if agent.portal_domain in str(s.url)]
    use_portal = bool(portal)
    ctx["lang"] = lang
    ctx["case_id"] = str(case.id)
    ctx["key_acts"] = [{"code": a.code, "title": pack.localized(a.title, lang)} for s in portal for a in s.key_acts]
    case_pk, user_pk = case.id, user.id
    # a test account (production smoke checks, deploy/smoke.py): its replies carry where the time went, so the speed
    # can be measured from outside without the server logs; never for a real person
    diagnostics = bool(user.is_test)
    first_reply = not any(m.role == "assistant" for m in rows)
    session.commit()  # the user's message is saved even if the reply fails

    agents = [a for a in (agent, container.chat_fallback_agent) if a is not None]
    settings = container.settings

    def fallback_allowed() -> bool:
        with container.session_factory() as s:
            return chat_usage_today(s, settings)["fallback_open"]

    def unavailable(reason: str, started: bool) -> Iterator[str]:
        """No reply: say so in the person's language and give the message back to the daily limit."""
        log.warning("chat=unavailable reason=%s case=%s started=%s", reason, case_pk, int(started))
        with container.session_factory() as s:
            m = s.get(ChatMessage, asked_pk)
            if m is not None:
                m.meta = {**(m.meta or {}), "failed": reason}
                s.commit()
        ev = {"type": "error", "code": "agent_failed" if started else "busy", "message": BUSY.get(lang, BUSY["ru"])}
        if diagnostics:
            ev["reason"] = reason
        yield _sse(ev)

    t_request = time.perf_counter()

    def events() -> Iterator[str]:
        # waiting for a worker thread between the response and its first chunk (a busy server shows here)
        queue_ms = int((time.perf_counter() - t_request) * 1000)
        result, used, reasons, started = None, None, [], False
        first_ms: int | None = None  # how long the person waited for the first words
        for i, a in enumerate(agents):
            provider = provider_of(a)
            if i > 0 and provider == "anthropic" and not fallback_allowed():
                reasons.append("anthropic_budget")
                break
            started = False
            try:
                for ev in a.stream(turns, context=ctx, language=f"the language with ISO 639-1 code '{reply_lang}'",
                                   country=country, use_portal=use_portal):
                    if ev["type"] == "done":
                        result = ev["result"]
                    else:
                        started = started or ev["type"] == "text"
                        if started and first_ms is None:
                            first_ms = int((time.perf_counter() - t_request) * 1000)
                        yield _sse(ev)
                if result is None or not (result.text or "").strip():
                    # a reply never ends empty: the fallback, else «busy» (the message goes back to the limit)
                    raise EmptyReply(f"{provider}: empty reply")
                used = provider
                break
            except Exception as e:  # quota, API down, no credits, …: the fallback agent, else "try in a minute"
                reasons.append(_reason(provider, e))
                if started:
                    break
                if i < len(agents) - 1:
                    log.warning("chat agent failed before the reply started, trying the fallback: %s", str(e)[:200])
        if used is None or result is None:
            yield from unavailable("+".join(reasons) or "no_reply", started)
            return
        text = vault.restore(result.text) if result else ""
        if result.offer_document and first_reply and not ASKS_FOR_DOCUMENT.search(body.text):
            result.offer_document = False  # owner 30.09: never in the first reply — it scares people off
        # the agent's phases (library, each model round with the providers tried, each tool call and its source)
        timing = {**(getattr(result, "timing", None) or {}), "queue_ms": queue_ms}
        served_by = timing.get("provider") or used  # inside the free chain: cerebras, gemini …
        log.info("chat timing: case=%s summary %s", case_pk, json.dumps(
            {k: v for k, v in timing.items() if k not in ("rounds", "tools")} | {
                "first_ms": first_ms, "served_by": served_by, "rounds": len(timing.get("rounds", [])),
                "tools": [t.get("source") for t in timing.get("tools", [])]}))
        with container.session_factory() as s:
            m = ChatMessage(case_id=case_pk, user_id=None, role="assistant", text=text,
                            meta={"provider": used, "served_by": served_by, "norms": result.norms,
                                  "sources": result.sources, "unchecked": result.unchecked,
                                  "offer_document": result.offer_document, "tool_calls": result.tool_calls,
                                  "usage": result.usage, "first_ms": first_ms,
                                  "total_ms": int((time.perf_counter() - t_request) * 1000), "timing": timing})
            s.add(m)
            c = s.get(Case, case_pk)
            container.engine.audit(s, c, f"user:{user_pk}", "chat_reply", tokens=result.usage,
                                   unchecked=result.unchecked)
            s.commit()
            log.info("chat=reply case=%s provider=%s first_ms=%s total_ms=%s tools=%s", case_pk, used, first_ms,
                     m.meta.get("total_ms"), result.tool_calls)
            if result.unchecked:  # not shown to the person; the team watches how often it happens
                log.warning("chat=unchecked_norms case=%s", case_pk)
            # what is left of the daily limit (a rolling 24-hour window) after this answered message
            done = {"type": "done", "message": _view(m), "limit": daily_limit,
                    "remaining": max(daily_limit - sent - 1, 0), "window_hours": 24}
            if diagnostics:
                done["diagnostics"] = {"served_by": served_by, "first_ms": first_ms,
                                       "total_ms": m.meta.get("total_ms"), "timing": timing}
            yield _sse(done)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
