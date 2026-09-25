from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.documents import docx_text
from ..core.engine import OUTCOME_RESULTS, EngineError
from ..core.models import Action, Case, WaitlistEntry
from .deps import get_container, get_session, require_admin
from .routes import document_response, engine_error
from .views import case_view

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])


@router.get("/cases")
def list_cases(needs_review: bool | None = None, status: str | None = None, pending_approval: bool = False,
               scenario_id: str | None = None, limit: int = 100, session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    q = select(Case).order_by(Case.created_at.desc()).limit(min(limit, 500))
    if needs_review is not None:
        q = q.where(Case.needs_review == needs_review)
    if status:
        q = q.where(Case.status == status)
    if scenario_id:
        q = q.where(Case.scenario_id == scenario_id)
    if pending_approval:
        q = q.where(Case.id.in_(select(Action.case_id).where(Action.approval_status == "pending")))
    out = []
    for c in session.scalars(q):
        pack = container.engine.pack_of(c)
        pending = [str(a.id) for a in c.actions if a.approval_status == "pending"]
        out.append({
            "id": str(c.id), "status": c.status, "needs_review": c.needs_review, "scenario_id": c.scenario_id,
            "jurisdiction": c.jurisdiction, "channel": c.channel, "amount_at_stake":
                str(c.amount_at_stake) if c.amount_at_stake is not None else None,
            "currency": c.currency, "created_at": c.created_at.isoformat(),
            "confidence": c.qualification_confidence, "pending_approval_action_ids": pending,
            "status_label": pack.t(pack.lang(c.language), f"statuses.{c.status}", default=c.status),
        })
    return out


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


@router.get("/waitlist")
def waitlist(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(WaitlistEntry).order_by(WaitlistEntry.id.desc()).limit(500))
    return [{"country": w.country, "contact": w.contact, "problem": w.problem,
             "created_at": w.created_at.isoformat()} for w in rows]
