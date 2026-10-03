"""Lawyers on the platform: ЭЦП-tied applications, case assignment, the lawyer's cabinet, customer–lawyer papers.

A lawyer applies while signed in with ЭЦП (so the application carries who they are per the certificate);
an administrator checks the licence against the public registry and verifies the application, then assigns
cases. Assignment generates the pack's agreements (consent, engagement), which the customer and then the
lawyer sign with ЭЦП (see api/signing.py).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..team import notify_team
from ..core import lawyer_pilot as pilot
from ..core.lawyer_pilot import iin_identity, render_agreement  # noqa: F401 — kept importable from here
from ..core.models import Agreement, Case, LawyerApplication, LawyerRequest, User
from .deps import current_user, get_container, get_session, load_case, require_admin
from .signing import agreement_view, signature_view
from .views import case_view

router = APIRouter(prefix="/v1")
admin_router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])


def create_agreements(session: Session, container: Container, case: Case, app: LawyerApplication) -> list[Agreement]:
    return pilot.create_agreements(session, container.engine, case, app)


# ------------------------------------------------------------------ customer side
@router.get("/cases/{case_id}/lawyer")
def case_lawyer(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                container: Container = Depends(get_container)) -> dict[str, Any]:
    case = load_case(case_id, session, user)
    return _lawyer_block(session, container, case)


def _lawyer_block(session: Session, container: Container, case: Case) -> dict[str, Any]:
    if case.lawyer_application_id is None:
        return {"lawyer": None, "agreements": []}
    app = session.get(LawyerApplication, case.lawyer_application_id)
    pack = container.engine.pack_of(case)
    lang = pack.lang(case.language)
    ags = session.scalars(select(Agreement).where(Agreement.case_id == case.id,
                                                  Agreement.lawyer_application_id == app.id)).all()
    return {"lawyer": {"name": app.ecp_name or app.full_name, "kind": app.kind, "organization": app.organization},
            "agreements": [agreement_view(pack, a, lang) for a in ags]}


# ------------------------------------------------------------------ lawyer cabinet
def _verified_application(session: Session, user: User) -> LawyerApplication:
    app = session.scalar(select(LawyerApplication).where(LawyerApplication.user_id == user.id,
                                                         LawyerApplication.status == "verified"))
    if app is None:
        raise HTTPException(403, {"code": "not_a_verified_lawyer", "message": "not_a_verified_lawyer"})
    return app


@router.get("/lawyer/me")
def lawyer_me(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    apps = session.scalars(select(LawyerApplication).where(LawyerApplication.user_id == user.id)
                           .order_by(LawyerApplication.id.desc())).all()
    ident = iin_identity(session, user.id)
    for a in apps:  # applied first, confirmed ЭЦП later: the application now carries who they are
        if ident is not None and not a.iin_hash:
            a.iin_hash, a.ecp_name = ident.subject_hash, user.display_name
    return {"applications": [{"id": a.id, "status": a.status, "name": a.ecp_name or a.full_name, "kind": a.kind,
                              "reject_reason": a.reject_reason if a.status == "rejected" else None}
                             for a in apps],
            "verified": any(a.status == "verified" for a in apps),
            "has_ecp": ident is not None}


@router.get("/lawyer/cases")
def lawyer_cases(user: User = Depends(current_user), session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    _verified_application(session, user)
    cases = session.scalars(select(Case).where(Case.lawyer_user_id == user.id).order_by(Case.created_at.desc())).all()
    return [{**case_view(container.engine, session, c), **_lawyer_block(session, container, c)} for c in cases]


@router.get("/lawyer/cases/{case_id}")
def lawyer_case(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                container: Container = Depends(get_container)) -> dict[str, Any]:
    _verified_application(session, user)
    case = session.get(Case, case_id)
    if case is None or case.lawyer_user_id != user.id:
        raise HTTPException(404, "case not found")
    return {**case_view(container.engine, session, case), **_lawyer_block(session, container, case)}


@router.get("/lawyer/cases/{case_id}/actions/{action_id}/document")
def lawyer_document(case_id: uuid.UUID, action_id: uuid.UUID, format: Literal["docx", "pdf"] = "pdf",
                    user: User = Depends(current_user), session: Session = Depends(get_session),
                    container: Container = Depends(get_container)):
    from ..core.models import Action
    from .routes import document_response

    _verified_application(session, user)
    case = session.get(Case, case_id)
    action = session.get(Action, action_id)
    if case is None or case.lawyer_user_id != user.id or action is None or action.case_id != case.id:
        raise HTTPException(404, "not found")
    return document_response(container, action, format)


# ------------------------------------------------------------------ admin
class AppStatusIn(BaseModel):
    status: Literal["new", "verified", "rejected"]


@admin_router.post("/lawyer-applications/{app_id}/status")
def set_application_status(app_id: int, body: AppStatusIn, session: Session = Depends(get_session)) -> dict:
    app = session.get(LawyerApplication, app_id)
    if app is None:
        raise HTTPException(404, "application not found")
    if body.status == "verified" and not app.iin_hash:
        # the lawyer must have applied signed in with ЭЦП: that is how we know who signs their papers
        raise HTTPException(409, {"code": "ecp_required", "message": "ecp_required"})
    app.status = body.status
    return {"id": app.id, "status": app.status}


class AssignIn(BaseModel):
    application_id: int


@admin_router.post("/cases/{case_id}/assign")
def assign_lawyer(case_id: uuid.UUID, body: AssignIn, session: Session = Depends(get_session),
                  container: Container = Depends(get_container)) -> dict[str, Any]:
    case = session.get(Case, case_id)
    app = session.get(LawyerApplication, body.application_id)
    if case is None or app is None:
        raise HTTPException(404, "not found")
    try:
        ags = pilot.assign(session, container.engine, case, app, "admin")
    except pilot.PilotError as e:
        raise HTTPException(409, {"code": e.code, "message": e.code}) from e
    pack = container.engine.pack_of(case)
    return {"lawyer": {"name": app.ecp_name or app.full_name},
            "agreements": [agreement_view(pack, a, pack.lang(case.language)) for a in ags]}


__all__ = ["router", "admin_router", "signature_view"]


class LawyerRequestIn(BaseModel):
    lawyer_ref: str | None = Field(default=None, max_length=100)
    application_id: int | None = None  # «Юрист по кнопке»: the pilot lawyer the request goes to
    full_name: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=300)
    consent: bool = False


@router.post("/cases/{case_id}/lawyer-request", status_code=201)
def request_lawyer(case_id: uuid.UUID, body: LawyerRequestIn, user: User = Depends(current_user),
                   session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict[str, Any]:
    """«Обратиться»: register the case and the applicant's contacts for a lawyer. With application_id (the closed
    pilot «Юрист по кнопке», api/pilot.py) the request goes to that pilot lawyer at their current price, who accepts
    or declines it; without it the team passes the request to a lawyer of the right field, as before."""
    from ..identity import form_rules as R
    from .pilot import tell_lawyer

    case = load_case(case_id, session, user)
    phone, phone_err = R.normalize_kz_phone(body.phone)
    errors = {k: v for k, v in {"full_name": R.check_full_name(body.full_name), "phone": phone_err,
                                "email": R.check_email(body.email),
                                "consent": None if body.consent else "required"}.items() if v}
    if errors:
        raise HTTPException(422, {"code": "invalid_request", "message": "invalid_request", "fields": errors})
    app = None
    if body.application_id is not None:
        app = session.get(LawyerApplication, body.application_id)
        if not pilot.is_pilot_lawyer(app) or (case.jurisdiction and app.country != case.jurisdiction):
            raise HTTPException(404, {"code": "lawyer_not_found", "message": "lawyer_not_found"})
        if pilot.open_request(session, case) is not None:
            raise HTTPException(409, {"code": "request_open", "message": "request_open"})
    req = LawyerRequest(case_id=case.id, user_id=user.id,
                        lawyer_ref=body.lawyer_ref or (f"lawyer-{app.id}" if app is not None else None),
                        full_name=R.clean(body.full_name), phone=phone, email=(body.email or "").strip() or None,
                        application_id=app.id if app is not None else None,
                        price=app.price if app is not None else None)
    session.add(req)
    session.flush()
    container.engine.audit(session, case, f"user:{user.id}", "lawyer_requested", request=req.id, lawyer=req.lawyer_ref,
                           price=str(req.price) if req.price is not None else None)
    if app is None:
        notify_team(container, f"Заявка клиента юристу №{req.id}",
                    f"{req.full_name}, тел. {req.phone}{', ' + req.email if req.email else ''}\n"
                    f"Дело: {case.id}\nЮрист в каталоге: {body.lawyer_ref or '—'}\n\n"
                    f"Передайте дело юристу нужной специализации и сообщите клиенту.", desk="clients",
                    test=user.is_test)
        return {"id": req.id, "case_id": str(case.id), "status": req.status}
    currency = container.engine.pack_of(case).currency
    tell_lawyer(session, container, app, "Konsilier AI: новый запрос клиента",
                f"{app.full_name}, клиент отправил вам запрос по делу (ваша цена {pilot.money(req.price)} {currency}). "
                f"Откройте кабинет юриста, чтобы принять или отклонить его: https://konsilier.com/lawyer",
                test=user.is_test)
    notify_team(container, f"«Юрист по кнопке»: запрос №{req.id} юристу {pilot.lawyer_name(app)}",
                f"Клиент: {req.full_name}, тел. {req.phone}\nДело: {case.id}\nЦена юриста: {req.price} {currency}\n\n"
                f"Юрист получил уведомление и принимает или отклоняет запрос в своём кабинете.", desk="clients",
                test=user.is_test)
    return {"id": req.id, "case_id": str(case.id), "status": req.status,
            "request": pilot.request_view(session, container.engine, req)}


@admin_router.get("/lawyer-requests")
def list_lawyer_requests(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(LawyerRequest).order_by(LawyerRequest.created_at.desc()).limit(200)).all()
    return [{"id": r.id, "case_id": str(r.case_id), "lawyer_ref": r.lawyer_ref, "full_name": r.full_name,
             "phone": r.phone, "email": r.email, "status": r.status, "created_at": r.created_at.isoformat()}
            for r in rows]
