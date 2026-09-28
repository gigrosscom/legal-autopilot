"""Free consultation chat of a case: history, and a streamed reply from the fast model (konsilier/chat.py)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import Case, ChatMessage, Evidence, User
from ..core.pii import PiiVault
from .deps import current_user, get_container, get_session
from .questions import _case_for, _context

router = APIRouter(prefix="/v1")


def _view(m: ChatMessage) -> dict[str, Any]:
    return {"id": str(m.id), "role": m.role, "text": m.text, "created_at": m.created_at.isoformat(),
            "attachments": m.meta.get("attachments", []), "norms": m.meta.get("norms", []),
            "unchecked": bool(m.meta.get("unchecked"))}


def _evidence_note(session: Session, case: Case, vault: PiiVault) -> list[dict[str, Any]]:
    rows = session.scalars(select(Evidence).where(Evidence.case_id == case.id)).all()
    return [vault.redact_obj({"file": e.filename, "kind": e.kind, "facts": e.extracted_facts or {},
                              "text": (e.text or "")[:1500]}) for e in rows]


@router.get("/chat/info")
def info(container: Container = Depends(get_container)) -> dict[str, Any]:
    """Whether the chat is available and its daily limit; which AI answers is not disclosed to clients."""
    return {"available": container.chat_agent is not None, "daily_limit": container.settings.chat_daily_limit}


@router.get("/cases/{case_id}/chat")
def history(case_id: uuid.UUID, user: User = Depends(current_user),
            session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    case = _case_for(session, case_id, user)
    rows = session.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id)
                           .order_by(ChatMessage.created_at, ChatMessage.id)).all()
    return [_view(m) for m in rows]


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    attachments: list[str] = Field(default_factory=list, max_length=10)  # evidence ids uploaded with this message


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
    sent = session.scalar(select(func.count()).select_from(ChatMessage).where(
        ChatMessage.user_id == user.id, ChatMessage.role == "user", ChatMessage.created_at > since)) or 0
    if sent >= container.settings.chat_daily_limit:
        raise HTTPException(429, {"code": "too_many_messages", "message": "too_many_messages"})

    names = {str(e.id): e.filename for e in case.evidence}
    attachments = [{"id": a, "filename": names[a]} for a in body.attachments if a in names]
    session.add(ChatMessage(case_id=case.id, user_id=user.id, role="user", text=body.text,
                            meta={"attachments": attachments}))
    session.flush()
    rows = session.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id)
                           .order_by(ChatMessage.created_at, ChatMessage.id)).all()
    ctx = _context(container, case)
    vault: PiiVault = ctx.pop("vault")
    pack = ctx["pack"]
    ctx["case"] = {**ctx["case"], "files": _evidence_note(session, case, vault)}
    turns = [{"role": m.role, "text": vault.redact(m.text)} for m in rows]
    lang = pack.lang(case.language)
    country = pack.localized(pack.manifest.name, "en") or pack.country
    portal = [s for s in pack.manifest.legal_sources if agent.portal_domain in str(s.url)]
    use_portal = bool(portal)
    ctx["key_acts"] = [{"code": a.code, "title": pack.localized(a.title, lang)} for s in portal for a in s.key_acts]
    case_pk, user_pk = case.id, user.id
    session.commit()  # the user's message is saved even if the reply fails

    def events() -> Iterator[str]:
        result = None
        try:
            for ev in agent.stream(turns, context=ctx, language=f"the language with ISO 639-1 code '{lang}'",
                                   country=country, use_portal=use_portal):
                if ev["type"] == "done":
                    result = ev["result"]
                else:
                    yield _sse(ev)
        except Exception as e:  # API down, no credits, …: the page shows a clear error
            yield _sse({"type": "error", "code": "agent_failed", "message": str(e)[:200]})
            return
        text = vault.restore(result.text) if result else ""
        with container.session_factory() as s:
            m = ChatMessage(case_id=case_pk, user_id=None, role="assistant", text=text,
                            meta={"norms": result.norms, "unchecked": result.unchecked,
                                  "tool_calls": result.tool_calls, "usage": result.usage})
            s.add(m)
            c = s.get(Case, case_pk)
            container.engine.audit(s, c, f"user:{user_pk}", "chat_reply", tokens=result.usage,
                                   unchecked=result.unchecked)
            s.commit()
            yield _sse({"type": "done", "message": _view(m)})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
