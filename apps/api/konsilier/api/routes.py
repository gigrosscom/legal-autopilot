from __future__ import annotations

import uuid
from dataclasses import asdict
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.engine import OUTCOME_RESULTS, EngineError
from ..core.models import Action, Case, Evidence, LawyerApplication, Notification, User, WaitlistEntry
from ..core.scenario import RESPONSE_CLASSES
from .deps import current_user, get_container, get_session, load_case, require_bot
from .views import case_view

router = APIRouter(prefix="/v1")

MAX_UPLOAD = 15 * 1024 * 1024
ALLOWED_UPLOADS = ("image/jpeg", "image/png", "image/webp", "application/pdf", "text/plain")


def engine_error(e: EngineError) -> HTTPException:
    return HTTPException(409, {"code": e.code, "message": str(e)})


# ------------------------------------------------------------------ users
class NewUser(BaseModel):
    language: str = "ru"
    country: str | None = None
    email: str | None = None


@router.post("/users")
def create_user(body: NewUser, session: Session = Depends(get_session)) -> dict[str, Any]:
    user = User(channel="web", language=body.language, country=(body.country or "").upper() or None,
                email=body.email)
    session.add(user)
    session.flush()
    return {"id": str(user.id), "token": user.api_token}


class TelegramUser(BaseModel):
    telegram_id: str
    language: str = "ru"
    country: str | None = None
    display_name: str | None = None


@router.post("/users/telegram", dependencies=[Depends(require_bot)])
def upsert_telegram_user(body: TelegramUser, session: Session = Depends(get_session)) -> dict[str, Any]:
    user = session.scalar(select(User).where(User.channel == "telegram", User.external_id == body.telegram_id))
    if user is None:
        user = User(channel="telegram", external_id=body.telegram_id, language=body.language,
                    country=(body.country or "").upper() or None, display_name=body.display_name)
        session.add(user)
        session.flush()
    return {"id": str(user.id), "token": user.api_token}


