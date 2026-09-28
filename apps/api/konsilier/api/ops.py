"""Operations centre: two desks, each opened by its operators' verified e-mail (sign in with an e-mail code).

- lawyers desk: every application of an advocate, legal consultant or human-rights organisation;
- clients desk: every client question, complaint or suggestion, and every client request to a lawyer.

Which e-mails operate which desk: settings OPS_LAWYERS_EMAILS / OPS_CLIENTS_EMAILS (konsilier/team.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import LawyerApplication, LawyerRequest, Notification, SupportTicket, TicketMessage, User
from ..team import Desk, desks_of
from .deps import current_user, get_container, get_session
from .support import messages_of, ticket_view

router = APIRouter(prefix="/v1/ops")
log = logging.getLogger(__name__)


def operator(desk: Desk):
    def dep(user: User = Depends(current_user), container: Container = Depends(get_container)) -> User:
        if desk not in desks_of(container.settings, user.email):
            raise HTTPException(403, {"code": "not_operator", "message": "not_operator"})
        return user
    return dep


def _tell(session: Session, container: Container, user_id: Any, email: str | None, subject: str, text: str) -> None:
    """Reach the person: site inbox (if they have an account here) and e-mail (if they left one)."""
    if user_id:
        session.add(Notification(user_id=user_id, channel="web", kind="desk_message", text=text, delivered=True))
    if email and "@" in email and container.email_sender is not None:
        try:
            container.email_sender.send(email, subject, text)
        except Exception:  # noqa: BLE001
            log.warning("desk e-mail to a client failed", exc_info=True)


@router.get("/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_session),
       container: Container = Depends(get_container)) -> dict[str, Any]:
    desks = desks_of(container.settings, user.email)
    counts: dict[str, int] = {}
    if "lawyers" in desks:
        counts["lawyers"] = session.scalar(select(func.count()).select_from(LawyerApplication)
                                           .where(LawyerApplication.status == "new")) or 0
    if "clients" in desks:
        counts["clients"] = (session.scalar(select(func.count()).select_from(SupportTicket)
                                            .where(SupportTicket.status == "new")) or 0) + \
                            (session.scalar(select(func.count()).select_from(LawyerRequest)
                                            .where(LawyerRequest.status == "new")) or 0)
    return {"email": user.email, "desks": desks, "new": counts}


# ------------------------------------------------------------------ lawyers desk
@router.get("/lawyers/applications")
def applications(status: str | None = None, session: Session = Depends(get_session),
                 _: User = Depends(operator("lawyers"))) -> list[dict[str, Any]]:
    q = select(LawyerApplication).order_by(LawyerApplication.id.desc()).limit(500)
    if status:
        q = q.where(LawyerApplication.status == status)
    return [{"id": a.id, "created_at": a.created_at.isoformat(), "full_name": a.full_name, "kind": a.kind,
             "organization": a.organization, "license_number": a.license_number, "city": a.city,
             "specializations": a.specializations, "contact": a.contact, "message": a.message,
             "wants_expert": a.wants_expert, "status": a.status, "ecp_verified": bool(a.iin_hash),
             "ecp_name": a.ecp_name, "note": a.desk_note} for a in session.scalars(q).all()]


class AppUpdate(BaseModel):
    status: Literal["new", "verified", "rejected"] | None = None
    note: str | None = Field(default=None, max_length=4000)


@router.post("/lawyers/applications/{app_id}")
def update_application(app_id: int, body: AppUpdate, session: Session = Depends(get_session),
                       container: Container = Depends(get_container),
                       _: User = Depends(operator("lawyers"))) -> dict[str, Any]:
    a = session.get(LawyerApplication, app_id)
    if a is None:
        raise HTTPException(404, "application not found")
    if body.note is not None:
        a.desk_note = body.note
    if body.status and body.status != a.status:
        if body.status == "verified" and not a.iin_hash:
            # who signs papers with clients is known only from the ЭЦП certificate
            raise HTTPException(409, {"code": "ecp_required", "message": "ecp_required"})
        a.status = body.status
        if body.status == "verified":
            _tell(session, container, a.user_id, a.contact, "Konsiliér AI: заявка юриста подтверждена",
                  f"{a.full_name}, ваш статус проверен, доступ к кабинету юриста открыт: https://konsilier.com/lawyer")
        elif body.status == "rejected":
            _tell(session, container, a.user_id, a.contact, "Konsiliér AI: заявка юриста",
                  f"{a.full_name}, подтвердить статус по заявке не удалось. Если это ошибка, ответьте на это письмо "
                  f"или напишите на info@konsilier.com.")
    return {"id": a.id, "status": a.status, "note": a.desk_note}


# ------------------------------------------------------------------ clients desk
@router.get("/clients/tickets")
def tickets(status: str | None = None, session: Session = Depends(get_session),
            _: User = Depends(operator("clients"))) -> list[dict[str, Any]]:
    q = select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(500)
    if status:
        q = q.where(SupportTicket.status == status)
    rows = session.scalars(q).all()
    msgs = messages_of(session, [t.id for t in rows])
    return [ticket_view(t, msgs[t.id]) for t in rows]


class DeskReply(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/clients/tickets/{ticket_id}/reply")
def reply(ticket_id: int, body: DeskReply, session: Session = Depends(get_session),
          container: Container = Depends(get_container), op: User = Depends(operator("clients"))) -> dict[str, Any]:
    t = session.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(404, "ticket not found")
    session.add(TicketMessage(ticket_id=t.id, author="desk", operator=op.email, text=body.text.strip()))
    t.status, t.updated_at = "in_progress", datetime.now(timezone.utc)
    _tell(session, container, t.user_id, t.email, f"Konsiliér AI: ответ на обращение №{t.id}",
          f"{body.text.strip()}\n\nОбращение №{t.id}. Ответить можно на странице https://konsilier.com/support")
    session.flush()
    return ticket_view(t, messages_of(session, [t.id])[t.id])


class TicketStatus(BaseModel):
    status: Literal["new", "in_progress", "done"]


@router.post("/clients/tickets/{ticket_id}/status")
def ticket_status(ticket_id: int, body: TicketStatus, session: Session = Depends(get_session),
                  _: User = Depends(operator("clients"))) -> dict[str, Any]:
    t = session.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(404, "ticket not found")
    t.status, t.updated_at = body.status, datetime.now(timezone.utc)
    return {"id": t.id, "status": t.status}


@router.get("/clients/lawyer-requests")
def lawyer_requests(status: str | None = None, session: Session = Depends(get_session),
                    _: User = Depends(operator("clients"))) -> list[dict[str, Any]]:
    q = select(LawyerRequest).order_by(LawyerRequest.created_at.desc()).limit(500)
    if status:
        q = q.where(LawyerRequest.status == status)
    return [{"id": r.id, "case_id": str(r.case_id), "lawyer_ref": r.lawyer_ref, "full_name": r.full_name,
             "phone": r.phone, "email": r.email, "status": r.status, "note": r.desk_note,
             "created_at": r.created_at.isoformat()} for r in session.scalars(q).all()]


class RequestUpdate(BaseModel):
    status: Literal["new", "passed", "closed"] | None = None
    note: str | None = Field(default=None, max_length=4000)


@router.post("/clients/lawyer-requests/{req_id}")
def update_request(req_id: int, body: RequestUpdate, session: Session = Depends(get_session),
                   _: User = Depends(operator("clients"))) -> dict[str, Any]:
    r = session.get(LawyerRequest, req_id)
    if r is None:
        raise HTTPException(404, "request not found")
    if body.note is not None:
        r.desk_note = body.note
    if body.status:
        r.status = body.status
    return {"id": r.id, "status": r.status, "note": r.desk_note}
