"""Clients write to the platform: a question, a complaint or a suggestion. The clients desk answers
(konsilier/api/ops.py); the reply comes to the client's e-mail and shows on the site."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import Case, SupportTicket, TicketMessage, User
from ..team import notify_team
from .deps import current_user, get_container, get_session

router = APIRouter(prefix="/v1")

KIND_RU = {"question": "Вопрос", "complaint": "Жалоба", "suggestion": "Предложение", "plan": "Заявка на тариф"}
PER_DAY = 10


def ticket_view(t: SupportTicket, messages: list[TicketMessage]) -> dict[str, Any]:
    return {"id": t.id, "kind": t.kind, "status": t.status, "created_at": t.created_at.isoformat(),
            "case_id": str(t.case_id) if t.case_id else None, "name": t.name, "email": t.email, "phone": t.phone,
            "language": t.language,
            "messages": [{"id": m.id, "author": m.author, "text": m.text, "created_at": m.created_at.isoformat()}
                         for m in messages]}


def messages_of(session: Session, ticket_ids: list[int]) -> dict[int, list[TicketMessage]]:
    out: dict[int, list[TicketMessage]] = {i: [] for i in ticket_ids}
    if ticket_ids:
        for m in session.scalars(select(TicketMessage).where(TicketMessage.ticket_id.in_(ticket_ids))
                                 .order_by(TicketMessage.created_at, TicketMessage.id)).all():
            out[m.ticket_id].append(m)
    return out


class TicketIn(BaseModel):
    kind: Literal["question", "complaint", "suggestion", "plan"]  # plan: a request for a plan not paid online yet
    text: str = Field(min_length=5, max_length=4000)
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    case_id: uuid.UUID | None = None
    language: str | None = Field(default=None, max_length=8)


@router.post("/support", status_code=201)
def create_ticket(body: TicketIn, user: User = Depends(current_user), session: Session = Depends(get_session),
                  container: Container = Depends(get_container)) -> dict[str, Any]:
    email = (body.email or "").strip() or user.email
    phone = (body.phone or "").strip() or user.phone
    if not email and not phone:
        raise HTTPException(422, {"code": "contact_required", "message": "contact_required"})
    since = datetime.now(timezone.utc) - timedelta(days=1)
    if (session.scalar(select(func.count()).select_from(SupportTicket).where(
            SupportTicket.user_id == user.id, SupportTicket.created_at > since)) or 0) >= PER_DAY:
        raise HTTPException(429, {"code": "too_many", "message": "too_many"})
    case_id = None
    if body.case_id:
        case = session.get(Case, body.case_id)
        case_id = case.id if case is not None and case.owner_id == user.id else None
    t = SupportTicket(user_id=user.id, case_id=case_id, kind=body.kind, name=(body.name or "").strip() or None,
                      email=email, phone=phone, language=(body.language or user.language or "ru")[:8])
    session.add(t)
    session.flush()
    session.add(TicketMessage(ticket_id=t.id, author="client", text=body.text.strip()))
    session.flush()
    notify_team(container, f"{KIND_RU[t.kind]} №{t.id} от клиента",
                f"{t.name or 'Без имени'} · {t.email or ''} {t.phone or ''}\n"
                f"{'Дело: ' + str(t.case_id) if t.case_id else ''}\n\n{body.text.strip()}\n\n"
                f"Ответьте в оперативном центре: https://konsilier.com/ops", desk="clients")
    return ticket_view(t, messages_of(session, [t.id])[t.id])


@router.get("/support")
def my_tickets(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(SupportTicket).where(SupportTicket.user_id == user.id)
                           .order_by(SupportTicket.created_at.desc()).limit(50)).all()
    msgs = messages_of(session, [t.id for t in rows])
    return [ticket_view(t, msgs[t.id]) for t in rows]


class ClientReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/support/{ticket_id}/messages", status_code=201)
def client_reply(ticket_id: int, body: ClientReplyIn, user: User = Depends(current_user),
                 session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict[str, Any]:
    t = session.get(SupportTicket, ticket_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "ticket not found")
    session.add(TicketMessage(ticket_id=t.id, author="client", text=body.text.strip()))
    t.status, t.updated_at = "in_progress" if t.status == "done" else t.status, datetime.now(timezone.utc)
    session.flush()
    notify_team(container, f"Ответ клиента по обращению №{t.id}", body.text.strip(), desk="clients")
    return ticket_view(t, messages_of(session, [t.id])[t.id])
