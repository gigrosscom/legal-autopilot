"""Lawyers on the platform: ЭЦП-tied applications, case assignment, the lawyer's cabinet, customer–lawyer papers.

A lawyer applies while signed in with ЭЦП (so the application carries who they are per the certificate);
an administrator checks the licence against the public registry and verifies the application, then assigns
cases. Assignment generates the pack's agreements (consent, engagement), which the customer and then the
lawyer sign with ЭЦП (see api/signing.py).
"""

from __future__ import annotations

import io
import uuid
from datetime import date
from typing import Any, Literal

from docx import Document
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..team import notify_team
from ..core.models import Agreement, Case, Identity, LawyerApplication, LawyerRequest, User
from .deps import current_user, get_container, get_session, load_case, require_admin
from .signing import agreement_view, signature_view
from .views import case_view

router = APIRouter(prefix="/v1")
admin_router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])


def iin_identity(session: Session, user_id: uuid.UUID) -> Identity | None:
    return session.scalar(select(Identity).where(Identity.user_id == user_id, Identity.kind == "iin"))


def render_agreement(pack: Any, kind: str, lang: str, values: dict[str, str]) -> bytes:
    """DOCX from the pack's template. Unreviewed templates carry a visible note; nothing is invented here."""
    ags = pack.agreements
    tpl = ags.templates[kind]
    lang = lang if lang in tpl.body else pack.manifest.default_language
    doc = Document()
    if ags.reviewed_at is None and "unreviewed" in ags.footer:
        doc.add_paragraph(pack.localized(ags.footer["unreviewed"], lang)).runs[0].italic = True
    doc.add_heading(pack.localized(tpl.title, lang), level=1)
    for para in tpl.body[lang]:
        doc.add_paragraph(para.format(**values))
    doc.add_paragraph(values["date"])
    if "signed_with" in ags.footer:
        doc.add_paragraph(pack.localized(ags.footer["signed_with"], lang)).runs[0].italic = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_agreements(session: Session, container: Container, case: Case, app: LawyerApplication) -> list[Agreement]:
    import hashlib

    pack = container.engine.pack_of(case)
    if pack.agreements is None:
        return []
    lang = pack.lang(case.language)
    owner = session.get(User, case.owner_id)
    ident = iin_identity(session, owner.id)
    sc_title = ""
    if case.scenario_id:
        try:
            sc_title = pack.localized(container.packs.scenario(case.scenario_id).title, lang)
        except KeyError:
            sc_title = ""
    values = {
        "customer_name": owner.display_name or (case.facts or {}).get("applicant_name") or "—",
        "customer_id": ident.display if ident else "—",
        "lawyer_name": app.ecp_name or app.full_name,
        "lawyer_kind": pack.localized(pack.agreements.lawyer_kinds.get(app.kind, {"ru": app.kind}), lang),
        "case_ref": str(case.id)[:8].upper(),
        "case_title": sc_title or "—",
        "date": date.today().strftime("%d.%m.%Y"),
    }
    out = []
    for kind in pack.agreements.templates:
        data = render_agreement(pack, kind, lang, values)
        ag = Agreement(case_id=case.id, kind=kind, lawyer_application_id=app.id, docx_key="",
                       sha256=hashlib.sha256(data).hexdigest(),
                       template_reviewed=pack.agreements.reviewed_at is not None)
        session.add(ag)
        session.flush()
        ag.docx_key = container.storage.put(f"cases/{case.id}/agreements/{ag.id}.docx", data,
                                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        out.append(ag)
    return out


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
    return {"applications": [{"id": a.id, "status": a.status, "name": a.ecp_name or a.full_name, "kind": a.kind}
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
    if app.status != "verified" or app.user_id is None or not app.iin_hash:
        raise HTTPException(409, {"code": "lawyer_not_verified", "message": "lawyer_not_verified"})
    if case.lawyer_application_id == app.id:
        raise HTTPException(409, {"code": "already_assigned", "message": "already_assigned"})
    case.lawyer_user_id, case.lawyer_application_id = app.user_id, app.id
    ags = create_agreements(session, container, case, app)
    container.engine.audit(session, case, "admin", "lawyer_assigned", application_id=app.id,
                           agreements=[a.kind for a in ags])
    pack = container.engine.pack_of(case)
    return {"lawyer": {"name": app.ecp_name or app.full_name},
            "agreements": [agreement_view(pack, a, pack.lang(case.language)) for a in ags]}


__all__ = ["router", "admin_router", "signature_view"]


class LawyerRequestIn(BaseModel):
    lawyer_ref: str | None = Field(default=None, max_length=100)
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=6, max_length=40)
    email: str | None = Field(default=None, max_length=200)
    consent: bool


@router.post("/cases/{case_id}/lawyer-request", status_code=201)
def request_lawyer(case_id: uuid.UUID, body: LawyerRequestIn, user: User = Depends(current_user),
                   session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict[str, Any]:
    """«Обратиться»: register the case and the applicant's contacts for a lawyer. Direct booking opens later;
    until then the team passes the request to a verified lawyer of the right field."""
    case = load_case(case_id, session, user)
    if not body.consent:
        raise HTTPException(422, {"code": "consent_required", "message": "consent_required"})
    digits = "".join(ch for ch in body.phone if ch.isdigit())
    if len(digits) < 10:
        raise HTTPException(422, {"code": "phone", "message": "phone"})
    req = LawyerRequest(case_id=case.id, user_id=user.id, lawyer_ref=body.lawyer_ref, full_name=body.full_name.strip(),
                        phone=("+" if body.phone.strip().startswith("+") else "") + digits,
                        email=(body.email or "").strip() or None)
    session.add(req)
    session.flush()
    container.engine.audit(session, case, f"user:{user.id}", "lawyer_requested", request=req.id, lawyer=body.lawyer_ref)
    notify_team(container, f"Заявка клиента юристу №{req.id}",
                f"{req.full_name}, тел. {req.phone}{', ' + req.email if req.email else ''}\n"
                f"Дело: {case.id}\nЮрист в каталоге: {body.lawyer_ref or '—'}\n\n"
                f"Передайте дело проверенному юристу нужной специализации и сообщите клиенту.")
    return {"id": req.id, "case_id": str(case.id), "status": req.status}


@admin_router.get("/lawyer-requests")
def list_lawyer_requests(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(LawyerRequest).order_by(LawyerRequest.created_at.desc()).limit(200)).all()
    return [{"id": r.id, "case_id": str(r.case_id), "lawyer_ref": r.lawyer_ref, "full_name": r.full_name,
             "phone": r.phone, "email": r.email, "status": r.status, "created_at": r.created_at.isoformat()}
            for r in rows]
