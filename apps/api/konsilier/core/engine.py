"""CaseEngine — the deterministic driver of a case.

The engine owns every decision about *what happens next*: which question to ask,
which scenario action comes next (by ``when`` conditions from YAML), when a
deadline starts, when a lawyer must approve. The LLM is only consulted for
language tasks through ``core.ai``.
"""

from __future__ import annotations

import io
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ai, qualifier, safety
from .adapters.payment import PaymentAdapter
from .adapters.storage import Storage
from .adapters.submission import SubmissionAdapter
from .deadlines import DeadlineScheduler
from .documents import PdfConverter, render_docx
from .fields import FieldError, display, normalize
from .llm import Attachment, LLMProvider, RedactingLLM
from .generic import GenericRef, is_generic
from .models import (
    Action,
    AuditLog,
    Case,
    Claim,
    Consent,
    DemandSignal,
    Evidence,
    Organization,
    Outcome,
    Party,
    User,
    utcnow,
)
from .notify import Notifier
from .packs import JurisdictionPack, PackRegistry
from .pii import PiiVault
from .scenario import ActionSpec, Scenario
from .state_machine import CaseStatus, assert_transition

log = logging.getLogger(__name__)

S = CaseStatus
IDENTITY_KIND = "id_document"  # a copy of the applicant's ID: attached to documents, never read by the LLM
_IIN = re.compile(r"(?<!\d)\d{12}(?!\d)")
OUTCOME_RESULTS = ("won", "partial", "lost", "settled", "abandoned")


