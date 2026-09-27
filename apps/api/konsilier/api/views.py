"""JSON views of domain objects for web/bot/admin clients."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import ai
from ..core.engine import CaseEngine, EngineError
from ..core.fields import display
from ..core.models import AuditLog, Case, Deadline
from ..core.roadmap import build_roadmap


def case_view(engine: CaseEngine, session: Session, case: Case, *, admin: bool = False) -> dict[str, Any]:
    pack = engine.pack_of(case)
    lang = pack.lang(case.language)
    compliance = pack.manifest.compliance
    view: dict[str, Any] = {
        "id": str(case.id),
        "status": case.status,
        "status_label": pack.t(lang, f"statuses.{case.status}", default=case.status),
        "needs_review": case.needs_review,
        "jurisdiction": case.jurisdiction,
        "language": lang,
        "amount_at_stake": str(case.amount_at_stake) if case.amount_at_stake is not None else None,
        "currency": case.currency,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "ai_label": pack.localized(compliance.ai_label, lang),
        "service_disclaimer": pack.localized(compliance.service_disclaimer, lang),
        "scenario": None,
        "facts": [],
        "question": None,
        "evidence": [],
        "actions": [],
        "proposal": None,
        "roadmap": None,
        "outcome": None,
    }
    if case.scenario_id:
        sc = engine.scenario_of(case)
        view["scenario"] = {
            "id": sc.id, "version": sc.version, "title": pack.localized(sc.title, lang),
            "ontology": sc.ontology, "draft": sc.is_draft,
            "draft_disclaimer": pack.localized(compliance.draft_disclaimer, lang) if sc.is_draft else None,
            "price": {"amount": sc.pricing.amount, "currency": sc.pricing.currency or pack.currency,
                      "model": sc.pricing.model},
        }
        for f in sc.intake:
            if f.type == "evidence" or f.name not in case.facts:
                continue
            view["facts"].append({"field": f.name, "label": ai.field_label(sc, pack, lang, f.name),
                                  "value": display(f, case.facts[f.name])})
        if case.pending_field:
            view["question"] = asdict(engine.question_for(sc, pack, lang, case.pending_field))
        deadlines = {d.action_id: d for d in session.scalars(select(Deadline).where(Deadline.case_id == case.id))}
        for a in case.actions:
            spec = sc.action(a.action_id)
            dl = deadlines.get(a.id)
            view["actions"].append({
                "id": str(a.id), "action_id": a.action_id, "sequence": a.sequence, "kind": a.kind,
                "title": pack.localized(spec.title, lang), "status": a.status,
                "approval_status": a.approval_status, "approval_note": a.approval_note if admin else None,
                "channel": a.channel, "email_allowed": spec.channel != "user_submits",
                "addressee": a.addressee, "instructions": a.instructions,
                "has_docx": bool(a.docx_key), "has_pdf": bool(a.pdf_key),
                "downloadable": a.status in ("ready", "submitted", "responded") or admin,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "submitted_via": a.submitted_via,
                "response_class": a.response_class,
                "response_label": pack.t(lang, f"responses.{a.response_class}", default=a.response_class)
                if a.response_class else None,
                "response_summary": a.response_summary,
                "deadline": {"due_date": dl.due_date.isoformat(), "status": dl.status,
                             "norm_ref": dl.norm_ref} if dl else None,
                "norm_refs": list(spec.norm_refs),
            })
        view["roadmap"] = build_roadmap(case, sc, pack, deadlines).to_dict()
        try:
            view["proposal"] = asdict(engine.proposal(case))
        except EngineError:
            view["proposal"] = None
    for e in case.evidence:
        view["evidence"].append({"id": str(e.id), "kind": e.kind, "filename": e.filename,
                                 "confirmed": e.confirmed, "extracted_facts": e.extracted_facts,
                                 "has_text": bool(e.text)})
    if case.outcome:
        o = case.outcome
        view["outcome"] = {"result": o.result, "amount_recovered": str(o.amount_recovered)
                           if o.amount_recovered is not None else None, "currency": o.currency,
                           "days_to_resolution": o.days_to_resolution, "resolved_at_step": o.resolved_at_step}
    if admin:
        view["raw_facts"] = case.facts
        view["qualification_confidence"] = case.qualification_confidence
        view["initial_text"] = case.initial_text
        view["narrative"] = case.narrative
        view["audit"] = [
            {"at": log.created_at.isoformat(), "actor": log.actor, "event": log.event,
             "from": log.from_status, "to": log.to_status, "data": log.data}
            for log in session.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
        ]
    return view
