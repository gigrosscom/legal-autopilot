"""Legal questions about a case, answered by the legal agent from the official texts (konsilier/lawagent)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import Case, CaseQuestion, User
from ..core.pii import PiiVault
from .deps import current_user, get_container, get_session

router = APIRouter(prefix="/v1")

PER_CASE_PER_DAY = 10


def _case_for(session: Session, case_id: uuid.UUID, user: User) -> Case:
    case = session.get(Case, case_id)
    if case is None or (case.owner_id != user.id and case.lawyer_user_id != user.id):
        raise HTTPException(404, "case not found")
    return case


def _view(q: CaseQuestion) -> dict[str, Any]:
    return {"id": str(q.id), "question": q.question, "created_at": q.created_at.isoformat(), **(q.answer or {})}


def _context(container: Container, case: Case) -> dict[str, Any]:
    """What the agent may know about the case: no names, IDs or contacts (redacted like every LLM input)."""
    pack = container.engine.pack_of(case)
    lang = pack.lang(case.language)
    title = None
    if case.scenario_id:
        try:
            title = pack.localized(container.packs.scenario(case.scenario_id).title, lang)
        except KeyError:
            title = None
    if not title and pack.coverage and (case.taxonomy or {}).get("dispute_id") in pack.coverage.disputes:
        title = pack.localized(pack.coverage.dispute(case.taxonomy["dispute_id"]).title, lang)
    vault = PiiVault(case.pii_map)
    summary = vault.redact_obj({"topic": title, "story": case.initial_text or "",
                                "amount": str(case.amount_at_stake) if case.amount_at_stake is not None else None,
                                "status": case.status})
    forums = [{"name": f["name"], "type": f["type"], "legal_effect": f["legal_effect"]}
              for f in container.engine.forum_options(case)]
    return {"case": summary, "forums": forums, "pack": pack, "vault": vault}


class AskIn(BaseModel):
    question: str = Field(min_length=5, max_length=2000)


@router.get("/cases/{case_id}/questions")
def list_questions(case_id: uuid.UUID, user: User = Depends(current_user),
                   session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    case = _case_for(session, case_id, user)
    rows = session.scalars(select(CaseQuestion).where(CaseQuestion.case_id == case.id)
                           .order_by(CaseQuestion.created_at.desc()).limit(50)).all()
    return [_view(q) for q in rows]


@router.post("/cases/{case_id}/questions", status_code=201)
def ask(case_id: uuid.UUID, body: AskIn, user: User = Depends(current_user), session: Session = Depends(get_session),
        container: Container = Depends(get_container)) -> dict[str, Any]:
    case = _case_for(session, case_id, user)
    agent = container.law_agent_for(case)
    if agent is None:
        raise HTTPException(503, {"code": "agent_unavailable", "message": "agent_unavailable"})
    since = datetime.now(timezone.utc) - timedelta(days=1)
    n = session.scalar(select(func.count()).select_from(CaseQuestion).where(
        CaseQuestion.case_id == case.id, CaseQuestion.created_at > since)) or 0
    if n >= PER_CASE_PER_DAY:
        raise HTTPException(429, {"code": "too_many_questions", "message": "too_many_questions"})
    ctx = _context(container, case)
    vault: PiiVault = ctx.pop("vault")
    pack = ctx["pack"]
    try:
        res = agent.ask(vault.redact(body.question), context=ctx,
                        language=f"the language with ISO 639-1 code '{pack.lang(case.language)}'",
                        country=pack.localized(pack.manifest.name, "en") or pack.country)
    except Exception as e:  # API down, no credits, …: a clear error, not a 500
        raise HTTPException(503, {"code": "agent_failed", "message": str(e)[:200]}) from e
    answer = vault.restore_obj({"answer": res.answer, "steps": res.steps, "norms": res.norms,
                                "unverified": res.unverified, "needs_lawyer": res.needs_lawyer,
                                "confidence": res.confidence, "tool_calls": res.tool_calls})
    q = CaseQuestion(case_id=case.id, user_id=user.id, question=body.question, answer=answer)
    session.add(q)
    container.engine.audit(session, case, f"user:{user.id}", "legal_question", norms=len(res.norms),
                           unverified=res.unverified, tokens=res.usage)
    session.flush()
    return _view(q)