# ------------------------------------------------------------------ packs / waitlist
@router.get("/packs")
def list_packs(lang: str = "ru", container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    out = []
    for pack in container.packs.packs.values():
        if pack.manifest.status != "live":
            continue
        lg = pack.lang(lang)
        out.append({
            "country": pack.country, "name": pack.localized(pack.manifest.name, lg),
            "languages": list(pack.manifest.languages), "currency": pack.currency,
            "scenarios": [{
                "id": s.id, "title": pack.localized(s.title, lg), "summary": pack.localized(s.summary, lg),
                "price": {"amount": s.pricing.amount, "currency": s.pricing.currency or pack.currency},
                "draft": s.is_draft,
            } for s in pack.scenarios.values() if s.published],
        })
    return out


@router.get("/lawyers")
def list_lawyers(country: str, lang: str = "ru",
                 container: Container = Depends(get_container)) -> dict[str, Any]:
    """Lawyer directory ranked by proven results. v0.1 serves the pack's demo profiles only."""
    from ..core.rating import CategoryStats, LawyerStats, score

    try:
        pack = container.packs.pack(country)
    except KeyError as e:
        raise HTTPException(404, "unknown country") from e
    demo = pack.demo_lawyers
    lg = pack.lang(lang)
    baseline = demo.get("baseline", {})
    out = []
    for raw in demo.get("lawyers", []):
        cats = [CategoryStats(**c) for c in raw.get("categories", [])]
        s = score(LawyerStats(cats, raw.get("milestones_total", 0), raw.get("milestones_on_time", 0),
                              raw.get("reviews_count", 0), raw.get("reviews_avg", 0.0)), baseline)
        # Text fields may be {lang: text} maps in the pack data.
        profile = {k: pack.localized(v, lg) if isinstance(v, dict) and k in ("title", "organization", "city", "name") else v
                   for k, v in raw.items() if k != "categories"}
        profile["specializations"] = [
            {"key": k, "label": pack.t(lg, f"categories.{k}", default=k)} for k in raw.get("specializations", [])]
        profile["results"] = [{
            "category": c.category, "label": pack.t(lg, f"categories.{c.category}", default=c.category),
            "cases": c.cases, "won": c.won, "partial": c.partial,
            "success_rate": round((c.won + 0.5 * c.partial) / c.cases, 3) if c.cases else None,
            "baseline": baseline.get(c.category), "recovered": c.recovered, "claimed": c.claimed,
        } for c in cats]
        profile["score"] = s.to_dict()
        out.append(profile)
    out.sort(key=lambda p: p["score"]["total"], reverse=True)
    return {"demo": True, "disclaimer": pack.localized(demo.get("disclaimer", {}), lg) if demo else "",
            "currency": pack.currency, "lawyers": out}


class WaitlistIn(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    contact: str = Field(min_length=3, max_length=200)
    problem: str | None = Field(default=None, max_length=2000)
    language: str | None = None


@router.post("/waitlist", status_code=201)
def join_waitlist(body: WaitlistIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    session.add(WaitlistEntry(country=body.country.upper(), contact=body.contact, problem=body.problem,
                              language=body.language))
    return {"ok": True}


# ------------------------------------------------------------------ cases
class NewCase(BaseModel):
    text: str = Field(min_length=3, max_length=8000)
    language: str | None = None
    country: str | None = None


@router.post("/cases", status_code=201)
def create_case(body: NewCase, user: User = Depends(current_user), session: Session = Depends(get_session),
                container: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        case, reply = container.engine.start_case(session, user, body.text, language=body.language,
                                                  country=body.country)
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"reply": reply.to_dict(), "case": case_view(container.engine, session, case)}


@router.get("/cases")
def list_cases(user: User = Depends(current_user), session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    cases = session.scalars(select(Case).where(Case.owner_id == user.id).order_by(Case.created_at.desc())).all()
    return [case_view(container.engine, session, c) for c in cases]


@router.get("/cases/{case_id}")
def get_case(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
             container: Container = Depends(get_container)) -> dict[str, Any]:
    return case_view(container.engine, session, load_case(case_id, session, user))


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


@router.post("/cases/{case_id}/messages")
def post_message(case_id: uuid.UUID, body: MessageIn, user: User = Depends(current_user),
                 session: Session = Depends(get_session), container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    try:
        reply = container.engine.handle_message(session, case, body.text)
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"reply": reply.to_dict(), "case": case_view(container.engine, session, case)}


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    ctype = (file.content_type or "application/octet-stream").split(";")[0]
    if ctype not in ALLOWED_UPLOADS:
        raise HTTPException(415, f"unsupported file type {ctype}")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large")
    return data, ctype


@router.post("/cases/{case_id}/evidence", status_code=201)
async def upload_evidence(case_id: uuid.UUID, file: UploadFile = File(...), kind: str = Form("other"),
                          user: User = Depends(current_user), session: Session = Depends(get_session),
                          container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    data, ctype = await _read_upload(file)
    ev = container.engine.add_evidence(session, case, kind=kind, filename=file.filename or "file",
                                       content_type=ctype, data=data)
    session.flush()
    return {"evidence": {"id": str(ev.id), "kind": ev.kind, "filename": ev.filename,
                         "extracted_facts": ev.extracted_facts, "has_text": bool(ev.text)},
            "case": case_view(container.engine, session, case)}


class ConfirmIn(BaseModel):
    facts: dict[str, Any] | None = None  # None → accept extracted facts as-is


@router.post("/cases/{case_id}/evidence/{evidence_id}/confirm")
def confirm_evidence(case_id: uuid.UUID, evidence_id: uuid.UUID, body: ConfirmIn,
                     user: User = Depends(current_user), session: Session = Depends(get_session),
                     container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    ev = session.get(Evidence, evidence_id)
    if ev is None or ev.case_id != case.id:
        raise HTTPException(404, "evidence not found")
    try:
        reply = container.engine.confirm_evidence(session, case, ev, body.facts)
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"reply": reply.to_dict(), "case": case_view(container.engine, session, case)}


class AckIn(BaseModel):
    kind: Literal["false_report", "special_category"]


@router.post("/cases/{case_id}/acknowledge")
def acknowledge(case_id: uuid.UUID, body: AckIn, user: User = Depends(current_user),
                session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """The user confirms a required notice (false report liability / special-category data consent)."""
    case = load_case(case_id, session, user)
    try:
        reply = container.engine.acknowledge(session, case, body.kind, actor=f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"reply": reply.to_dict(), "case": case_view(container.engine, session, case)}


class TriageIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    country: str
    language: str = "ru"


@router.post("/triage")
def triage(body: TriageIn, container: Container = Depends(get_container)) -> dict[str, Any]:
    """Pre-intake emergency check (keywords from the pack, no LLM, nothing stored)."""
    from ..core import safety

    try:
        pack = container.packs.pack(body.country)
    except KeyError:
        return {"emergency": False, "numbers": []}
    lang = pack.lang(body.language)
    hit = safety.detect_emergency(pack.coverage, body.text)
    return {"emergency": hit, "message": pack.t(lang, "safety.emergency") if hit else "",
            "numbers": safety.emergency_numbers(pack.coverage, lang, pack.manifest.default_language) if hit else []}


@router.get("/emergency")
def emergency(country: str, lang: str = "ru", container: Container = Depends(get_container)) -> dict[str, Any]:
    """Emergency numbers of a country (always available, e.g. for the site footer)."""
    from ..core import safety

    try:
        pack = container.packs.pack(country)
    except KeyError as e:
        raise HTTPException(404, "unknown country") from e
    lg = pack.lang(lang)
    return {"numbers": safety.emergency_numbers(pack.coverage, lg, pack.manifest.default_language),
            "message": pack.t(lg, "safety.emergency")}


class ForumIn(BaseModel):
    forum_id: str


@router.post("/cases/{case_id}/forum")
def choose_forum(case_id: uuid.UUID, body: ForumIn, user: User = Depends(current_user),
                 session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """Universal path: the user picks where to file from the pack's registry candidates."""
    case = load_case(case_id, session, user)
    try:
        reply = container.engine.choose_forum(session, case, body.forum_id, actor=f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"reply": reply.to_dict(), "case": case_view(container.engine, session, case)}


@router.get("/coverage")
def coverage(lang: str = "ru", container: Container = Depends(get_container)) -> dict[str, Any]:
    """Countries × branches with honest statuses: verified scenario / universal path with a lawyer / soon."""
    from ..core.coverage import global_taxonomy

    tax = global_taxonomy()
    branches = [{"id": b.id, "title": b.title.get(lang) or b.title.get("en") or b.id,
                 "situation": b.situation.get(lang) or b.situation.get("en") or ""} for b in tax.branches]
    countries = []
    for pack in container.packs.packs.values():
        if pack.manifest.status == "test":
            continue
        lg = pack.lang(lang)
        cov = pack.coverage
        cells: dict[str, str] = {}
        for b in tax.branches:
            if pack.manifest.status == "planned":
                cells[b.id] = "soon"
            elif any(_scenario_branch(cov, sc) == b.id and sc.published and not sc.is_draft
                     for sc in pack.scenarios.values()):
                cells[b.id] = "verified"
            elif any(_scenario_branch(cov, sc) == b.id and sc.published for sc in pack.scenarios.values()):
                cells[b.id] = "scenario_draft"
            elif cov is not None and cov.has_registry and b.id not in cov.routing.lawyer_only and any(
                    f.accepts_case(d, r) for d in cov.disputes.values() if d.branch == b.id
                    for r in d.applicant_roles for f in cov.forums.values()):
                cells[b.id] = "universal"
            elif cov is not None and cov.has_registry:
                cells[b.id] = "lawyer"
            else:
                cells[b.id] = "soon"
        countries.append({"country": pack.country, "name": pack.manifest.name.get(lang) or pack.localized(pack.manifest.name, lg),
                          "status": pack.manifest.status, "languages": list(pack.manifest.languages),
                          "cells": cells})
    return {"branches": branches, "countries": countries}


def _scenario_branch(cov: Any, sc: Any) -> str | None:
    """Branch of a scenario via its ``taxonomy:`` link in YAML."""
    if sc.taxonomy and cov is not None and sc.taxonomy in cov.disputes:
        return cov.dispute(sc.taxonomy).branch
    return None


@router.get("/forums")
def list_forums(country: str, lang: str = "ru", branch: str | None = None,
                container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    """Public view of a pack's forum registry, with verification status."""
    try:
        pack = container.packs.pack(country)
    except KeyError as e:
        raise HTTPException(404, "unknown country") from e
    cov = pack.coverage
    if cov is None:
        return []
    lg = pack.lang(lang)
    out = []
    for f in cov.forums.values():
        if branch and not any(branch in r.branches or any(d.startswith(branch + ".") for d in r.dispute_types)
                              for r in f.accepts):
            continue
        out.append({"id": f.id, "type": f.type, "name": pack.localized(f.name, lg), "legal_effect": f.legal_effect,
                    "verified": f.verified, "appeals_to": list(f.appeals_to),
                    "channels": [{"kind": c.kind, "url": c.url} for c in f.submission],
                    "fee": None if not f.fee or f.fee.amount is None else {"amount": f.fee.amount,
                                                                          "currency": f.fee.currency}})
    return out


@router.post("/cases/{case_id}/actions/next")
def prepare_next(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                 container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    try:
        action = container.engine.prepare_next_action(session, case, f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"action_id": str(action.id), "case": case_view(container.engine, session, case)}


def _load_action(case: Case, action_id: uuid.UUID, session: Session) -> Action:
    action = session.get(Action, action_id)
    if action is None or action.case_id != case.id:
        raise HTTPException(404, "action not found")
    return action


def document_response(container: Container, action: Action, fmt: str) -> Response:
    key = action.pdf_key if fmt == "pdf" else action.docx_key
    if not key:
        raise HTTPException(404, f"{fmt} not available")
    media = "application/pdf" if fmt == "pdf" else \
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(container.storage.get(key), media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{action.sequence:02d}-{action.action_id}.{fmt}"'})


@router.get("/cases/{case_id}/actions/{action_id}/document")
def download_document(case_id: uuid.UUID, action_id: uuid.UUID, format: Literal["docx", "pdf"] = "pdf",
                      user: User = Depends(current_user), session: Session = Depends(get_session),
                      container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    if action.status not in ("ready", "submitted", "responded"):
        raise HTTPException(409, {"code": "awaiting_approval", "message": "document is awaiting lawyer approval"})
    return document_response(container, action, format)


class SubmittedIn(BaseModel):
    via: Literal["user_submits", "email"] = "user_submits"


@router.post("/cases/{case_id}/actions/{action_id}/submitted")
def mark_submitted(case_id: uuid.UUID, action_id: uuid.UUID, body: SubmittedIn,
                   user: User = Depends(current_user), session: Session = Depends(get_session),
                   container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    try:
        container.engine.mark_submitted(session, case, action, f"user:{user.id}", via=body.via)
    except EngineError as e:
        raise engine_error(e) from e
    except (RuntimeError, ValueError) as e:
        raise HTTPException(502, {"code": "submission_failed", "message": str(e)}) from e
    session.flush()
    return {"case": case_view(container.engine, session, case)}


class ResponseIn(BaseModel):
    text: str | None = Field(default=None, max_length=20000)
    response_class: Literal[RESPONSE_CLASSES] | None = None  # type: ignore[valid-type]
    no_response: bool = False


@router.post("/cases/{case_id}/actions/{action_id}/response")
def record_response(case_id: uuid.UUID, action_id: uuid.UUID, body: ResponseIn,
                    user: User = Depends(current_user), session: Session = Depends(get_session),
                    container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    rc = "none" if body.no_response else body.response_class
    try:
        proposal = container.engine.record_response(session, case, action, text=body.text, response_class=rc,
                                                    actor=f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"proposal": asdict(proposal), "case": case_view(container.engine, session, case)}


@router.post("/cases/{case_id}/actions/{action_id}/response/file")
async def record_response_file(case_id: uuid.UUID, action_id: uuid.UUID, file: UploadFile = File(...),
                               user: User = Depends(current_user), session: Session = Depends(get_session),
                               container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    data, ctype = await _read_upload(file)
    ev = container.engine.add_evidence(session, case, kind="response", filename=file.filename or "response",
                                       content_type=ctype, data=data)
    try:
        # images carry no text → user must pick the class explicitly (clarify)
        proposal = container.engine.record_response(
            session, case, action, text=ev.text or None, response_class=None if ev.text else "unclear",
            actor=f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"proposal": asdict(proposal), "case": case_view(container.engine, session, case)}


class CloseIn(BaseModel):
    result: Literal[OUTCOME_RESULTS]  # type: ignore[valid-type]
    amount_recovered: Decimal | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/cases/{case_id}/close")
def close_case(case_id: uuid.UUID, body: CloseIn, user: User = Depends(current_user),
               session: Session = Depends(get_session), container: Container = Depends(get_container)):
    case = load_case(case_id, session, user)
    try:
        container.engine.close(session, case, result=body.result, amount_recovered=body.amount_recovered,
                               comment=body.comment, actor=f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return {"case": case_view(container.engine, session, case)}


class LawyerApplicationIn(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    full_name: str = Field(min_length=3, max_length=200)
    kind: Literal["advocate", "legal_consultant", "human_rights", "other"]
    organization: str | None = Field(default=None, max_length=300)
    license_number: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    specializations: list[str] = Field(default_factory=list, max_length=10)
    contact: str = Field(min_length=3, max_length=200)
    message: str | None = Field(default=None, max_length=2000)
    referred_by: str | None = Field(default=None, max_length=16)
    wants_expert: bool = False


@router.post("/lawyer-applications", status_code=201)
def apply_as_lawyer(body: LawyerApplicationIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    import secrets

    code = secrets.token_urlsafe(5).replace("-", "x").replace("_", "y")[:7].upper()
    ref = (body.referred_by or "").strip().upper() or None
    if ref and not session.scalar(select(LawyerApplication.id).where(LawyerApplication.referral_code == ref)):
        ref = None  # unknown code is ignored, not an error
    app_row = LawyerApplication(**body.model_dump(exclude={"referred_by", "country"}), country=body.country.upper(),
                                referral_code=code, referred_by=ref)
    session.add(app_row)
    session.flush()
    invited = session.scalar(select(func.count()).select_from(LawyerApplication)
                             .where(LawyerApplication.referred_by == code))
    return {"id": app_row.id, "referral_code": code, "invited": invited or 0}


class ClientErrorIn(BaseModel):
    message: str = Field(max_length=1000)
    stack: str | None = Field(default=None, max_length=4000)
    digest: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=300)
    user_agent: str | None = Field(default=None, max_length=300)
    translated: bool | None = None


@router.post("/client-errors", status_code=204)
def client_error(body: ClientErrorIn) -> None:
    """Browser crash reports → server logs (no personal data: message, stack, path only)."""
    import logging

    logging.getLogger("konsilier.client").warning(
        "client error at %s: %s | translated=%s | ua=%s | stack=%s",
        body.url, body.message, body.translated, body.user_agent, (body.stack or "").replace("\n", " ⏎ ")[:1500])


@router.get("/notifications")
def notifications(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.scalars(select(Notification).where(Notification.user_id == user.id)
                           .order_by(Notification.id.desc()).limit(50)).all()
    return [{"id": n.id, "case_id": str(n.case_id) if n.case_id else None, "kind": n.kind, "text": n.text,
             "created_at": n.created_at.isoformat()} for n in rows]
