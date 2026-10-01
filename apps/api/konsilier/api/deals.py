"""The owner's boards in the command centre (owner 01.10): every real client's deal from the first question to the
answer, and the clients' questions to the desk. Views only — the columns come from the case status and its bill,
no new statuses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import Action, Case, Deadline, Invoice, SupportTicket, User
from .deps import get_container, get_session, require_admin
from .support import messages_of, ticket_view
from ..team import is_test_text, is_test_user

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])

DEAL_COLUMNS = (
    ("new", "Новый вопрос"), ("intake", "Сбор данных"), ("to_pay", "Готов к оплате"),
    ("confirm", "Ждёт подтверждения оплаты"), ("paid", "Оплачено"), ("ready", "Документ готов"),
    ("sent", "Отправлено"), ("closed", "Ответ получен / Закрыто"),
)


def is_test_owner(u: User | None) -> bool:
    return u is None or is_test_user(u)


def is_test_case(case: Case, owner: User | None) -> bool:
    """A QA / smoke deal: a test account, or a test name typed as the applicant («Тест», «Person 0456»…)."""
    return is_test_owner(owner) or is_test_text((case.facts or {}).get("applicant_name"))


def _bill(session: Session, case: Case) -> Invoice | None:
    return session.scalars(select(Invoice).where(Invoice.case_id == case.id, Invoice.purpose.in_(("document", "case")),
                                                 Invoice.status != "cancelled")
                           .order_by(Invoice.created_at.desc()).limit(1)).first()


def deal_column(case: Case, bill: Invoice | None) -> str:
    st = case.status
    if st == "intake":
        return "intake" if case.scenario_id else "new"
    if st == "qualified":
        if bill is not None and bill.status == "awaiting_confirmation":
            return "confirm"
        if case.paid or (bill is not None and bill.status == "paid"):
            return "paid"
        return "to_pay"
    if st == "action_ready":
        return "paid" if any(a.approval_status == "pending" for a in case.actions) else "ready"
    if st in ("submitted", "awaiting_response"):
        return "sent"
    return "closed"  # escalated, handed to a lawyer, resolved


def deal_card(container: Container, session: Session, case: Case, owner: User | None) -> dict[str, Any]:
    pack = container.engine.pack_of(case)
    lang = pack.lang(case.language)
    title = case.scenario_id
    if case.scenario_id:
        try:
            title = pack.localized(container.packs.scenario(case.scenario_id).title, lang)
        except KeyError:
            pass
    bill = _bill(session, case)
    due = session.scalars(select(Deadline).where(Deadline.case_id == case.id, Deadline.status == "active")
                          .order_by(Deadline.due_date).limit(1)).first()
    contacts = [x for x in (owner.email if owner else None, owner.phone if owner else None) if x]
    if owner is not None and not contacts:
        contacts = [i.display for i in owner.identities if i.kind in ("email", "phone") and i.display]
    return {
        "id": str(case.id), "column": deal_column(case, bill), "title": title or (case.initial_text or "")[:80],
        "status_label": pack.t(lang, f"statuses.{case.status}", default=case.status),
        "amount_at_stake": float(case.amount_at_stake) if case.amount_at_stake is not None else None,
        "currency": case.currency or pack.currency, "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        "bill": {"code": bill.code, "status": bill.status, "amount": float(bill.amount), "purpose": bill.purpose}
        if bill else None,
        "client": {"name": (owner.display_name if owner else None) or "", "contacts": contacts,
                   "channel": owner.channel if owner else None,
                   "ecp": bool(owner and any(i.kind == "iin" for i in owner.identities))},
        "deadline": due.due_date.isoformat() if due else None,
        "pending_review": [str(a.id) for a in case.actions if a.approval_status == "pending"],
        "documents": [{"id": str(a.id), "action_id": a.action_id, "status": a.status, "pdf": bool(a.pdf_key),
                       "docx": bool(a.docx_key)} for a in case.actions],
    }


@router.get("/deals")
def deals(limit: int = 500, tests: bool = False, session: Session = Depends(get_session),
          container: Container = Depends(get_container)) -> dict[str, Any]:
    """Real clients, newest first in each column; QA / smoke deals only with tests=true, marked «test»."""
    cards: dict[str, list[dict[str, Any]]] = {k: [] for k, _ in DEAL_COLUMNS}
    owners: dict[Any, User | None] = {}
    for case in session.scalars(select(Case).order_by(Case.updated_at.desc()).limit(min(limit, 2000))):
        if case.owner_id not in owners:
            owners[case.owner_id] = session.get(User, case.owner_id)
        owner = owners[case.owner_id]
        test = is_test_case(case, owner)
        if test and not tests:
            continue
        card = deal_card(container, session, case, owner)
        card["test"] = test
        cards[card["column"]].append(card)
    now = datetime.now(timezone.utc)
    paid = session.scalars(select(Invoice).where(Invoice.status == "paid", Invoice.decided_at.is_not(None),
                                                 Invoice.decided_at >= now - timedelta(days=7))).all()
    real_paid = [i for i in paid if not is_test_owner(session.get(User, i.user_id))]

    def total(since: datetime) -> float:
        return float(sum((i.amount for i in real_paid if i.decided_at and i.decided_at >= since), Decimal(0)))
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    waiting = len(cards["confirm"]) + sum(1 for c in cards["paid"] if c["pending_review"])
    return {"columns": [{"id": k, "label": label, "cards": cards[k]} for k, label in DEAL_COLUMNS],
            "paid_today": total(today), "paid_week": total(now - timedelta(days=7)),
            "currency": real_paid[0].currency if real_paid else None,
            "waiting_for_owner": waiting}


TICKET_COLUMNS = (("new", "Новые"), ("in_progress", "В работе"), ("answered", "Ответ дан"), ("done", "Закрыто"))


def ticket_column(t: SupportTicket, last_author: str | None) -> str:
    if t.status == "done":
        return "done"
    if last_author == "desk":
        return "answered"
    return "in_progress" if t.status == "in_progress" else "new"


@router.get("/tickets")
def tickets(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.scalars(select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(500)).all()
    msgs = messages_of(session, [t.id for t in rows])
    cols: dict[str, list[dict[str, Any]]] = {k: [] for k, _ in TICKET_COLUMNS}
    for t in rows:
        last = msgs[t.id][-1].author if msgs[t.id] else None
        cols[ticket_column(t, last)].append(ticket_view(t, msgs[t.id]))
    return {"columns": [{"id": k, "label": label, "cards": cols[k]} for k, label in TICKET_COLUMNS]}


class TicketMove(BaseModel):
    status: Literal["new", "in_progress", "done"]


@router.post("/tickets/{ticket_id}/status")
def move_ticket(ticket_id: int, body: TicketMove, session: Session = Depends(get_session)) -> dict[str, Any]:
    t = session.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(404, "ticket not found")
    t.status, t.updated_at = body.status, datetime.now(timezone.utc)
    return {"id": t.id, "status": t.status}


class FactsFix(BaseModel):
    values: dict[str, str]
    rebuild: bool = True


@router.post("/cases/{case_id}/facts")
def fix_facts(case_id: str, body: FactsFix, session: Session = Depends(get_session),
              container: Container = Depends(get_container)) -> dict[str, Any]:
    """The owner corrects a case's data (a wrong name, the client's own e-mail put as the seller's) and the documents
    not yet sent are made again. An empty value clears the field."""
    import uuid

    case = session.get(Case, uuid.UUID(case_id))
    if case is None or not case.scenario_id:
        raise HTTPException(404, "case not found")
    engine = container.engine
    sc, pack = engine.scenario_of(case), engine.pack_of(case)
    clear = {k for k, v in body.values.items() if not v.strip()}
    case.facts = {k: v for k, v in case.facts.items() if k not in clear}
    llm = engine.llm_for(case)
    errors = engine._apply_values(case, sc, pack, {k: v for k, v in body.values.items() if k not in clear}, llm,
                                  strict=True, overwrite=True)
    engine._save_vault(case, llm)
    if errors:
        raise HTTPException(422, {"code": "invalid_facts", "message": "invalid_facts", "fields": errors})
    engine.audit(session, case, "admin", "facts_corrected", fields=sorted(body.values))
    rebuilt = engine.rebuild_documents(session, case) if body.rebuild else 0
    session.flush()
    return {"rebuilt": rebuilt, "facts": {k: str(v) for k, v in case.facts.items()}}
