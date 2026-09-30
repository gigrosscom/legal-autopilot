"""«Юрист по кнопке» — the closed pilot (core/lawyer_pilot.py has the rules).

Client: GET /v1/cases/{id}/lawyers (pilot lawyers + the case's request), POST /v1/cases/{id}/lawyer-request with
application_id (api/lawyers.py), POST /v1/cases/{id}/lawyer-payment and /lawyer-payment/claim.
Lawyer: GET /v1/lawyer/requests, POST /v1/lawyer/requests/{id}/accept | decline, GET /v1/lawyer/cases/{id}/dossier,
GET /v1/lawyer/cases/{id}/evidence/{eid}.
Owner (admin token, command centre): GET /v1/admin/pilot-lawyers, POST /v1/admin/lawyer-applications/{id}/pilot.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..core import lawyer_pilot as pilot
from ..core.engine import EngineError
from ..core.models import (Case, ChatMessage, Deadline, Evidence, Invoice, LawyerApplication, LawyerRequest,
                           Notification, User)
from ..team import notify_team
from .deps import current_user, get_container, get_session, load_case, require_admin

router = APIRouter(prefix="/v1")
admin_router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])
log = logging.getLogger(__name__)


def tell_lawyer(session: Session, container: Container, app: LawyerApplication, subject: str, text: str,
                test: bool = False) -> None:
    """The lawyer's site inbox (when the application is tied to an account) and e-mail — best effort."""
    if app.user_id is not None:
        session.add(Notification(user_id=app.user_id, channel="web", kind="lawyer", text=text, delivered=True))
    email = app.email or (app.contact if "@" in (app.contact or "") else None)
    if test or not email or container.email_sender is None:
        return
    try:
        container.email_sender.send(email, subject, text)
    except Exception:  # noqa: BLE001 — a mail outage must not lose the request
        log.warning("e-mail to a lawyer failed", exc_info=True)


def _err(e: pilot.PilotError | EngineError) -> HTTPException:
    return HTTPException(409, {"code": e.code, "message": e.code})


# ------------------------------------------------------------------ client
def pilot_lawyer_view(pack: Any, app: LawyerApplication, lang: str) -> dict[str, Any]:
    kinds = pack.agreements.lawyer_kinds if pack.agreements is not None else {}
    title = pack.localized(kinds[app.kind], lang) if app.kind in kinds else app.kind
    return {"id": app.id, "name": app.full_name, "kind": app.kind, "kind_label": title[:1].upper() + title[1:],
            "organization": app.organization or "", "city": app.city or "",
            "specializations": [{"key": k, "label": pack.t(lang, f"categories.{k}", default=k)}
                                for k in (app.specializations or [])],
            "price": float(app.price), "currency": pack.currency, "price_note": app.price_note or ""}


