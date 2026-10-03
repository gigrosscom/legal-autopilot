"""JSON views of domain objects for web/bot/admin clients."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import ai, qualifier
from ..core.engine import CaseEngine, EngineError
from ..core.appeal_portal import filing_record, portal_filings, portal_target
from ..core.fields import display
from ..core.filing import filing_view
from ..core.models import AuditLog, Case, Consent, Deadline
from ..core.roadmap import build_roadmap
from ..core.state_machine import CaseStatus, board_column


def _scenario_is_draft(engine: CaseEngine, case: Case) -> bool:
    if not case.scenario_id:
        return False
    try:
        return engine.packs.scenario(case.scenario_id).is_draft
    except KeyError:
        return False


def coverage_view(engine: CaseEngine, case: Case, pack: Any, lang: str) -> dict[str, Any]:
    """Coverage level and what it means for this case (ADR 0001): shown to the user on every step."""
    cov = pack.coverage
    out: dict[str, Any] = {"level": qualifier.display_level(case.coverage_level, _scenario_is_draft(engine, case), bool(case.scenario_id)), "dispute": None, "forum": None, "reasons": [],
                           "options": engine.forum_options(case), "other_forums": [], "upl_notice": None,
}
    tax = case.taxonomy or {}
    if cov is not None:
        if tax.get("dispute_id") in cov.disputes:
            d = cov.dispute(tax["dispute_id"])
            out["dispute"] = {"id": d.id, "title": pack.localized(d.title, lang), "branch": d.branch}
        if case.forum_id in cov.forums:
            dispute = cov.disputes.get(tax.get("dispute_id"))
            out["forum"] = engine.forum_option(pack, cov.forums[case.forum_id], lang, dispute)
            # «почему»: the dispute's own route (routes.yaml) when it names this forum, else the pack's line
            step = cov.route_step(tax.get("dispute_id"), case.forum_id)
            why = step.why if step is not None else cov.routing.forum_why.get(case.forum_id)
            out["forum"]["why"] = pack.localized(why, lang) if why else None
            out["other_forums"] = engine.other_forums(case)  # «Другой адресат»
        if cov.routing.upl_notice:
            out["upl_notice"] = pack.localized(cov.routing.upl_notice.text, lang)
    out["reasons"] = [{"code": r, "label": pack.t(lang, f"routing.reasons.{r}", default=r)}
                      for r in (case.route_reasons or [])]
    return out


def response_deadline(case: Case, deadlines: dict[Any, Deadline], pack: Any) -> dict[str, Any] | None:
    """While the case awaits an answer: the running (or just expired) response deadline of the latest document and
    the days left in the pack's local calendar (negative once it has passed)."""
    if case.status != CaseStatus.AWAITING_RESPONSE.value:
        return None
    for a in reversed(case.actions):
        dl = deadlines.get(a.id)
        if dl is not None and dl.status in ("active", "expired"):
            return {"due_date": dl.due_date.isoformat(), "status": dl.status,
                    "days_left": (dl.due_date - pack.local_now().date()).days}
    return None