class EngineError(Exception):
    """A request that is valid HTTP but not allowed in the current case state."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


@dataclass
class Question:
    field: str
    text: str
    type: str
    optional: bool
    evidence_kinds: list[dict[str, str]] = field(default_factory=list)
    uploaded: int = 0  # files already attached to this evidence question


@dataclass
class Reply:
    message: str
    question: Question | None = None
    intake_complete: bool = False
    error: str | None = None
    # universal path: forums to choose from ({id, name, type, legal_effect, verified, …})
    options: list[dict[str, Any]] = field(default_factory=list)
    # acknowledgement the user must give before intake continues (false_report | special_category)
    ack_required: str | None = None
    # emergency screen data: {"numbers": [...]} when the story mentions immediate danger
    emergency: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Proposal:
    type: str  # prepare_action | handoff | close | clarify | wait | none
    action_id: str | None = None
    title: str | None = None
    response_class: str | None = None
    suggested_result: str | None = None
    message: str = ""


@dataclass
class EngineConfig:
    qualify_min_confidence: float = 0.6
    approval_required_first_n: int = 50
    self_service: bool = True
    self_service_documents: tuple[str, ...] = ("claim_letter", "complaint", "statement", "motion")
    extract_images_with_llm: bool = False


class CaseEngine:
    def __init__(self, *, packs: PackRegistry, llm: LLMProvider, storage: Storage, pdf: PdfConverter,
                 scheduler: DeadlineScheduler, notifier: Notifier, payments: PaymentAdapter,
                 submissions: dict[str, SubmissionAdapter], config: EngineConfig):
        self.packs = packs
        self.llm_provider = llm
        self.storage = storage
        self.pdf = pdf
        self.scheduler = scheduler
        self.notifier = notifier
        self.payments = payments
        self.submissions = submissions
        self.config = config

    # ================================================================ helpers
    def llm_for(self, case: Case) -> RedactingLLM:
        return RedactingLLM(self.llm_provider, PiiVault(case.pii_map))

    def _save_vault(self, case: Case, llm: RedactingLLM) -> None:
        case.pii_map = dict(llm.vault.mapping)

    def scenario_of(self, case: Case) -> Scenario:
        if not case.scenario_id:
            raise EngineError("no_scenario")
        sc = self.packs.scenario(case.scenario_id)
        if case.scenario_version and sc.version != case.scenario_version:
            log.warning("case %s uses %s@%s, loaded %s", case.id, sc.id, case.scenario_version, sc.version)
        return sc

    def pack_of(self, case: Case) -> JurisdictionPack:
        if case.jurisdiction:
            return self.packs.pack(case.jurisdiction)
        return self._fallback_pack(case.language)

    def _fallback_pack(self, lang: str) -> JurisdictionPack:
        live = [p for p in self.packs.packs.values() if p.manifest.status == "live"] or list(self.packs.packs.values())
        for p in live:
            if lang in p.manifest.languages:
                return p
        return live[0]

    def audit(self, session: Session, case: Case | None, actor: str, event: str,
              from_status: str | None = None, to_status: str | None = None, **data: Any) -> None:
        session.add(AuditLog(case_id=case.id if case else None, actor=actor, event=event,
                             from_status=from_status, to_status=to_status, data=_jsonable(data)))

    def transition(self, session: Session, case: Case, target: CaseStatus, actor: str, **data: Any) -> None:
        current = case.status
        assert_transition(current, target)
        case.status = target.value
        self.audit(session, case, actor, "status_changed", current, target.value, **data)

    # ================================================================ intake
    def start_case(self, session: Session, user: User, text: str, *, language: str | None = None,
                   channel: str | None = None, country: str | None = None) -> tuple[Case, Reply]:
        lang = language or user.language or "ru"
        country = (country or user.country or "").upper() or None
        if country and country not in self.packs.packs:
            raise EngineError("country_not_supported")
        if country and self.packs.pack(country).manifest.status == "planned":
            raise EngineError("country_planned")  # skeleton pack: waitlist only, no cases yet
        case = Case(owner_id=user.id, language=lang, channel=channel or user.channel,
                    jurisdiction=country, initial_text=text, facts={}, skipped_fields=[], pii_map={})
        session.add(case)
        session.flush()
        self.audit(session, case, f"user:{user.id}", "case_created", None, case.status, channel=case.channel)
        pack = self.pack_of(case)
        keyword_emergency = safety.detect_emergency(pack.coverage, text)
        reply = self._qualify_and_continue(session, case, text)
        if keyword_emergency or "emergency" in ((case.taxonomy or {}).get("flags") or []):
            reply.emergency = self.emergency_info(case)
            self.audit(session, case, "system", "emergency_detected", by="keywords" if keyword_emergency else "llm")
        return case, reply

    def emergency_info(self, case: Case) -> dict[str, Any]:
        pack = self.pack_of(case)
        lang = pack.lang(case.language)
        return {"numbers": safety.emergency_numbers(pack.coverage, lang, pack.manifest.default_language),
                "message": pack.t(lang, "safety.emergency")}

    # ================================================================ acknowledgements
    def ack_reply(self, session: Session, case: Case) -> Reply | None:
        pack = self.pack_of(case)
        kind = safety.pending_ack(session, pack.coverage, case)
        if kind is None:
            return None
        lang = pack.lang(case.language)
        if kind == safety.ACK_FALSE_REPORT and pack.coverage and pack.coverage.routing.false_report_norm:
            text = pack.localized(pack.coverage.routing.false_report_norm.text, lang)
        else:
            text = pack.t(lang, f"safety.ack.{kind}")
        return Reply(message=text, ack_required=kind)

    def acknowledge(self, session: Session, case: Case, kind: str, actor: str) -> Reply:
        pack = self.pack_of(case)
        if kind not in safety.required_acks(pack.coverage, case):
            raise EngineError("ack_not_required")
        if kind not in safety.given_acks(session, case):
            session.add(Consent(case_id=case.id, kind=kind))
            session.flush()
            self.audit(session, case, actor, "acknowledged", kind=kind)
        pending = self.ack_reply(session, case)
        if pending is not None:
            return pending
        if case.scenario_id and case.status == S.INTAKE.value:
            return self._next_step(session, case, self.scenario_of(case), pack)
        return Reply(message="")

    def _qualify_and_continue(self, session: Session, case: Case, text: str) -> Reply:
        llm = self.llm_for(case)
        candidates = self.packs.published(case.jurisdiction)
        sid, confidence, reason = ai.qualify(llm, candidates, self.packs.packs, text, case.language)
        case.qualification_confidence = confidence
        if sid is None:
            case.needs_review = True
            self.audit(session, case, "system", "qualification_failed", reason=reason)
            pack = self.pack_of(case)
            if pack.coverage is not None and pack.coverage.has_registry:
                return self._route_universal(session, case, pack, llm, text)
            self._save_vault(case, llm)
            return Reply(message=pack.t(pack.lang(case.language), "interview.no_scenario"))
        case.coverage_level = qualifier.LEVEL_VERIFIED
        sc = self.packs.scenario(sid)
        pack = self.packs.pack(sc.jurisdiction)
        case.scenario_id, case.scenario_version = sc.id, sc.version
        case.jurisdiction = sc.jurisdiction
        case.ontology_code = sc.ontology
        case.language = pack.lang(case.language)
        case.currency = pack.currency
        case.needs_review = confidence < self.config.qualify_min_confidence
        self.audit(session, case, "system", "qualified_scenario", scenario_id=sc.id,
                   confidence=confidence, needs_review=case.needs_review, reason=reason)
        # bulk extraction from the free story
        missing = self.missing_fields(case, sc)
        values = ai.extract_fields(llm, sc, pack, case.language, text, None, missing)
        self._apply_values(case, sc, pack, values, llm, strict=False)
        self._save_vault(case, llm)
        intro = pack.t(case.language, "interview.intro", scenario=pack.localized(sc.title, case.language),
                       first_action=pack.localized(sc.actions[0].title, case.language))
        reply = self._next_step(session, case, sc, pack)
        reply.message = f"{intro}\n\n{reply.message}".strip()
        return reply

    # ================================================================ universal path (ADR 0001)
    def _route_universal(self, session: Session, case: Case, pack: JurisdictionPack, llm: RedactingLLM,
                         text: str) -> Reply:
        cov = pack.coverage
        assert cov is not None
        lang = pack.lang(case.language)
        result = ai.classify_taxonomy(llm, qualifier.taxonomy_options(cov, lang),
                                      sorted({r for d in cov.disputes.values() for r in d.applicant_roles}),
                                      text, lang)
        self._save_vault(case, llm)
        route = qualifier.route_universal(cov, result, amount=case.amount_at_stake)
        case.jurisdiction = case.jurisdiction or pack.country
        case.taxonomy = route.to_taxonomy()
        case.route_reasons = route.reasons
        case.qualification_confidence = route.confidence
        branch = cov.dispute(route.dispute_id).branch if route.dispute_id else None
        session.add(DemandSignal(country=pack.country, branch=branch, dispute_type=route.dispute_id,
                                 level=route.level or "unclassified", reason=",".join(route.reasons) or None))
        self.audit(session, case, "system", "qualified_level", level=route.level, dispute=route.dispute_id,
                   role=route.role, confidence=route.confidence, reasons=route.reasons, flags=route.flags)
        if route.level is None:
            return Reply(message=pack.t(lang, "interview.no_scenario"))
        if route.level == qualifier.LEVEL_LAWYER:
            return self._handoff_level3(session, case, pack)
        if set(route.flags) & safety.ABUSE_FLAGS:
            case.hold_reason = "abuse_suspected"
            self.audit(session, case, "system", "hold", reason=case.hold_reason, flags=route.flags)
        case.coverage_level = qualifier.LEVEL_UNIVERSAL
        # low confidence already routes to a lawyer (level 3); what is left is a clear case
        case.needs_review = not self.config.self_service
        if len(route.forums) == 1:
            return self.choose_forum(session, case, route.forums[0].id, actor="system")
        return Reply(message=pack.t(lang, "routing.choose_forum",
                                    dispute=pack.localized(cov.dispute(route.dispute_id).title, lang)),
                     options=[self.forum_option(pack, f, lang) for f in route.forums])

    def forum_option(self, pack: JurisdictionPack, forum: Any, lang: str) -> dict[str, Any]:
        out = {"id": forum.id, "name": pack.localized(forum.name, lang), "type": forum.type,
               "legal_effect": forum.legal_effect, "verified": forum.verified,
               "channels": [ch.kind for ch in forum.submission],
               "deadline_known": forum.response_deadline is not None}
        return out

    def forum_options(self, case: Case) -> list[dict[str, Any]]:
        """Forums the user may still choose from (universal case waiting for a choice)."""
        if case.coverage_level != qualifier.LEVEL_UNIVERSAL or case.scenario_id or not case.taxonomy:
            return []
        pack = self.pack_of(case)
        cov = pack.coverage
        if cov is None or not case.taxonomy.get("dispute_id"):
            return []
        dispute = cov.dispute(case.taxonomy["dispute_id"])
        return [self.forum_option(pack, f, case.language)
                for f in cov.candidate_forums(dispute, case.taxonomy.get("role") or dispute.applicant_roles[0])]

    def choose_forum(self, session: Session, case: Case, forum_id: str, actor: str) -> Reply:
        if case.status != S.INTAKE.value or case.scenario_id:
            raise EngineError("forum_already_chosen")
        if forum_id not in {o["id"] for o in self.forum_options(case)}:
            raise EngineError("forum_not_allowed")
        pack = self.pack_of(case)
        ref = GenericRef(pack.country, case.taxonomy["dispute_id"], case.taxonomy["role"], forum_id)
        sc = self.packs.scenario(ref.scenario_id)
        case.forum_id = forum_id
        case.scenario_id, case.scenario_version = sc.id, sc.version
        case.ontology_code = sc.ontology
        case.language = pack.lang(case.language)
        case.currency = pack.currency
        self.audit(session, case, actor, "forum_chosen", forum=forum_id, scenario_id=sc.id)
        llm = self.llm_for(case)
        values = ai.extract_fields(llm, sc, pack, case.language, case.initial_text or "", None,
                                   self.missing_fields(case, sc))
        self._apply_values(case, sc, pack, values, llm, strict=False)
        self._save_vault(case, llm)
        forum_name = pack.localized(pack.coverage.forums[forum_id].name, case.language)
        intro = pack.t(case.language, "routing.universal_intro", forum=forum_name)
        reply = self.ack_reply(session, case) or self._next_step(session, case, sc, pack)
        reply.message = f"{intro}\n\n{reply.message}".strip()
        return reply

    def _handoff_level3(self, session: Session, case: Case, pack: JurisdictionPack) -> Reply:
        lang = pack.lang(case.language)
        case.coverage_level = qualifier.LEVEL_LAWYER
        case.needs_review = True
        self.transition(session, case, S.HANDED_TO_LAWYER, "system", reasons=case.route_reasons)
        reasons = "; ".join(pack.t(lang, f"routing.reasons.{r}", default=r) for r in case.route_reasons)
        message = pack.t(lang, "routing.handed_to_lawyer", reasons=reasons)
        self.notifier.notify(session, case, "handoff", message)
        return Reply(message=message)

    def missing_fields(self, case: Case, sc: Scenario) -> list[str]:
        """Fields still to ask, in interview order: what happened → evidence → identity document → personal data.
        The order within each group is the scenario's."""
        def stage(f: Any) -> int:
            if f.type == "evidence":
                return 2 if IDENTITY_KIND in f.evidence_kinds else 1
            return 3 if f.pii else 0
        missing = [f for f in sc.intake if f.name not in case.facts and f.name not in (case.skipped_fields or [])]
        return [f.name for f in sorted(missing, key=stage)]

    def _apply_values(self, case: Case, sc: Scenario, pack: JurisdictionPack, values: dict[str, Any],
                      llm: RedactingLLM | None, strict: bool, overwrite: bool = False) -> dict[str, str]:
        errors: dict[str, str] = {}
        facts = dict(case.facts)
        today = pack.local_now().date()
        for name, raw in values.items():
            try:
                f = sc.field(name)
            except KeyError:
                continue
            if f.type == "evidence" or (name in facts and not overwrite):
                continue
            try:
                facts[name] = normalize(f, raw, today=today)
            except FieldError as e:
                errors[name] = e.code
                continue
            if f.pii and llm is not None:
                llm.vault.register(f.pii, facts[name])
            if name in (case.skipped_fields or []):
                case.skipped_fields = [s for s in case.skipped_fields if s != name]
        case.facts = facts
        if sc.claim and sc.claim.amount_field and sc.claim.amount_field in facts:
            case.amount_at_stake = Decimal(str(facts[sc.claim.amount_field]))
        return errors if strict else {}

    def question_for(self, sc: Scenario, pack: JurisdictionPack, lang: str, name: str) -> Question:
        f = sc.field(name)
        text = pack.localized(f.question, lang) if f.question else pack.t(
            lang, f"fields.{name}.question", default=ai.field_label(sc, pack, lang, name))
        kinds = [{"kind": k, "label": pack.t(lang, f"evidence.{k}", default=k)} for k in f.evidence_kinds]
        return Question(field=name, text=text, type=f.type, optional=f.optional, evidence_kinds=kinds)

    def _next_step(self, session: Session, case: Case, sc: Scenario, pack: JurisdictionPack) -> Reply:
        lang = case.language
        for f in sc.intake:  # crime reports: labels instead of facts → ask once to describe facts
            if f.type == "longtext" and f.name in case.facts and \
                    safety.labels_instead_of_facts(pack.coverage, case, str(case.facts[f.name])):
                case.taxonomy = {**(case.taxonomy or {}), "labels_warned": True}
                case.facts = {k: v for k, v in case.facts.items() if k != f.name}
                case.pending_field = f.name
                q = self.question_for(sc, pack, lang, f.name)
                return Reply(message=f"{pack.t(lang, 'safety.facts_not_labels')}\n{q.text}", question=q,
                             error="facts_not_labels")
        missing = self.missing_fields(case, sc)
        if missing:
            case.pending_field = missing[0]
            q = self.question_for(sc, pack, lang, missing[0])
            return Reply(message=q.text, question=q)
        case.pending_field = None
        if case.status == S.INTAKE.value:
            self._sync_parties_and_claim(session, case, sc, pack)
            self.transition(session, case, S.QUALIFIED, "system")
        return Reply(message=pack.t(lang, "interview.done", summary=self.facts_summary(case, sc, pack)),
                     intake_complete=True)

    def facts_summary(self, case: Case, sc: Scenario, pack: JurisdictionPack) -> str:
        lines = []
        for f in sc.intake:
            if f.type == "evidence":
                n = sum(1 for e in case.evidence if e.kind in f.evidence_kinds)
                if n:
                    lines.append(f"• {ai.field_label(sc, pack, case.language, f.name)}: {n}")
                continue
            if f.name in case.facts:
                lines.append(f"• {ai.field_label(sc, pack, case.language, f.name)}: {display(f, case.facts[f.name])}")
        return "\n".join(lines)

    def handle_message(self, session: Session, case: Case, text: str) -> Reply:
        if case.status != S.INTAKE.value:
            raise EngineError("not_in_intake")
        if not case.scenario_id and case.coverage_level == qualifier.LEVEL_UNIVERSAL and case.taxonomy:
            pack = self.pack_of(case)
            return Reply(message=pack.t(pack.lang(case.language), "routing.choose_forum_first"),
                         options=self.forum_options(case))
        if not case.scenario_id:
            combined = f"{case.initial_text or ''}\n{text}".strip()
            case.initial_text = combined
            return self._qualify_and_continue(session, case, combined)
        ack = self.ack_reply(session, case)
        if ack is not None:
            return ack
        sc, pack = self.scenario_of(case), self.pack_of(case)
        lang = case.language
        llm = self.llm_for(case)
        pending = case.pending_field
        if pending:
            f = sc.field(pending)
            if f.type == "evidence" and (_is_skip(text, pack, lang) or _is_done(text, pack, lang)):
                if any(e.kind in f.evidence_kinds for e in case.evidence):
                    case.facts = {**case.facts, f.name: "provided"}  # files uploaded: this question is done
                    return self._next_step(session, case, sc, pack)
            if _is_skip(text, pack, lang):
                if not f.optional:
                    q = self.question_for(sc, pack, lang, pending)
                    return Reply(message=f"{pack.t(lang, 'interview.required')}\n{q.text}", question=q,
                                 error="required")
                case.skipped_fields = [*(case.skipped_fields or []), pending]
                return self._next_step(session, case, sc, pack)
            if f.type == "evidence":
                q = self.question_for(sc, pack, lang, pending)
                return Reply(message=f"{pack.t(lang, 'interview.upload_or_skip')}\n{q.text}", question=q)
            if f.pii:
                # personal data is taken verbatim, it never goes to the LLM
                values = {pending: text}
            else:
                values = ai.extract_fields(llm, sc, pack, lang, text, pending, self.missing_fields(case, sc))
                values.setdefault(pending, text)
            errors = self._apply_values(case, sc, pack, values, llm, strict=True)
            self._save_vault(case, llm)
            if pending in errors:
                q = self.question_for(sc, pack, lang, pending)
                msg = pack.t(lang, f"errors.{errors[pending]}", default=pack.t(lang, "errors.generic"))
                return Reply(message=f"{msg}\n{q.text}", question=q, error=errors[pending])
        return self._next_step(session, case, sc, pack)

    # ================================================================ evidence
    def add_evidence(self, session: Session, case: Case, *, kind: str, filename: str, content_type: str,
                     data: bytes) -> Evidence:
        ev = Evidence(case_id=case.id, kind=kind, filename=filename, content_type=content_type,
                      extracted_facts={})
        ev.id = uuid.uuid4()
        ev.storage_key = self.storage.put(f"cases/{case.id}/evidence/{ev.id}/{_safe_name(filename)}",
                                          data, content_type)
        ev.text = extract_text(content_type, data)
        session.add(ev)
        case.evidence.append(ev)
        if kind == IDENTITY_KIND:
            # an identity document is personal data: never sent to the LLM (not even with image extraction on)
            if case.scenario_id and case.status == S.INTAKE.value:
                sc = self.scenario_of(case)
                m = _IIN.search(ev.text or "")
                if m and any(f.name == "applicant_iin" for f in sc.intake):
                    ev.extracted_facts = {"applicant_iin": m.group(0)}
            self.audit(session, case, "user", "evidence_added", kind=kind)
            return ev
        if case.scenario_id and case.status == S.INTAKE.value:
            sc, pack = self.scenario_of(case), self.pack_of(case)
            llm = self.llm_for(case)
            attachments: tuple[Attachment, ...] = ()
            if content_type.startswith("image/") and self.config.extract_images_with_llm:
                attachments = (Attachment(content_type, data, filename),)
            if ev.text or attachments:
                facts, summary = ai.extract_evidence(llm, sc, pack, case.language, ev.text, attachments)
                valid: dict[str, Any] = {}
                today = pack.local_now().date()
                for name, raw in facts.items():
                    try:
                        valid[name] = normalize(sc.field(name), raw, today=today)
                    except (FieldError, KeyError):
                        continue
                ev.extracted_facts = valid
                self._save_vault(case, llm)
        self.audit(session, case, "user", "evidence_added", kind=kind, filename=filename)
        return ev

    def confirm_evidence(self, session: Session, case: Case, evidence: Evidence,
                         facts: dict[str, Any] | None) -> Reply:
        sc, pack = self.scenario_of(case), self.pack_of(case)
        llm = self.llm_for(case)
        chosen = evidence.extracted_facts if facts is None else facts
        errors = self._apply_values(case, sc, pack, chosen, llm, strict=True, overwrite=True)
        self._save_vault(case, llm)
        evidence.confirmed = True
        self.audit(session, case, "user", "evidence_confirmed", evidence_id=str(evidence.id),
                   facts=list(chosen), errors=errors)
        if case.status != S.INTAKE.value:
            return Reply(message="")
        # the evidence question stays open: the user may add more files, then says "done"
        reply = self._next_step(session, case, sc, pack)
        q = reply.question
        kinds = {k["kind"] for k in q.evidence_kinds} if q and q.type == "evidence" else set()
        if evidence.kind in kinds:
            q.uploaded = sum(1 for e in case.evidence if e.kind in kinds)
            reply.message = f"{pack.t(case.language, 'interview.evidence_added', n=str(q.uploaded))}\n{reply.message}"
        if errors:
            reply.error = ",".join(f"{k}:{v}" for k, v in errors.items())
        return reply

    # ================================================================ actions
    def responses(self, case: Case) -> dict[str, str | None]:
        return {a.action_id: a.response_class for a in case.actions}

    def next_action_spec(self, case: Case, sc: Scenario) -> ActionSpec | None:
        if not case.actions:
            return sc.actions[0]
        done = {a.action_id for a in case.actions}
        responses = self.responses(case)
        for spec in sc.actions:
            if spec.id in done:
                continue
            cond = spec.condition
            if cond and cond.evaluate(responses):
                return spec
        return None

    def plan(self, session: Session, case: Case) -> dict[str, Any] | None:
        """The proposed solution shown right after the story: which document, to whom, through which service,
        what to attach, and whether a lawyer checks it first. Everything comes from scenario / pack data."""
        if not case.scenario_id or case.status not in (S.INTAKE.value, S.QUALIFIED.value):
            return None
        sc, pack = self.scenario_of(case), self.pack_of(case)
        spec = self.next_action_spec(case, sc)
        if spec is None or spec.kind == "handoff":
            return None
        lang = case.language
        addressee = self._addressee(case, sc, pack, spec)
        channels: list[dict[str, Any]] = []
        attachments: list[str] = []
        cov = pack.coverage
        forum = cov.forums.get(spec.addressee.forum) if cov and spec.addressee and spec.addressee.forum else None
        if forum is None and is_generic(case.scenario_id) and cov:  # a claim to the other party itself
            ref = GenericRef.parse(case.scenario_id or "")
            forum = cov.forums.get(ref.forum_id) if ref else None
        if forum is not None:
            channels = [{"kind": ch.kind, "url": ch.url} for ch in forum.submission]
            doc = cov.document_for(forum) if cov else None
            if doc is not None:
                attachments += list(doc.attachments.get(lang) or doc.attachments.get(pack.manifest.default_language) or ())
        else:
            if addressee.get("submit_url"):
                channels.append({"kind": "portal", "url": addressee["submit_url"]})
            if spec.channel == "email_or_user_submits":
                channels += [{"kind": "in_person", "url": None}, {"kind": "post", "url": None},
                             {"kind": "email", "url": None}]
            elif not channels:
                channels = [{"kind": "in_person", "url": None}, {"kind": "post", "url": None}]
        for f in sc.intake:  # the evidence the interview asks for
            if f.type == "evidence":
                attachments += [pack.t(lang, f"evidence.{k}", default=k) for k in f.evidence_kinds if k != "other"]
        seen: set[str] = set()
        attachments = [a for a in attachments if not (a in seen or seen.add(a))]
        return {"document": pack.localized(spec.title, lang),
                "addressee": addressee.get("name") or None,
                "channels": channels, "attachments": attachments,
                "lawyer_check": self.approval_required(session, case, spec)}

    def proposal(self, case: Case) -> Proposal:
        if not case.scenario_id:
            return Proposal(type="none")
        sc, pack = self.scenario_of(case), self.pack_of(case)
        lang = case.language
        status = CaseStatus(case.status)
        if status == S.INTAKE:
            return Proposal(type="none")
        if status == S.QUALIFIED:
            spec = sc.actions[0]
            return Proposal(type="prepare_action", action_id=spec.id, title=pack.localized(spec.title, lang),
                            message=pack.t(lang, "proposal.prepare", action=pack.localized(spec.title, lang)))
        if status in (S.ACTION_READY, S.SUBMITTED, S.HANDED_TO_LAWYER, S.RESOLVED):
            return Proposal(type="wait")
        last = case.actions[-1]
        if last.response_class is None:
            return Proposal(type="wait", message=pack.t(lang, "proposal.wait"))
        rc = last.response_class
        if rc == "unclear":
            return Proposal(type="clarify", response_class=rc, message=pack.t(lang, "proposal.clarify"))
        if rc == "full":
            return Proposal(type="close", response_class=rc, suggested_result="won",
                            message=pack.t(lang, "proposal.close_won"))
        spec = self.next_action_spec(case, sc)
        if spec is None:
            return Proposal(type="close", response_class=rc,
                            suggested_result="partial" if rc == "partial" else "lost",
                            message=pack.t(lang, "proposal.no_more_steps"))
        title = pack.localized(spec.title, lang)
        if spec.kind == "handoff":
            return Proposal(type="handoff", action_id=spec.id, title=title, response_class=rc,
                            message=pack.t(lang, "proposal.handoff"))
        return Proposal(type="prepare_action", action_id=spec.id, title=title, response_class=rc,
                        message=pack.t(lang, "proposal.escalate", action=title))

    def document_type(self, case: Case, spec: ActionSpec) -> str | None:
        """Document type of a universal-path action (from the forum registry); None for signed scenarios."""
        pack = self.pack_of(case)
        cov = pack.coverage
        if cov is None or not is_generic(case.scenario_id):
            return None
        if spec.addressee and spec.addressee.forum:
            forum = cov.forums.get(spec.addressee.forum)
        else:  # a claim to the other party itself
            ref = GenericRef.parse(case.scenario_id or "")
            forum = cov.forums.get(ref.forum_id) if ref else None
        doc = cov.document_for(forum) if forum else None
        return doc.id if doc else None

    def _to_court(self, case: Case, spec: ActionSpec) -> bool:
        cov = self.pack_of(case).coverage
        forum = cov.forums.get(spec.addressee.forum) if cov and spec.addressee and spec.addressee.forum else None
        return forum is not None and forum.type == "court"

    def approval_required(self, session: Session, case: Case, spec: ActionSpec | None = None) -> bool:
        if self.config.self_service and not case.needs_review and case.hold_reason is None:
            if not is_generic(case.scenario_id):
                return False  # signed / draft level-1 scenarios contain pre-trial documents only
            if spec is not None and self.document_type(case, spec) in self.config.self_service_documents \
                    and not self._to_court(case, spec):
                return False
            return True  # court documents (lawsuit, appeal) are filed only after a lawyer's check
        if case.needs_review or case.coverage_level == qualifier.LEVEL_UNIVERSAL or is_generic(case.scenario_id):
            return True
        rank = session.scalar(select(func.count()).select_from(Case).where(
            Case.scenario_id == case.scenario_id, Case.created_at <= case.created_at))
        return (rank or 0) <= self.config.approval_required_first_n

    def prepare_next_action(self, session: Session, case: Case, actor: str) -> Action:
        if not case.scenario_id:
            raise EngineError("no_document_path")
        sc, pack = self.scenario_of(case), self.pack_of(case)
        if case.hold_reason is None and not case.actions:
            reason = safety.abuse_reason(session, pack.coverage, case)
            if reason:
                case.hold_reason = reason
                self.audit(session, case, "system", "hold", reason=reason)
        if case.hold_reason is not None:
            raise EngineError("on_hold")
        status = CaseStatus(case.status)
        if status == S.INTAKE:
            reply = self._next_step(session, case, sc, pack)
            if not reply.intake_complete:
                raise EngineError("intake_incomplete")
            status = CaseStatus(case.status)
        # re-preparing a rejected document for the same action
        if status == S.ACTION_READY and case.actions and case.actions[-1].approval_status == "rejected":
            return self._render_action(session, case, sc, pack, sc.action(case.actions[-1].action_id),
                                       case.actions[-1], actor)
        if status not in (S.QUALIFIED, S.AWAITING_RESPONSE, S.ESCALATED):
            raise EngineError("cannot_prepare_now")
        if status != S.QUALIFIED:
            last = case.actions[-1] if case.actions else None
            if not last or not last.response_class:
                raise EngineError("response_required")
            if last.response_class in ("full", "unclear"):
                raise EngineError("no_escalation_for_response")
        spec = self.next_action_spec(case, sc)
        if spec is None:
            raise EngineError("no_next_action")
        if status == S.AWAITING_RESPONSE:
            self.transition(session, case, S.ESCALATED, actor, reason=case.actions[-1].response_class)
        action = Action(case_id=case.id, sequence=len(case.actions) + 1, action_id=spec.id, kind=spec.kind,
                        channel=spec.channel, is_draft_scenario=sc.is_draft)
        session.add(action)
        case.actions.append(action)
        if spec.kind == "handoff":
            action.status = "done"
            self.transition(session, case, S.HANDED_TO_LAWYER, actor, action=spec.id)
            self.notifier.notify(session, case, "handoff", pack.t(case.language, "notifications.handoff"))
            return action
        if not case.paid and sc.pricing.model == "fixed":
            inv = self.payments.create_invoice(case_id=str(case.id), amount=Decimal(str(sc.pricing.amount)),
                                               currency=sc.pricing.currency or pack.currency)
            case.paid = inv.status == "paid"
            self.audit(session, case, "system", "invoice_created", invoice=inv.id, status=inv.status,
                       amount=str(inv.amount), currency=inv.currency)
        return self._render_action(session, case, sc, pack, spec, action, actor)

    def _addressee(self, case: Case, sc: Scenario, pack: JurisdictionPack, spec: ActionSpec) -> dict[str, Any]:
        lang = case.language
        if spec.addressee is None:
            return {}
        if spec.addressee.forum:
            forum = pack.coverage.forums[spec.addressee.forum]
            portal = next((c.url for c in forum.submission if c.kind == "portal"), None)
            email = next((c.email for c in forum.submission if c.kind == "email"), None)
            return {"kind": "forum", "key": forum.id, "name": pack.localized(forum.name, lang), "address": "",
                    "email": email, "submit_url": portal, "id": None, "type": forum.type,
                    "legal_effect": forum.legal_effect, "verified": forum.verified}
        if spec.addressee.authority:
            auth = pack.manifest.authorities[spec.addressee.authority]
            return {"kind": "authority", "key": spec.addressee.authority, "name": pack.localized(auth.name, lang),
                    "address": pack.localized(auth.address, lang) if auth.address else "",
                    "email": auth.email, "submit_url": auth.submit_url, "id": None}
        party = sc.parties[spec.addressee.party]
        get = lambda attr: case.facts.get(getattr(party, attr)) if getattr(party, attr) else None  # noqa: E731
        return {"kind": party.kind, "key": spec.addressee.party, "name": get("name_field") or "",
                "id": get("id_field"), "email": get("email_field"), "address": get("address_field") or "",
                "submit_url": None}

    def _render_action(self, session: Session, case: Case, sc: Scenario, pack: JurisdictionPack,
                       spec: ActionSpec, action: Action, actor: str) -> Action:
        lang = case.language
        title = pack.localized(spec.title, lang)
        addressee = self._addressee(case, sc, pack, spec)
        llm = self.llm_for(case)
        if not case.narrative:
            # the narrative needs no personal data: names/ids are printed in the header by the template
            facts = {fl.name: display(fl, case.facts[fl.name]) for fl in sc.intake
                     if fl.name in case.facts and fl.type != "evidence" and not fl.pii}
            attached = sorted({pack.t(lang, f"evidence.{e.kind}", default=e.kind) for e in case.evidence
                               if e.kind not in ("response", IDENTITY_KIND)})
            case.narrative = ai.write_narrative(llm, sc, pack, lang, facts, title, attached)
            self._save_vault(case, llm)
        if is_generic(sc.id) and not case.formal_demands and case.facts.get("desired_outcome"):
            case.formal_demands = ai.write_demands(llm, pack, lang, str(case.facts["desired_outcome"]), title)
            self._save_vault(case, llm)
        ctx = self.document_context(case, sc, pack, spec, addressee)
        docx = render_docx(pack.packs_root / spec.template, ctx,
                           ai_label=pack.localized(pack.manifest.compliance.ai_label, lang),
                           draft_disclaimer=pack.localized(pack.manifest.compliance.draft_disclaimer, lang)
                           if sc.is_draft else None)
        base = f"cases/{case.id}/actions/{action.sequence:02d}-{spec.id}"
        action.docx_key = self.storage.put(f"{base}.docx", docx,
                                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        pdf = self.pdf.convert(docx)
        action.pdf_key = self.storage.put(f"{base}.pdf", pdf, "application/pdf") if pdf else None
        action.addressee = addressee
        action.instructions = [
            s.format_map(_Fmt(ctx["fmt"])) for s in (spec.instructions.get(lang) or
                                                      spec.instructions.get(pack.manifest.default_language) or ())
        ]
        if self.approval_required(session, case, spec):
            action.approval_status, action.status = "pending", "pending_approval"
        else:
            action.approval_status, action.status = "not_required", "ready"
        if case.status != S.ACTION_READY.value:
            self.transition(session, case, S.ACTION_READY, actor, action=spec.id)
        self.audit(session, case, actor, "document_generated", action=spec.id,
                   approval=action.approval_status, pdf=bool(pdf))
        return action

    def document_context(self, case: Case, sc: Scenario, pack: JurisdictionPack, spec: ActionSpec,
                         addressee: dict[str, Any]) -> dict[str, Any]:
        lang = case.language
        f = {fl.name: display(fl, case.facts.get(fl.name)) for fl in sc.intake if fl.type != "evidence"}
        applicant = {}
        if "applicant" in sc.parties:
            p = sc.parties["applicant"]
            applicant = {"name": f.get(p.name_field, ""), "id": f.get(p.id_field or "", ""),
                         "email": f.get(p.email_field or "", ""), "address": f.get(p.address_field or "", "")}
        evidence = [pack.t(lang, f"evidence.{e.kind}", default=e.kind) + (f" ({e.filename})" if e.filename else "")
                    for e in case.evidence if e.kind != "response"]
        previous = [{"title": pack.localized(sc.action(a.action_id).title, lang),
                     "date": a.submitted_at.strftime("%d.%m.%Y") if a.submitted_at else "",
                     "response": pack.t(lang, f"responses.{a.response_class}", default=a.response_class or "")}
                    for a in case.actions if a.action_id != spec.id and a.submitted_at]
        today = pack.local_now().date().strftime("%d.%m.%Y")
        fmt = {**f, "addressee": addressee.get("name", ""), "submit_url": addressee.get("submit_url") or "",
               "addressee_email": addressee.get("email") or "", "currency": case.currency or pack.currency,
               "today": today, "formal_demands": case.formal_demands or f.get("desired_outcome", "")}
        if spec.deadline:
            fmt["deadline_days"] = spec.deadline.calendar_days or spec.deadline.business_days
        demands = pack.localized(spec.demands, lang).format_map(_Fmt(fmt)) if spec.demands else ""
        return {
            "title": pack.localized(spec.title, lang),
            "f": f,
            "applicant": applicant,
            "addressee": addressee,
            "narrative": case.narrative or f.get("problem_description", ""),
            "demands": demands,
            "norm_refs": list(spec.norm_refs),
            "evidence": evidence,
            "previous_actions": previous,
            "date": today,
            "currency": case.currency or pack.currency,
            "fmt": fmt,
        }

    def approve(self, session: Session, action: Action, reviewer: str, approved: bool, note: str | None) -> None:
        if action.approval_status != "pending":
            raise EngineError("not_pending")
        case = session.get(Case, action.case_id)
        action.approval_status = "approved" if approved else "rejected"
        action.status = "ready" if approved else "rejected"
        action.approved_by, action.approval_note = reviewer, note
        self.audit(session, case, f"admin:{reviewer}", "document_approved" if approved else "document_rejected",
                   action=action.action_id, note=note)
        pack = self.pack_of(case)
        key = "notifications.approved" if approved else "notifications.rejected"
        self.notifier.notify(session, case, "approval", pack.t(case.language, key))

    def mark_submitted(self, session: Session, case: Case, action: Action, actor: str,
                       via: str = "user_submits") -> None:
        if action.kind != "document" or action.status != "ready":
            raise EngineError("document_not_ready")
        if case.status != S.ACTION_READY.value:
            raise EngineError("cannot_submit_now")
        sc, pack = self.scenario_of(case), self.pack_of(case)
        spec = sc.action(action.action_id)
        if via == "email":
            if spec.channel == "user_submits":
                raise EngineError("email_not_allowed")
            adapter = self.submissions["email"]
            files = [(f"{spec.id}.docx", self.storage.get(action.docx_key),
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]
            if action.pdf_key:
                files.append((f"{spec.id}.pdf", self.storage.get(action.pdf_key), "application/pdf"))
            if action.signatures:  # the ЭЦП-signed file (CMS with the document inside)
                sig = action.signatures[-1]
                files.append((f"{spec.id}.{sig.file_format}.cms", self.storage.get(sig.cms_key),
                              "application/pkcs7-mime"))
            user = session.get(User, case.owner_id)
            adapter.submit(to_email=(action.addressee or {}).get("email"), subject=pack.localized(spec.title, case.language),
                           body=pack.t(case.language, "email.body"), reply_to=user.email, attachments=files)
        now = utcnow()
        action.status, action.submitted_at, action.submitted_via = "submitted", now, via
        self.transition(session, case, S.SUBMITTED, actor, action=spec.id, via=via)
        if spec.deadline:
            start = now.astimezone(pack.tz).date()
            due = pack.add_days(start, spec.deadline.calendar_days, spec.deadline.business_days)
            remind = list(spec.deadline.remind_before_days or pack.manifest.reminder_before_days)
            self.scheduler.schedule(session, case, action, due, spec.deadline.norm_ref, remind)
            self.audit(session, case, "system", "deadline_created", action=spec.id, due=due.isoformat(),
                       norm_ref=spec.deadline.norm_ref)
        self.transition(session, case, S.AWAITING_RESPONSE, "system", action=spec.id)

    def record_response(self, session: Session, case: Case, action: Action, *, text: str | None,
                        response_class: str | None = None, actor: str = "user") -> Proposal:
        if case.status != S.AWAITING_RESPONSE.value or not case.actions or case.actions[-1].id != action.id:
            raise EngineError("not_awaiting_response")
        sc, pack = self.scenario_of(case), self.pack_of(case)
        summary = ""
        if response_class is None:
            if text and text.strip():
                llm = self.llm_for(case)
                response_class, summary = ai.classify_response(
                    llm, pack, case.language, text, pack.localized(sc.action(action.action_id).title, case.language))
                self._save_vault(case, llm)
            else:
                response_class = "none"
        action.response_class, action.response_summary, action.responded_at = response_class, summary, utcnow()
        action.status = "responded"
        self.scheduler.cancel_for_action(session, action, status="met" if response_class != "none" else "expired")
        self.audit(session, case, actor, "response_recorded", action=action.action_id,
                   response_class=response_class, classified_by="user" if text is None else "llm")
        return self.proposal(case)

    def close(self, session: Session, case: Case, *, result: str, amount_recovered: Decimal | None,
              comment: str | None, actor: str) -> Outcome:
        if result not in OUTCOME_RESULTS:
            raise EngineError("bad_result")
        if amount_recovered is not None:
            amount_recovered = Decimal(str(amount_recovered)).quantize(Decimal("0.01"))
        self.transition(session, case, S.RESOLVED, actor, result=result)
        created = case.created_at if case.created_at.tzinfo else case.created_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        for a in case.actions:
            self.scheduler.cancel_for_action(session, a, status="cancelled")
        outcome = Outcome(case_id=case.id, result=result, amount_recovered=amount_recovered,
                          currency=case.currency, days_to_resolution=max(0, (now - created).days),
                          resolved_at_step=case.actions[-1].action_id if case.actions else None,
                          scenario_id=case.scenario_id, scenario_version=case.scenario_version,
                          comment=comment, resolved_at=now)
        session.add(outcome)
        case.outcome = outcome
        self.audit(session, case, actor, "outcome_recorded", result=result,
                   amount_recovered=str(amount_recovered) if amount_recovered is not None else None,
                   days=outcome.days_to_resolution, step=outcome.resolved_at_step)
        return outcome

    # ================================================================ parties/claims
    def _sync_parties_and_claim(self, session: Session, case: Case, sc: Scenario, pack: JurisdictionPack) -> None:
        existing = {p.role for p in case.parties}
        for role, spec in sc.parties.items():
            if role in existing:
                continue
            name = case.facts.get(spec.name_field)
            if role == "applicant":
                session.add(Party(case_id=case.id, role=role, user_id=case.owner_id, display_name=name))
                continue
            org = Organization(country=case.jurisdiction, kind=spec.kind, name=name or "?",
                               registration_id=case.facts.get(spec.id_field) if spec.id_field else None,
                               email=case.facts.get(spec.email_field) if spec.email_field else None,
                               address=case.facts.get(spec.address_field) if spec.address_field else None)
            session.add(org)
            session.flush()
            session.add(Party(case_id=case.id, role=role, organization_id=org.id, display_name=name))
        if sc.claim and not case.claims:
            session.add(Claim(case_id=case.id, type=sc.claim.type, amount=case.amount_at_stake,
                              currency=case.currency,
                              norm_refs=sorted({r for a in sc.actions for r in a.norm_refs})))


# ==================================================================== utils
class _Fmt(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _is_skip(text: str, pack: JurisdictionPack, lang: str) -> bool:
    words = pack.i18n.get(lang, {}).get("interview", {}).get("skip_words", []) or []
    t = text.strip().lower().strip(".!")
    return t in {w.lower() for w in words} or t in {"-", "—", "/skip"}


def _is_done(text: str, pack: JurisdictionPack, lang: str) -> bool:
    words = pack.i18n.get(lang, {}).get("interview", {}).get("done_words", []) or []
    return text.strip().lower().strip(".!") in {w.lower() for w in words}


def _safe_name(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return keep[-100:] or "file"


def extract_text(content_type: str, data: bytes) -> str | None:
    if content_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip() or None
        except Exception as e:  # damaged PDF etc.
            log.warning("pdf text extraction failed: %s", e)
            return None
    if content_type.startswith("text/"):
        return data.decode("utf-8", errors="replace")
    return None


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)
