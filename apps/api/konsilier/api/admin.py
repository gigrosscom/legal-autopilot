from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core import qualifier
from ..core.documents import docx_text
from ..core.engine import OUTCOME_RESULTS, EngineError
from ..core.coverage.schema import Forum
from ..core.models import Action, AuditLog, Case, DemandSignal, ForumDraft, LawyerApplication, WaitlistEntry
from ..core.state_machine import BOARD_COLUMNS, board_column
from .deps import get_container, get_session, require_admin
from .routes import document_response, engine_error
from .views import case_view

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])


@router.get("/cases")
def list_cases(needs_review: bool | None = None, status: str | None = None, pending_approval: bool = False,
               scenario_id: str | None = None, coverage_level: str | None = None, on_hold: bool | None = None,
               limit: int = 100, session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    q = select(Case).order_by(Case.created_at.desc()).limit(min(limit, 500))
    if coverage_level:
        q = q.where(Case.coverage_level == coverage_level)
    if on_hold is not None:
        q = q.where(Case.hold_reason.is_not(None) if on_hold else Case.hold_reason.is_(None))
    if needs_review is not None:
        q = q.where(Case.needs_review == needs_review)
    if status:
        q = q.where(Case.status == status)
    if scenario_id:
        q = q.where(Case.scenario_id == scenario_id)
    if pending_approval:
        q = q.where(Case.id.in_(select(Action.case_id).where(Action.approval_status == "pending")))
    return [_card(container, c) for c in session.scalars(q)]


def _card(container: Container, c: Case) -> dict[str, Any]:
    pack = container.engine.pack_of(c)
    lang = pack.lang(c.language)
    pending = [str(a.id) for a in c.actions if a.approval_status == "pending"]
    title = None
    draft = False
    if c.scenario_id:
        try:
            sc = container.packs.scenario(c.scenario_id)
            title, draft = pack.localized(sc.title, lang), sc.is_draft
        except KeyError:
            title = c.scenario_id
    elif c.taxonomy and pack.coverage and c.taxonomy.get("dispute_id") in pack.coverage.disputes:
        title = pack.localized(pack.coverage.dispute(c.taxonomy["dispute_id"]).title, lang)
    return {
        "id": str(c.id), "status": c.status, "needs_review": c.needs_review, "scenario_id": c.scenario_id,
        "jurisdiction": c.jurisdiction, "channel": c.channel, "amount_at_stake":
            str(c.amount_at_stake) if c.amount_at_stake is not None else None,
        "currency": c.currency, "created_at": c.created_at.isoformat(),
        "confidence": c.qualification_confidence, "pending_approval_action_ids": pending,
        "status_label": pack.t(lang, f"statuses.{c.status}", default=c.status),
        "stage": board_column(c.status), "coverage_level": c.coverage_level,
        "display_level": qualifier.display_level(c.coverage_level, draft, bool(c.scenario_id)), "hold_reason": c.hold_reason,
        "title": title, "route_reasons": c.route_reasons or [],
        "tasks": [{"id": str(a.id), "action_id": a.action_id, "status": a.status,
                   "approval_status": a.approval_status} for a in c.actions],
    }


@router.get("/board")
def board(coverage_level: str | None = None, limit: int = 500, session: Session = Depends(get_session),
          container: Container = Depends(get_container)) -> dict[str, Any]:
    """Kanban: every case in exactly one lifecycle column; resolved cases stay visible."""
    q = select(Case).order_by(Case.updated_at.desc()).limit(min(limit, 2000))
    if coverage_level:
        q = q.where(Case.coverage_level == coverage_level)
    columns: dict[str, list[dict[str, Any]]] = {col: [] for col, _ in BOARD_COLUMNS}
    for c in session.scalars(q):
        card = _card(container, c)
        columns[card["stage"]].append(card)
    return {"columns": [{"id": col, "cards": columns[col]} for col, _ in BOARD_COLUMNS]}


@router.post("/cases/{case_id}/release")
def release_hold(case_id: uuid.UUID, session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> dict[str, Any]:
    """An admin reviewed a held case (suspected abuse / false report risk) and lets it continue."""
    case = _case(case_id, session)
    if case.hold_reason is None:
        raise HTTPException(409, "case is not on hold")
    container.engine.audit(session, case, "admin", "hold_released", reason=case.hold_reason)
    case.hold_reason = None
    session.flush()
    return case_view(container.engine, session, case, admin=True)


@router.get("/demand")
def demand(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Universal-path demand: which dispute types to package as verified scenarios next."""
    rows = session.execute(select(DemandSignal.country, DemandSignal.branch, DemandSignal.dispute_type,
                                  DemandSignal.level, func.count()).group_by(
        DemandSignal.country, DemandSignal.branch, DemandSignal.dispute_type, DemandSignal.level)
        .order_by(func.count().desc()))
    return [{"country": c, "branch": b, "dispute_type": d, "level": lv, "count": n} for c, b, d, lv, n in rows]


@router.get("/forums")
def forums(country: str, session: Session = Depends(get_session),
           container: Container = Depends(get_container)) -> dict[str, Any]:
    """Registry as in the pack (source of truth in git) plus pending drafts from this admin."""
    try:
        pack = container.packs.pack(country)
    except KeyError as e:
        raise HTTPException(404, "unknown country") from e
    registry = [f.model_dump(mode="json") for f in (pack.coverage.forums.values() if pack.coverage else [])]
    drafts = [{"id": d.id, "forum_id": d.forum_id, "data": d.data, "note": d.note, "author": d.author,
               "status": d.status, "created_at": d.created_at.isoformat()}
              for d in session.scalars(select(ForumDraft).where(ForumDraft.country == pack.country)
                                       .order_by(ForumDraft.id.desc()))]
    return {"registry": registry, "drafts": drafts}


class ForumDraftIn(BaseModel):
    country: str
    data: dict[str, Any]
    note: str | None = None
    author: str | None = None


@router.post("/forum-drafts", status_code=201)
def create_forum_draft(body: ForumDraftIn, session: Session = Depends(get_session),
                       container: Container = Depends(get_container)) -> dict[str, Any]:
    """Validated proposal; becomes part of the pack only via `cli forums-export` → reviewed PR."""
    try:
        pack = container.packs.pack(body.country)
    except KeyError as e:
        raise HTTPException(404, "unknown country") from e
    try:
        forum = Forum.model_validate(body.data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not forum.id.startswith(pack.country.lower() + "."):
        raise HTTPException(422, f"forum id must start with {pack.country.lower()}.")
    draft = ForumDraft(country=pack.country, forum_id=forum.id, data=forum.model_dump(mode="json"),
                       note=body.note, author=body.author)
    session.add(draft)
    session.flush()
    return {"id": draft.id, "forum_id": draft.forum_id, "status": draft.status}


@router.post("/forum-drafts/{draft_id}/discard")
def discard_forum_draft(draft_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    draft = session.get(ForumDraft, draft_id)
    if draft is None:
        raise HTTPException(404, "draft not found")
    draft.status = "discarded"
    return {"id": draft.id, "status": draft.status}


def _case(case_id: uuid.UUID, session: Session) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    return case


def _action(action_id: uuid.UUID, session: Session) -> Action:
    action = session.get(Action, action_id)
    if action is None:
        raise HTTPException(404, "action not found")
    return action


@router.get("/cases/{case_id}")
def get_case(case_id: uuid.UUID, session: Session = Depends(get_session),
             container: Container = Depends(get_container)) -> dict[str, Any]:
    return case_view(container.engine, session, _case(case_id, session), admin=True)


@router.get("/reviews")
def reviews(session: Session = Depends(get_session), container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    """Documents waiting for the owner's check (court documents and others the engine holds): oldest first."""
    rows = session.scalars(select(Action).where(Action.approval_status == "pending").order_by(Action.updated_at))
    out = []
    for a in rows:
        case = session.get(Case, a.case_id)
        title = a.action_id
        try:
            pack = container.engine.pack_of(case)
            title = pack.localized(container.engine.scenario_of(case).action(a.action_id).title, "ru")
        except Exception:  # noqa: BLE001 — a card without a nice title is still a card
            pass
        out.append({"action_id": str(a.id), "case_id": str(case.id), "title": title,
                    "scenario_id": case.scenario_id, "language": case.language,
                    "waiting_since": a.updated_at.isoformat() if a.updated_at else None,
                    "addressee": (a.addressee or {}).get("name"), "has_pdf": bool(a.pdf_key),
                    # why it waits: the legal self-check's reasons (core/legal_check.py), if it stopped it
                    "check_note": a.approval_note if (a.approval_note or "").startswith("Самопроверка") else None})
    return out


@router.get("/actions/{action_id}/document")
def download(action_id: uuid.UUID, format: Literal["docx", "pdf"] = "pdf", session: Session = Depends(get_session),
             container: Container = Depends(get_container)):
    return document_response(container, _action(action_id, session), format)


@router.get("/actions/{action_id}/preview")
def preview(action_id: uuid.UUID, session: Session = Depends(get_session),
            container: Container = Depends(get_container)) -> dict[str, Any]:
    action = _action(action_id, session)
    if not action.docx_key:
        raise HTTPException(404, "no document")
    return {"text": docx_text(container.storage.get(action.docx_key)), "has_pdf": bool(action.pdf_key)}


class ApprovalIn(BaseModel):
    approved: bool
    reviewer: str = Field(default="lawyer", max_length=100)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/actions/{action_id}/approval")
def approve(action_id: uuid.UUID, body: ApprovalIn, session: Session = Depends(get_session),
            container: Container = Depends(get_container)) -> dict[str, Any]:
    action = _action(action_id, session)
    try:
        container.engine.approve(session, action, body.reviewer, body.approved, body.note)
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return case_view(container.engine, session, session.get(Case, action.case_id), admin=True)


class ReviewIn(BaseModel):
    scenario_id: str | None = None  # re-qualify manually (intake only)
    needs_review: bool = False


@router.post("/cases/{case_id}/review")
def review(case_id: uuid.UUID, body: ReviewIn, session: Session = Depends(get_session),
           container: Container = Depends(get_container)) -> dict[str, Any]:
    case = _case(case_id, session)
    engine = container.engine
    if body.scenario_id and body.scenario_id != case.scenario_id:
        if case.status != "intake":
            raise HTTPException(409, "scenario can only be changed during intake")
        try:
            sc = container.packs.scenario(body.scenario_id)
        except KeyError as e:
            raise HTTPException(404, "unknown scenario") from e
        pack = container.packs.pack(sc.jurisdiction)
        case.scenario_id, case.scenario_version, case.jurisdiction = sc.id, sc.version, sc.jurisdiction
        case.ontology_code, case.currency = sc.ontology, pack.currency
        case.pending_field = (engine.missing_fields(case, sc) or [None])[0]
    case.needs_review = body.needs_review
    engine.audit(session, case, "admin", "reviewed", scenario_id=case.scenario_id, needs_review=case.needs_review)
    session.flush()
    return case_view(engine, session, case, admin=True)


class CloseIn(BaseModel):
    result: Literal[OUTCOME_RESULTS]  # type: ignore[valid-type]
    amount_recovered: Decimal | None = Field(default=None, ge=0)
    comment: str | None = None


@router.post("/cases/{case_id}/close")
def close(case_id: uuid.UUID, body: CloseIn, session: Session = Depends(get_session),
          container: Container = Depends(get_container)) -> dict[str, Any]:
    case = _case(case_id, session)
    container.engine.close(session, case, result=body.result, amount_recovered=body.amount_recovered,
                           comment=body.comment, actor="admin")
    session.flush()
    return case_view(container.engine, session, case, admin=True)


@router.post("/scheduler/tick")
def tick(container: Container = Depends(get_container)) -> dict[str, Any]:
    return {"sent": container.scheduler.tick()}


@router.get("/client-errors")
def client_errors(limit: int = 100, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Browser crash reports sent by the web app (newest first)."""
    rows = session.scalars(select(AuditLog).where(AuditLog.event == "client_error")
                           .order_by(AuditLog.id.desc()).limit(min(limit, 500)))
    return [{"at": r.created_at.isoformat(), **(r.data or {})} for r in rows]


@router.get("/waitlist")
def waitlist(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(WaitlistEntry).order_by(WaitlistEntry.id.desc()).limit(500))
    return [{"country": w.country, "contact": w.contact, "problem": w.problem,
             "created_at": w.created_at.isoformat()} for w in rows]


@router.get("/lawyer-applications")
def lawyer_applications(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(LawyerApplication).order_by(LawyerApplication.id.desc()).limit(500)).all()
    counts: dict[str, int] = {}
    for r in rows:
        if r.referred_by:
            counts[r.referred_by] = counts.get(r.referred_by, 0) + 1
    return [{"id": r.id, "created_at": r.created_at.isoformat(), "full_name": r.full_name, "kind": r.kind,
             "organization": r.organization, "license_number": r.license_number, "city": r.city,
             "specializations": r.specializations, "contact": r.contact, "message": r.message,
             "referral_code": r.referral_code, "referred_by": r.referred_by, "wants_expert": r.wants_expert, "invited": counts.get(r.referral_code, 0),
             "status": r.status, "ecp_verified": bool(r.iin_hash), "ecp_name": r.ecp_name,
             "desk_note": r.desk_note} for r in rows]