@router.get("/cases/{case_id}/lawyers")
def case_lawyers(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> dict[str, Any]:
    """The pilot lawyers the case owner may send a request to (verified, in the pilot, with a price), the case's
    current request with its bill, and the latest request (to show «declined, choose another»)."""
    case = load_case(case_id, session, user)
    eng = container.engine
    pack = eng.pack_of(case)
    lang = pack.lang(case.language)
    country = case.jurisdiction or pack.country
    req = pilot.open_request(session, case)
    last = session.scalar(select(LawyerRequest).where(LawyerRequest.case_id == case.id,
                                                      LawyerRequest.application_id.is_not(None))
                          .order_by(LawyerRequest.id.desc()).limit(1))
    return {"lawyers": [pilot_lawyer_view(pack, a, lang) for a in pilot.pilot_lawyers(session, country)],
            "currency": pack.currency,
            "request": pilot.request_view(session, eng, req) if req is not None else None,
            "last": pilot.request_view(session, eng, last) if last is not None else None,
            "payment_available": pilot.channel(eng) is not None}


def _case_request(session: Session, case: Case) -> LawyerRequest:
    req = pilot.open_request(session, case)
    if req is None:
        raise HTTPException(404, {"code": "no_request", "message": "no_request"})
    return req


@router.post("/cases/{case_id}/lawyer-payment")
def lawyer_payment(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                   container: Container = Depends(get_container)) -> dict[str, Any]:
    """The bill for the accepted lawyer's price, to the company's account (never the personal Kaspi Gold); 409
    lawyer_payment_unavailable while the company's payment channel is not set up."""
    case = load_case(case_id, session, user)
    req = _case_request(session, case)
    try:
        pilot.create_invoice(session, container.engine, req, f"user:{user.id}")
    except pilot.PilotError as e:
        raise _err(e) from e
    session.flush()
    return {"request": pilot.request_view(session, container.engine, req)}


@router.post("/cases/{case_id}/lawyer-payment/claim")
def lawyer_payment_claim(case_id: uuid.UUID, user: User = Depends(current_user),
                         session: Session = Depends(get_session),
                         container: Container = Depends(get_container)) -> dict[str, Any]:
    """"I have paid": the desk (or the owner in the command centre) finds the payment and confirms it."""
    from .routes import _tell_desk_claimed

    case = load_case(case_id, session, user)
    req = _case_request(session, case)
    try:
        inv = container.engine.claim_payment(session, pilot.invoice_of(session, req), f"user:{user.id}")
    except EngineError as e:
        raise _err(e) from e
    session.flush()
    if inv.status == "awaiting_confirmation" and not user.is_test:
        _tell_desk_claimed(container, inv, f"дело {case.id}, запрос юристу №{req.id}")
    return {"request": pilot.request_view(session, container.engine, req)}


# ------------------------------------------------------------------ lawyer
def _lawyer_apps(session: Session, user: User) -> list[LawyerApplication]:
    apps = session.scalars(select(LawyerApplication).where(LawyerApplication.user_id == user.id,
                                                           LawyerApplication.status == "verified")).all()
    if not apps:
        raise HTTPException(403, {"code": "not_a_verified_lawyer", "message": "not_a_verified_lawyer"})
    return list(apps)


def _summary(container: Container, case: Case) -> dict[str, Any]:
    """What a lawyer sees before the client paid: the kind of case, not who the client is."""
    eng = container.engine
    pack = eng.pack_of(case)
    title = category = None
    if case.scenario_id:
        try:
            sc = eng.scenario_of(case)
            title = pack.localized(sc.title, "ru")
            category = pack.t("ru", f"categories.{(sc.ontology or '').split('.')[0].lower()}", default="") or None
        except Exception:  # noqa: BLE001 — a removed scenario must not hide the request
            title = case.scenario_id
    tax = case.taxonomy or {}
    if not category and pack.coverage is not None and tax.get("dispute_id") in pack.coverage.disputes:
        category = pack.localized(pack.coverage.dispute(tax["dispute_id"]).title, "ru")
    city = next((str(v) for k, v in (case.facts or {}).items() if k.endswith("city") and isinstance(v, str)), None)
    return {"title": title, "category": category, "city": city,
            "amount_at_stake": str(case.amount_at_stake) if case.amount_at_stake is not None else None,
            "currency": case.currency, "created_at": case.created_at.isoformat() if case.created_at else None}


def lawyer_request_view(session: Session, container: Container, req: LawyerRequest) -> dict[str, Any]:
    case = session.get(Case, req.case_id)
    inv = pilot.invoice_of(session, req)
    view = {"id": req.id, "status": req.status, "case_id": str(req.case_id), "created_at": req.created_at.isoformat(),
            "price": float(req.price) if req.price is not None else None,
            "currency": container.engine.pack_of(case).currency,
            "commission_pct": float(inv.commission_pct) if inv is not None and inv.commission_pct is not None
            else container.engine.config.lawyer_commission_pct,
            "summary": _summary(container, case), "client": None}
    if req.status in ("paid", "closed"):  # contacts only once the client paid
        view["client"] = {"name": req.full_name, "phone": req.phone, "email": req.email}
    return view


@router.get("/lawyer/requests")
def lawyer_requests(user: User = Depends(current_user), session: Session = Depends(get_session),
                    container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    ids = [a.id for a in _lawyer_apps(session, user)]
    rows = session.scalars(select(LawyerRequest).where(LawyerRequest.application_id.in_(ids))
                           .order_by(LawyerRequest.created_at.desc()).limit(200)).all()
    return [lawyer_request_view(session, container, r) for r in rows]


def _own_request(session: Session, user: User, req_id: int) -> LawyerRequest:
    ids = {a.id for a in _lawyer_apps(session, user)}
    req = session.get(LawyerRequest, req_id)
    if req is None or req.application_id not in ids:
        raise HTTPException(404, "request not found")
    return req


def _answer(req_id: int, accept: bool, user: User, session: Session, container: Container) -> dict[str, Any]:
    req = _own_request(session, user, req_id)
    try:
        pilot.decide(session, container.engine, req, accept, f"lawyer:{user.id}")
    except pilot.PilotError as e:
        raise _err(e) from e
    app = session.get(LawyerApplication, req.application_id)
    notify_team(container, f"«Юрист по кнопке»: юрист {pilot.lawyer_name(app)} "
                           f"{'принял' if accept else 'отклонил'} запрос №{req.id}",
                f"Дело: {req.case_id}\nКлиент: {req.full_name}, тел. {req.phone}\n"
                + ("Клиент оплачивает цену юриста на счёт компании; подтвердите оплату в оперативном центре."
                   if accept else "Клиент может выбрать другого юриста."), desk="clients",
                test=session.get(User, req.user_id).is_test)
    session.flush()
    return lawyer_request_view(session, container, req)


@router.post("/lawyer/requests/{req_id}/accept")
def accept_request(req_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
                   container: Container = Depends(get_container)) -> dict[str, Any]:
    return _answer(req_id, True, user, session, container)


@router.post("/lawyer/requests/{req_id}/decline")
def decline_request(req_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
                    container: Container = Depends(get_container)) -> dict[str, Any]:
    return _answer(req_id, False, user, session, container)


def _dossier_case(session: Session, user: User, case_id: uuid.UUID) -> tuple[Case, LawyerRequest]:
    """The case, only for the lawyer it is assigned to and only once the client paid for the lawyer's work."""
    ids = {a.id for a in _lawyer_apps(session, user)}
    case = session.get(Case, case_id)
    if case is None or case.lawyer_user_id != user.id or case.lawyer_application_id not in ids:
        raise HTTPException(403, {"code": "not_your_case", "message": "not_your_case"})
    req = session.scalar(select(LawyerRequest).where(
        LawyerRequest.case_id == case.id, LawyerRequest.application_id == case.lawyer_application_id,
        LawyerRequest.status.in_(("paid", "closed"))).order_by(LawyerRequest.id.desc()).limit(1))
    if req is None:
        raise HTTPException(403, {"code": "not_paid", "message": "not_paid"})
    return case, req


@router.get("/lawyer/cases/{case_id}/dossier")
def dossier(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
            container: Container = Depends(get_container)) -> dict[str, Any]:
    """The full case for the lawyer: the client's story, facts, evidence, deadlines and documents."""
    from .lawyers import _lawyer_block
    from .views import case_view

    case, req = _dossier_case(session, user, case_id)
    view = case_view(container.engine, session, case)
    story = [m.text for m in session.scalars(select(ChatMessage).where(
        ChatMessage.case_id == case.id, ChatMessage.role == "user").order_by(ChatMessage.created_at)).all()]
    deadlines = session.scalars(select(Deadline).where(Deadline.case_id == case.id)
                                .order_by(Deadline.due_date)).all()
    return {
        "case_id": str(case.id), "title": (view.get("scenario") or {}).get("title"), "status": view["status"],
        "status_label": view["status_label"],
        "client": {"name": req.full_name, "phone": req.phone, "email": req.email},
        "initial_text": case.initial_text, "narrative": case.narrative, "story": story,
        "facts": view["facts"], "amount_at_stake": view["amount_at_stake"], "currency": view["currency"],
        "evidence": [{"id": str(e.id), "kind": e.kind, "filename": e.filename, "has_file": bool(e.storage_key),
                      "text": e.text, "created_at": e.created_at.isoformat() if e.created_at else None}
                     for e in case.evidence],
        "deadlines": [{"due_date": d.due_date.isoformat(), "status": d.status, "norm_ref": d.norm_ref}
                      for d in deadlines],
        "documents": [{"id": a["id"], "title": a["title"], "status": a["status"], "has_pdf": a["has_pdf"],
                       "has_docx": a["has_docx"], "submitted_at": a["submitted_at"]} for a in view["actions"]],
        **_lawyer_block(session, container, case),
    }


@router.get("/lawyer/cases/{case_id}/evidence/{evidence_id}")
def dossier_evidence(case_id: uuid.UUID, evidence_id: uuid.UUID, user: User = Depends(current_user),
                     session: Session = Depends(get_session), container: Container = Depends(get_container)):
    case, _ = _dossier_case(session, user, case_id)
    ev = session.get(Evidence, evidence_id)
    if ev is None or ev.case_id != case.id or not ev.storage_key:
        raise HTTPException(404, "evidence not found")
    data = container.storage.get(ev.storage_key)
    name = (ev.filename or "file").replace('"', "")
    from urllib.parse import quote

    return Response(data, media_type=ev.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ------------------------------------------------------------------ owner (command centre)
def pilot_admin_view(session: Session, container: Container, a: LawyerApplication) -> dict[str, Any]:
    reqs = session.scalars(select(LawyerRequest).where(LawyerRequest.application_id == a.id)).all()
    return {"id": a.id, "full_name": a.full_name, "ecp_name": a.ecp_name, "kind": a.kind,
            "organization": a.organization, "city": a.city, "specializations": a.specializations or [],
            "status": a.status, "ecp_verified": bool(a.iin_hash), "has_account": a.user_id is not None,
            "pilot": bool(a.pilot), "price": float(a.price) if a.price is not None else None,
            "price_note": a.price_note or "", "listed": pilot.is_pilot_lawyer(a),
            "requests": {s: sum(1 for r in reqs if r.status == s) for s in ("new", "accepted", "declined", "paid")}}


@admin_router.get("/pilot-lawyers")
def pilot_lawyers(session: Session = Depends(get_session),
                  container: Container = Depends(get_container)) -> dict[str, Any]:
    """Verified lawyers, with whether they are in the pilot and their price; and whether lawyer payment is open."""
    rows = session.scalars(select(LawyerApplication).where(LawyerApplication.status == "verified")
                           .order_by(LawyerApplication.id)).all()
    ch = pilot.channel(container.engine)
    return {"lawyers": [pilot_admin_view(session, container, a) for a in rows],
            "commission_pct": container.engine.config.lawyer_commission_pct,
            "payment_available": ch is not None,
            "payment_channel": ["kaspi_pay_link"] * ("kaspi_pay_link" in (ch or {}))
            + ["company_account"] * ("company_account" in (ch or {}))}


class PilotIn(BaseModel):
    pilot: bool
    price: Decimal | None = Field(default=None, ge=0, le=100_000_000)
    price_note: str | None = Field(default=None, max_length=300)


@admin_router.post("/lawyer-applications/{app_id}/pilot")
def set_pilot(app_id: int, body: PilotIn, session: Session = Depends(get_session),
              container: Container = Depends(get_container)) -> dict[str, Any]:
    a = session.get(LawyerApplication, app_id)
    if a is None:
        raise HTTPException(404, "application not found")
    if body.pilot and a.status != "verified":
        raise HTTPException(409, {"code": "lawyer_not_verified", "message": "lawyer_not_verified"})
    if body.pilot and (body.price is None or body.price <= 0) and a.price is None:
        raise HTTPException(422, {"code": "price_required", "message": "price_required"})
    a.pilot = body.pilot
    if body.price is not None and body.price > 0:
        a.price = pilot.money(body.price)
    if body.price_note is not None:
        a.price_note = body.price_note.strip() or None
    return pilot_admin_view(session, container, a)


def lawyer_invoice_line(session: Session, inv: Invoice) -> dict[str, Any] | None:
    """For the desk / owner payment views: whose work the bill pays for, the commission and the payout."""
    if inv.purpose != pilot.PURPOSE:
        return None
    req = session.get(LawyerRequest, inv.lawyer_request_id) if inv.lawyer_request_id else None
    app = session.get(LawyerApplication, req.application_id) if req is not None and req.application_id else None
    return {"name": pilot.lawyer_name(app) if app is not None else None,
            "commission_pct": float(inv.commission_pct) if inv.commission_pct is not None else None,
            "commission_amount": float(inv.commission_amount) if inv.commission_amount is not None else None,
            "payout": float(pilot.payout(inv))}