def case_view(engine: CaseEngine, session: Session, case: Case, *, admin: bool = False) -> dict[str, Any]:
    pack = engine.pack_of(case)
    lang = pack.lang(case.language)
    compliance = pack.manifest.compliance
    ack = engine.ack_reply(session, case) if case.status == "intake" else None
    view: dict[str, Any] = {
        "id": str(case.id),
        "status": case.status,
        "status_label": pack.t(lang, f"statuses.{case.status}", default=case.status),
        "stage": board_column(case.status),
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
        "plan": None,
        "payment": None,
        # the owner allowed this case, anonymised, to teach Konsilier's own model (Zann)
        "training_consent": session.scalar(select(Consent.id).where(Consent.case_id == case.id,
                                                                    Consent.kind == "training")) is not None,
        "deadline": None,
        "outcome": None,
        "coverage": coverage_view(engine, case, pack, lang),
        # owner 02.10: who each step's document goes to and why — chosen by the system (routes.yaml)
        "recipients": engine.recipient_route(case),
        "safety": {"hold_reason": case.hold_reason,
                   "hold_message": pack.t(lang, "safety.hold") if case.hold_reason else None,
                   "pending_ack": ack.ack_required if ack else None},
    }
    if case.scenario_id:
        sc = engine.scenario_of(case)
        view["scenario"] = {
            "id": sc.id, "version": sc.version, "title": pack.localized(sc.title, lang),
            "ontology": sc.ontology, "draft": sc.is_draft,
            "kind": sc.kind, "beta": sc.beta, "disclaimer": pack.localized(sc.disclaimer, lang) if sc.disclaimer else None,
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
            q = asdict(engine.question_for(sc, pack, lang, case.pending_field))
            kinds = {k["kind"] for k in q["evidence_kinds"]}
            q["uploaded"] = sum(1 for e in case.evidence if e.kind in kinds) if kinds else 0
            view["question"] = q
        view["payment"] = engine.payment_view(session, case)
        deadlines = {d.action_id: d for d in session.scalars(select(Deadline).where(Deadline.case_id == case.id))}
        today = pack.local_now().date()
        from .delivery import filings_of, send_state

        container = getattr(engine.notifier, "outbound", None)  # the container (settings, the claims mailer)
        # one `filings` table (docs/integrations-plan.md, 7.3): letters and messenger sendings (several per document)
        # and the registered appeal on the appeal portal (one per document, with its number and date)
        filings = filings_of(session, case.id)
        registered = portal_filings(session, case.id)
        for a in case.actions:
            spec = sc.action(a.action_id)
            dl = deadlines.get(a.id)
            filing = None if spec.kind == "handoff" else filing_view(
                pack, sc, spec, lang=lang, addressee=a.addressee, facts=case.facts or {},
                forum=engine.action_forum(case, spec), today=today)
            view["actions"].append({
                "id": str(a.id), "action_id": a.action_id, "sequence": a.sequence, "kind": a.kind,
                "title": pack.localized(spec.title, lang), "status": a.status,
                "approval_status": a.approval_status, "approval_note": a.approval_note if admin else None,
                "channel": a.channel, "email_allowed": spec.channel != "user_submits",
                "addressee": a.addressee, "instructions": a.instructions,
                "has_docx": bool(a.docx_key), "has_pdf": bool(a.pdf_key),
                # QA 01.10: this document was paid for (a bill, «Дело под ключ», a bonus or a plan) — «Оплачено»
                "paid": a.unlocked_by not in (None, "free"),
                "signatures": [{"id": str(g.id), "role": g.role, "signer_name": g.signer_name, "display": g.display,
                                "method": g.method, "format": g.file_format, "signed_at": g.signed_at.isoformat()}
                               for g in a.signatures],
                "downloadable": (a.status in ("ready", "submitted", "responded")
                                 and engine.document_unlocked(case, a)) or admin,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "submitted_via": a.submitted_via,
                "response_class": a.response_class,
                "response_label": pack.t(lang, f"responses.{a.response_class}", default=a.response_class)
                if a.response_class else None,
                "response_summary": a.response_summary,
                "deadline": {"due_date": dl.due_date.isoformat(), "status": dl.status,
                             "norm_ref": dl.norm_ref} if dl else None,
                "norm_refs": [r for r in spec.norm_refs if "TODO" not in r],  # an unchecked norm is never shown
                "filing": filing,
                # «Отправить по e-mail» (api/delivery.py): may it be sent now, and the letters already sent
                "email_send": send_state(container, session, case, a)
                if container is not None and a.kind == "document" else None,
                "filings": filings.get(a.id, []),
                # manual filing on the appeal portal: what to pick there (None → not filed there) and the record
                "appeal_portal": portal_target(pack, lang, a),
                "filed": filing_record(registered[a.id]) if a.id in registered else None,
            })
        view["roadmap"] = build_roadmap(case, sc, pack, deadlines).to_dict()
        view["deadline"] = response_deadline(case, deadlines, pack)
        view["plan"] = engine.plan(session, case)
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
