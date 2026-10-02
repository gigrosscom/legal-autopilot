"""CaseEngine — the deterministic driver of a case.

The engine owns every decision about *what happens next*: which question to ask,
which scenario action comes next (by ``when`` conditions from YAML), when a
deadline starts, when a lawyer must approve. The LLM is only consulted for
language tasks through ``core.ai``.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ai, docgate, package, polish, qualifier, safety
from .adapters.payment import PaymentAdapter
from .adapters.storage import Storage
from .adapters.submission import SubmissionAdapter
from .deadlines import DeadlineScheduler
from .documents import PdfConverter, docx_text, render_docx
from .docstyle import DocStyle
from .fields import FieldError, display, looks_like_address, normalize
from .llm import Attachment, LLMProvider, RedactingLLM
from .generic import GenericRef, is_generic
from .models import (
    Action,
    AuditLog,
    Case,
    ChatMessage,
    Claim,
    Consent,
    DemandSignal,
    Evidence,
    Invoice,
    Organization,
    Outcome,
    Party,
    Subscription,
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
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
IDENTITY_KIND = "id_document"  # a copy of the applicant's ID: attached to documents, never read by the LLM
_IIN = re.compile(r"(?<!\d)\d{12}(?!\d)")
OUTCOME_RESULTS = ("won", "partial", "lost", "settled", "abandoned")


# the details a document needs that the form before payment asks (ZANN, api/chat.py DOC_DETAIL)
_DOC_DETAIL = re.compile(r"_(?:name|address|bin|iin|email|phone)$")



def _aware(d: datetime) -> datetime:
    """A stored time as UTC-aware (SQLite gives naive datetimes back)."""
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

class EngineError(Exception):
    """A request that is valid HTTP but not allowed in the current case state."""

    def __init__(self, code: str, message: str | None = None, fields: list[str] | None = None):
        self.code = code
        self.fields = fields or []  # document_check: the one field the client is asked to fix
        super().__init__(message or code)


@dataclass
class Question:
    field: str
    text: str
    type: str
    optional: bool
    evidence_kinds: list[dict[str, str]] = field(default_factory=list)
    uploaded: int = 0  # files already attached to this evidence question
    pattern: str | None = None  # the field's format (e.g. twelve digits): lets the web show a digit keypad


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
    # at most this many interview questions, then the draft (the rest are blanks filled in the draft); 0 = no cap;
    # -1 = no questions on the site: the draft at once, filled from the story, the chat and the files (owner 01.10,
    # «3 клика»); the Telegram bot keeps the questions (it has no draft screen)
    intake_max_questions: int = 0  # owner 02.10 (decision 226): ask what is missing, documents first
    case_price: int = 9990  # «Дело под ключ»: every document of one case
    # owner 01.10: a Kaspi Pay link payment gives the document at «Оплатить»; the desk matches it afterwards
    trust_kaspi_link: bool = True
    # owner 02.10: until the payment is set up, «Я оплатил(а)» gives the document on trust for every way to pay
    trust_all: bool = False
    # owner 02.10 «Бонусный счёт»: points to the invited person (on joining) and to the inviter (on that person's
    # first payment); 0 = the old reward, one free document each. At most referral_bonus_max_share of a bill.
    referral_bonus_points: int = 0
    referral_bonus_max_share: float = 0.5
    # subscriptions: plan → (price, documents per period)
    plans: dict[str, tuple[int, int]] = field(default_factory=lambda: {"biz": (29990, 20), "bizpro": (59990, 60)})
    plan_days: int = 30
    plan_currency: str = ""  # empty: the currency of the jurisdiction pack
    # «Юрист по кнопке» (core/lawyer_pilot.py): the company's payment channel only (never the personal Kaspi Gold)
    lawyer_commission_pct: float = 15.0
    lawyer_pay_direct: bool = False  # the client pays the lawyer directly (core/lawyer_pilot.py)
    lawyer_pay_link: str = ""  # the ТОО's Kaspi Pay link (https://…)
    lawyer_pay_account: str = ""  # the ТОО's requisites as text (tax number, IBAN, bank)
    company_name: str = ""  # ТОО «…», shown as the recipient
    # Kaspi Pay pushes are on (PAYMENT_KASPI_PUSH_TOKEN, konsilier/kaspi_parse.py): a Kaspi link / QR bill whose
    # «Оплатить» no push matched within UNPAID_AFTER stops the person's new bills until it is paid (owner 01.10)
    kaspi_push: bool = False


_NORM = re.compile(r"^(?P<act>.+?), (?:статья|статьи) (?P<art>[\w.-]+)$")


def group_norms(refs: Any) -> list[str]:
    """«Закон …, статья 30» + «Закон …, статья 42-4» → «Закон …, статьи 30 и 42-4» (P0 02.10: the act is named once)."""
    out: list[str] = []
    acts: dict[str, list[str]] = {}
    for ref in refs or ():
        if "TODO" in str(ref):  # a norm not yet checked never reaches the document (owner 02.10: no «уточнит юрист»)
            continue
        m = _NORM.match(str(ref).strip())
        if not m:
            out.append(str(ref))
            continue
        if m["act"] not in acts:
            acts[m["act"]] = []
            out.append(m["act"])
        acts[m["act"]].append(m["art"])
    result = []
    for item in out:
        arts = acts.get(item)
        if arts is None:
            result.append(item)
        elif len(arts) == 1:
            result.append(f"{item}, статья {arts[0]}")
        else:
            result.append(f"{item}, статьи {', '.join(arts[:-1])} и {arts[-1]}")
    return result


_EMPTY_BRACKETS = re.compile(r"\s*\(\s*\)")


def _tidy(text: str) -> str:
    """An instruction whose placeholder is still unknown (no addressee name yet) loses the empty «()» around it."""
    return _EMPTY_BRACKETS.sub("", text)


class CaseEngine:
    def __init__(self, *, packs: PackRegistry, llm: LLMProvider, storage: Storage, pdf: PdfConverter,
                 scheduler: DeadlineScheduler, notifier: Notifier, payments: PaymentAdapter,
                 submissions: dict[str, SubmissionAdapter], config: EngineConfig):
        self.packs = packs
        self.llm_provider = llm
        self.storage = storage
        self.pdf = pdf
        # PDF made after the document is handed out (ensure_pdf), so the document appears at once
        self.defer_pdf = False
        # called when a document waits for a lawyer's check, so the lawyer learns of it at once (set by the container)
        self.on_approval_needed: Any = None
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
    def facts_from_chat(self, session: Session, case_id: Any, text: str, keep_question: bool = False) -> list[str]:
        """QA BUG-03: what the person tells the chat goes into the case, so the interview asks only what is still
        missing (and the case can reach «Подготовить документ» without the same questions again). Runs after the
        chat reply, in the background; only while the case is being filled in. Returns the fields filled."""
        case = session.get(Case, case_id)
        if case is None or case.status not in (S.INTAKE.value, S.QUALIFIED.value) or not case.scenario_id \
                or len((text or "").strip()) < 15:
            return []
        sc, pack = self.scenario_of(case), self.pack_of(case)
        # the draft's blanks too: told in the chat after «Данные собраны», they go into the document (owner 01.10)
        missing = [n for n in [*self.missing_fields(case, sc), *self.draft_blanks(case, sc)] if sc.field(n).type != "evidence"
                   and not (keep_question and n == case.pending_field)]  # the question on screen stays as asked
        if not missing:
            return []
        llm = self.llm_for(case)
        before = set(case.facts)
        values = ai.extract_fields(llm, sc, pack, case.language, text, None, missing)
        self._apply_values(case, sc, pack, values, llm, strict=False)
        self._save_vault(case, llm)
        filled = sorted(set(case.facts) - before)
        if not filled:
            return []
        self.audit(session, case, "system", "facts_from_chat", fields=filled)
        if case.status == S.INTAKE.value and not keep_question \
                and (case.pending_field is None or case.pending_field in case.facts):
            self._next_step(session, case, sc, pack)  # the next question — or «Проверьте данные» when all is known
        return filled

    def qualify_later(self, session: Session, case_id: Any) -> None:
        """The scenario of a case opened by the chat (``defer_qualification``), in the background."""
        case = session.get(Case, case_id)
        if case is None or case.scenario_id or case.taxonomy:
            return
        self._qualify_and_continue(session, case, case.initial_text or "")
        if "emergency" in ((case.taxonomy or {}).get("flags") or []):
            self.audit(session, case, "system", "emergency_detected", by="llm")
        # what was told in the chat while the scenario was being worked out goes into the case too (PM 01.10)
        said = [m.text for m in session.scalars(select(ChatMessage).where(
            ChatMessage.case_id == case.id, ChatMessage.role == "user").order_by(ChatMessage.created_at)).all()
            if m.text and m.text.strip() != (case.initial_text or "").strip()]
        if said:
            self.facts_from_chat(session, case.id, "\n".join(said))

    def requalify_from_chat(self, session: Session, case_id: Any) -> bool:
        """A chat case whose first message said too little to classify («Здравствуйте, нужна помощь»): its taxonomy
        stayed empty and nothing ever looked again, so «Дела» showed «Новое дело · Определяем путь» for good (PM 02.10).
        Each new message in the chat tries again with everything the person has told so far."""
        case = session.get(Case, case_id)
        if case is None or case.scenario_id or case.status != S.INTAKE.value \
                or case.coverage_level != qualifier.LEVEL_VERIFIED or (case.taxonomy or {}).get("dispute_id"):
            return False  # classified, waiting for a forum, or handed to a lawyer
        said = [m.text.strip() for m in session.scalars(select(ChatMessage).where(
            ChatMessage.case_id == case.id, ChatMessage.role == "user").order_by(ChatMessage.created_at)).all()
            if m.text and m.text.strip()]
        first = (case.initial_text or "").strip()
        told = [t for t in said if t != first]
        if not told or (case.taxonomy or {}).get("chat_messages", 0) >= len(told):
            return False  # nothing new since the last try
        text = "\n".join([first, *told]).strip()[:8000]
        case.taxonomy, case.qualification_confidence = {}, None
        self.audit(session, case, "system", "requalify_from_chat", messages=len(told))
        self._qualify_and_continue(session, case, text)
        if case.scenario_id or (case.taxonomy or {}).get("dispute_id"):
            return True
        case.taxonomy = {**(case.taxonomy or {}), "chat_messages": len(told)}  # still unclear: try on the next one
        return False

    def start_case(self, session: Session, user: User, text: str, *, language: str | None = None,
                   channel: str | None = None, country: str | None = None,
                   defer_qualification: bool = False) -> tuple[Case, Reply]:
        """``defer_qualification``: the chat opens the case and answers at once; which scenario fits (an LLM call of
        several seconds) is worked out afterwards by ``qualify_later``."""
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
        if defer_qualification:
            reply = Reply(message="")
            if keyword_emergency:
                reply.emergency = self.emergency_info(case)
                self.audit(session, case, "system", "emergency_detected", by="keywords")
            return case, reply
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
        # a sole trader or a company in a dispute with a business: never a consumer scenario (consumer law does
        # not apply) — a business scenario if one is offered, else the business branch of the universal path
        business = any(safety.writes_as_business(p.coverage, text) for p in self.packs.packs.values()
                       if not case.jurisdiction or p.country == case.jurisdiction.upper())
        direct_sid = None
        if business:
            candidates = [s for s in candidates if "applicant" in s.parties and s.parties["applicant"].kind == "business"]
            self.audit(session, case, "system", "business_applicant")
        else:
            # QA BUG-24: a dispute the words alone decide (a private debt by a receipt) never goes to a model's guess
            for p in self.packs.packs.values():
                if case.jurisdiction and p.country != case.jurisdiction.upper():
                    continue
                rule = safety.direct_dispute(p.coverage, text)
                if rule is None:
                    continue
                self.audit(session, case, "system", "direct_dispute", dispute=rule.dispute, scenario=rule.scenario)
                if rule.scenario and any(s.id == rule.scenario for s in candidates):
                    direct_sid = rule.scenario
                    break
                if p.coverage is not None and p.coverage.has_registry:
                    return self._route_universal(session, case, p, llm, text, direct=rule)
        sid, confidence, reason = ((direct_sid, 1.0, "direct rule") if direct_sid else
                                   ai.qualify(llm, candidates, self.packs.packs, text, case.language) if candidates
                                   else (None, 0.0, "no business scenario"))
        case.qualification_confidence = confidence
        if sid is None:
            case.needs_review = True
            self.audit(session, case, "system", "qualification_failed", reason=reason)
            pack = self.pack_of(case)
            if pack.coverage is not None and pack.coverage.has_registry:
                return self._route_universal(session, case, pack, llm, text, business=business)
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
        self.read_unread_evidence(case, sc, pack)
        intro = pack.t(case.language, "interview.intro", scenario=pack.localized(sc.title, case.language),
                       first_action=pack.localized(sc.actions[0].title, case.language))
        reply = self._next_step(session, case, sc, pack)
        if reply.intake_complete and self.config.intake_max_questions < 0:  # «3 клика»: straight to the draft
            reply.message = pack.t(case.language, "interview.intro_draft",
                                   scenario=pack.localized(sc.title, case.language),
                                   first_action=pack.localized(sc.actions[0].title, case.language),
                                   default=reply.message)
            return reply
        reply.message = f"{intro}\n\n{reply.message}".strip()
        return reply

    # ================================================================ universal path (ADR 0001)
    def _route_universal(self, session: Session, case: Case, pack: JurisdictionPack, llm: RedactingLLM,
                         text: str, business: bool = False, direct: Any = None) -> Reply:
        cov = pack.coverage
        assert cov is not None
        lang = pack.lang(case.language)
        options = qualifier.taxonomy_options(cov, lang)
        roles = sorted({r for d in cov.disputes.values() for r in d.applicant_roles})
        if business:  # only disputes a business can bring (contract breach, unpaid invoice, tax…)
            options = [o for o in options if "business" in o["applicant_roles"]] or options
            roles = ["business"]
        result = ai.classify_taxonomy(llm, options, roles, text, lang)
        if direct is not None:  # the words decide the dispute; the model's flags (abuse, emergency…) still count
            result = {**result, "dispute_id": direct.dispute, "role": direct.role, "confidence": 1.0,
                      "reason": "direct rule"}
        if business and result.get("dispute_id") not in {o["id"] for o in options}:
            fallback = next((o["id"] for o in options if o["id"].endswith("contract_breach")), options[0]["id"])
            result = {**result, "dispute_id": fallback, "role": "business",
                      "confidence": max(float(result.get("confidence") or 0), cov.routing.min_confidence)}
        self._save_vault(case, llm)
        route = qualifier.route_universal(cov, result, amount=case.amount_at_stake,
                                          pending=safety.matter_pending(cov, text))
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
        # owner 02.10: the system picks the recipient — the dispute's own route (routes.yaml), else the pack rule
        # forum_order; the client only sees «Кому: …»
        picked = cov.auto_forum(route.forums, route.dispute_id)
        if picked is not None:
            return self.choose_forum(session, case, picked.id, actor="system")
        return Reply(message=pack.t(lang, "routing.choose_forum",
                                    dispute=pack.localized(cov.dispute(route.dispute_id).title, lang)),
                     options=[self.forum_option(pack, f, lang, cov.dispute(route.dispute_id))
                              for f in route.forums])

    def forum_option(self, pack: JurisdictionPack, forum: Any, lang: str, dispute: Any = None) -> dict[str, Any]:
        keys = (dispute.id, dispute.branch) if dispute is not None else ()
        hint = next((pack.localized(forum.hints[k], lang) for k in keys if k in forum.hints), None)
        pretrial = None
        if forum.legal_effect == "none":  # a step to the other side itself, not a body that decides
            pretrial = "mandatory" if any(k in forum.mandatory_for for k in keys) else "voluntary"
        out = {"id": forum.id, "name": pack.localized(forum.name, lang), "type": forum.type,
               "legal_effect": forum.legal_effect, "verified": forum.verified,
               "channels": [ch.kind for ch in forum.submission],
               # a court sets its own terms; elsewhere the term comes from the forum or from the hint
               "deadline_known": forum.response_deadline is not None or hint is not None or forum.type == "court",
               "pretrial": pretrial, "hint": hint}
        return out

    def recipient_route(self, case: Case) -> list[dict[str, Any]]:
        """Who each step's document goes to and why (routes.yaml): by the case's scenario, else its dispute type."""
        if not case.jurisdiction and not case.scenario_id:
            return []
        try:
            pack = self.pack_of(case)
        except Exception:  # noqa: BLE001 — no pack, no route
            return []
        cov = pack.coverage
        if cov is None:
            return []
        keys = [case.scenario_id, (case.taxonomy or {}).get("dispute_id")]
        route = next((cov.routes[k] for k in keys if k and k in cov.routes), None)
        if route is None:
            return []
        lang = case.language
        out = []
        for i, step in enumerate(route.steps, start=1):
            if step.forum is not None:
                kind, key, name = "forum", step.forum, pack.localized(cov.forums[step.forum].name, lang)
            elif step.authority is not None:
                auth = pack.manifest.authorities.get(step.authority)
                kind, key = "authority", step.authority
                name = pack.localized(auth.name, lang) if auth is not None else step.authority
            else:
                kind, key, name = "party", None, None
            out.append({"step": i, "kind": kind, "key": key, "name": name,
                        "label": pack.localized(step.label, lang), "when": pack.localized(step.when, lang) or None,
                        "why": pack.localized(step.why, lang), "norm": step.norm})
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
        pending = "pending" in (case.taxonomy.get("flags") or [])
        return [self.forum_option(pack, f, case.language, dispute)
                for f in cov.candidate_forums(dispute, case.taxonomy.get("role") or dispute.applicant_roles[0],
                                              pending)]

    def other_forums(self, case: Case) -> list[dict[str, Any]]:
        """«Другой адресат»: the forums the person may switch to while the document is not made yet."""
        if case.coverage_level != qualifier.LEVEL_UNIVERSAL or not case.forum_id or case.paid or case.actions \
                or case.status not in (S.INTAKE.value, S.QUALIFIED.value) or not case.taxonomy:
            return []
        pack = self.pack_of(case)
        cov = pack.coverage
        if cov is None or not case.taxonomy.get("dispute_id"):
            return []
        dispute = cov.dispute(case.taxonomy["dispute_id"])
        pending = "pending" in (case.taxonomy.get("flags") or [])
        return [self.forum_option(pack, f, case.language, dispute)
                for f in cov.candidate_forums(dispute, case.taxonomy.get("role") or dispute.applicant_roles[0], pending)
                if f.id != case.forum_id]

    def auto_choose_forum(self, session: Session, case: Case) -> bool:
        """A case left waiting at the old «Выберите адресата» list (before 02.10): the system chooses now."""
        if case.status != S.INTAKE.value or case.scenario_id or case.coverage_level != qualifier.LEVEL_UNIVERSAL \
                or not (case.taxonomy or {}).get("dispute_id"):
            return False
        cov = self.pack_of(case).coverage
        options = {o["id"] for o in self.forum_options(case)}
        picked = (cov.auto_forum([cov.forums[i] for i in cov.forums if i in options], case.taxonomy["dispute_id"])
                  if cov else None)
        if picked is None:
            return False
        self.choose_forum(session, case, picked.id, actor="system")
        return True

    def change_forum(self, session: Session, case: Case, forum_id: str, actor: str) -> Reply:
        """«Другой адресат»: before any document is made the step's recipient may be changed; facts already given stay."""
        if forum_id == case.forum_id:
            raise EngineError("forum_already_chosen")
        if forum_id not in {o["id"] for o in self.other_forums(case)}:
            raise EngineError("forum_not_allowed")
        self.audit(session, case, actor, "forum_changed", before=case.forum_id, forum=forum_id)
        if case.status == S.QUALIFIED.value:
            # nothing made or paid yet: back to filling in, so the new recipient's questions can be asked
            case.status = S.INTAKE.value
            self.audit(session, case, actor, "status_changed", S.QUALIFIED.value, S.INTAKE.value, reason="forum_changed")
        case.scenario_id, case.scenario_version, case.forum_id, case.pending_field = None, None, None, None
        session.flush()
        return self.choose_forum(session, case, forum_id, actor)

    def choose_forum(self, session: Session, case: Case, forum_id: str, actor: str) -> Reply:
        if case.status != S.INTAKE.value or case.scenario_id:
            if case.forum_id and forum_id != case.forum_id and case.status in (S.INTAKE.value, S.QUALIFIED.value):
                return self.change_forum(session, case, forum_id, actor)
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
        self.read_unread_evidence(case, sc, pack)
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

    def facts_missing(self, case: Case) -> list[str]:
        """R-29 (owner 02.10): the facts the case still lacks before a solution and a paid offer — what happened, when,
        how much, and who the other side is (its name: «кому»). Not the parties' addresses and ID numbers, nor the
        applicant's own data: those are asked in the form before payment (ZANN's rule in the chat's intake note).
        One list for the chat's note and the offer's gate. [] when complete; ["scenario"] while not classified."""
        if not case.scenario_id:
            return ["scenario"]
        sc = self.scenario_of(case)
        their_names = {p.name_field for role, p in sc.parties.items() if role != "applicant" and p.name_field}
        facts = case.facts or {}
        return [f.name for f in sc.intake
                if f.type != "evidence" and not f.optional and not f.pii and not facts.get(f.name)
                and (f.name in their_names or not _DOC_DETAIL.search(f.name))]

    def missing_fields(self, case: Case, sc: Scenario) -> list[str]:
        """Fields still to ask, in interview order: documents → what happened → identity document → personal data.
        Documents come first: what is in them is read and never asked. The order within each group is the
        scenario's."""
        def stage(f: Any) -> int:
            if f.type == "evidence":
                return 2 if IDENTITY_KIND in f.evidence_kinds else 0
            return 3 if f.pii else 1
        skipped = set(case.skipped_fields or [])
        # blanks left for the draft (DRAFT + name) are not asked again: the person fills them in the draft
        missing = [f for f in sc.intake if f.name not in case.facts and f.name not in skipped
                   and DRAFT + f.name not in skipped]
        return [f.name for f in sorted(missing, key=stage)]

    def _own_contacts(self, case: Case, sc: Scenario) -> set[str]:
        """The person's own e-mail / phone / id / address, lower-cased: never the other side's."""
        own: set[str] = set()
        owner = getattr(case, "owner", None)
        if owner is not None:
            own |= {x.strip().lower() for x in (owner.email, owner.phone) if x}
            own |= {i.display.strip().lower() for i in owner.identities if i.kind in ("email", "phone") and i.display}
        applicant = sc.parties.get("applicant")
        if applicant is not None:
            for a in ("email_field", "id_field", "address_field"):
                name = getattr(applicant, a, None)
                if name and case.facts.get(name):
                    own.add(str(case.facts[name]).strip().lower())
        for name in ("applicant_email", "applicant_phone", "applicant_iin", "applicant_address"):
            if case.facts.get(name):
                own.add(str(case.facts[name]).strip().lower())
        return own

    def rebuild_documents(self, session: Session, case: Case, rewrite_text: bool = True) -> int:
        """After the owner corrected the case's data: the documents not yet sent are made again from it (and the
        statement of circumstances rewritten, as it may name the corrected party). No notification, no status
        change. Returns how many were rebuilt."""
        sc, pack = self.scenario_of(case), self.pack_of(case)
        if rewrite_text:
            case.narrative = None
        done = 0
        for action in case.actions:
            if action.submitted_at or not action.docx_key:
                continue
            spec = sc.action(action.action_id)
            if not spec.template:
                continue
            lang = case.language
            self._ensure_text(case, sc, pack, pack.localized(spec.title, lang))
            addressee = self._addressee(case, sc, pack, spec)
            ctx = self.document_context(case, sc, pack, spec, addressee)
            docx = render_docx(pack.packs_root / spec.template, ctx,
                               ai_label=pack.localized(pack.manifest.compliance.ai_label, lang),
                               draft_disclaimer=pack.localized(pack.manifest.compliance.draft_disclaimer, lang)
                               if sc.is_draft else None, finish=self._finishing(case, sc, pack),
                               style=self.doc_style(pack), lang=lang, drop_empty=self._drop_empty(pack, lang))
            problems = self.check_document(case, sc, pack, ctx, addressee, docx)
            if problems:  # the desk sees what is still wrong in a document made again (PM 02.10)
                self.audit(session, case, "admin", "document_check_failed", action=spec.id,
                           problems=[f"{p.kind}: {p.detail}" for p in problems])
            action.addressee = addressee  # where «Отправить» sends it: never the client's own e-mail
            base = f"cases/{case.id}/actions/{action.sequence:02d}-{spec.id}"
            action.docx_key = self.storage.put(f"{base}.docx", docx,
                                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            pdf = None if self.defer_pdf else self.pdf.convert(docx)
            action.pdf_key = self.storage.put(f"{base}.pdf", pdf, "application/pdf") if pdf else None
            done += 1
        self.audit(session, case, "admin", "documents_rebuilt", count=done)
        return done

    def _applicant_name(self, case: Case, sc: Scenario) -> str:
        applicant = sc.parties.get("applicant")
        name = applicant.name_field if applicant is not None else None
        return str(case.facts.get(name) or "") if name else ""

    def prefill_blanks(self, session: Session, case: Case) -> list[str]:
        """Owner 01.10: «Данные собраны», yet the draft's fields were empty though the person had named the goods, the
        date and the sum. Before the draft is shown, its blanks are looked for once in everything the person told
        (the first message and the chat); only what is really not there stays blank. Once per story: the same text
        is never sent to the model twice."""
        if case.status not in (S.INTAKE.value, S.QUALIFIED.value) or not case.scenario_id:
            return []
        sc, pack = self.scenario_of(case), self.pack_of(case)
        blanks = self.draft_blanks(case, sc)
        if not blanks:
            return []
        said = [m.text for m in session.scalars(select(ChatMessage).where(
            ChatMessage.case_id == case.id, ChatMessage.role == "user").order_by(ChatMessage.created_at)).all()
            if m.text and m.text.strip() and m.text.strip() not in (case.initial_text or "")]
        story = "\n".join([case.initial_text or "", *said]).strip()
        mark = hashlib.sha256(story.encode()).hexdigest()[:16]  # the story read, not the blanks: they shrink
        taxonomy = dict(case.taxonomy or {})
        if len(story) < 15 or taxonomy.get("draft_prefill") == mark:
            return []
        llm = self.llm_for(case)
        before = set(case.facts)
        values = ai.extract_fields(llm, sc, pack, case.language, story, None, blanks)
        self._apply_values(case, sc, pack, values, llm, strict=False)
        self._save_vault(case, llm)
        case.taxonomy = {**taxonomy, "draft_prefill": mark}
        filled = sorted(set(case.facts) - before)
        if filled:
            self.audit(session, case, "system", "draft_prefilled", fields=filled)
        return filled

    def draft_blanks(self, case: Case, sc: Scenario) -> list[str]:
        """Required fields left blank for the draft («не помню», «пропустить», or past the question cap)."""
        skipped = set(case.skipped_fields or [])
        return [f.name for f in sc.intake if f.type != "evidence" and DRAFT + f.name in skipped
                and f.name not in case.facts]

    def _apply_values(self, case: Case, sc: Scenario, pack: JurisdictionPack, values: dict[str, Any],
                      llm: RedactingLLM | None, strict: bool, overwrite: bool = False) -> dict[str, str]:
        errors: dict[str, str] = {}
        facts = dict(case.facts)
        today = pack.local_now().date()
        # the postal addresses of the parties to a document (not a hotel or a university abroad)
        party_addresses = {p.address_field for p in sc.parties.values() if p.address_field}
        # the other side's contact is never the person's own (a receipt e-mailed to the client is not the seller's
        # e-mail — the first client's claim, 01.10)
        own = self._own_contacts(case, sc)
        other_side = {getattr(p, a) for k, p in sc.parties.items() if k != "applicant"
                      for a in ("email_field", "id_field", "address_field") if getattr(p, a, None)}
        # PM 02.10: «приобрёл в Тестов Тест Тестович» — the applicant's own name read as the seller's / landlord's
        mine = sc.parties.get("applicant")
        my_name = str(values.get(mine.name_field) or facts.get(mine.name_field) or "").strip().lower() \
            if mine is not None and mine.name_field else ""
        if case.owner is not None and case.owner.display_name:
            own = own | {case.owner.display_name.strip().lower()}
        if my_name:
            own = own | {my_name}
        other_side |= {p.name_field for k, p in sc.parties.items() if k != "applicant" and p.name_field}
        for name, raw in values.items():
            try:
                f = sc.field(name)
            except KeyError:
                continue
            if f.type == "evidence" or (name in facts and not overwrite):
                continue
            try:
                value = normalize(f, raw, today=today)
                if name in party_addresses and not looks_like_address(str(value)):
                    raise FieldError("address")  # QA BUG-10: a name or a BIN given instead of the postal address
                if name in other_side and str(value).strip().lower() in own:
                    if strict:  # typed by the person: say why it is not taken
                        raise FieldError("own")
                    continue  # silently dropped: the field stays empty (a blank in the draft)
                facts[name] = value
            except FieldError as e:
                errors[name] = e.code
                continue
            if f.pii and llm is not None:
                llm.vault.register(f.pii, facts[name])
            if name in (case.skipped_fields or []) or DRAFT + name in (case.skipped_fields or []):
                case.skipped_fields = [s for s in case.skipped_fields if s not in (name, DRAFT + name)]
        case.facts = facts
        if sc.claim and sc.claim.amount_field and sc.claim.amount_field in facts:
            case.amount_at_stake = Decimal(str(facts[sc.claim.amount_field]))
        if facts.get("claim_amount"):  # "how much you are owed", when it differs from what was paid
            case.amount_at_stake = Decimal(str(facts["claim_amount"]))
        return errors if strict else {}

    def question_for(self, sc: Scenario, pack: JurisdictionPack, lang: str, name: str) -> Question:
        f = sc.field(name)
        text = pack.localized(f.question, lang) if f.question else pack.t(
            lang, f"fields.{name}.question", default=ai.field_label(sc, pack, lang, name))
        kinds = [{"kind": k, "label": pack.t(lang, f"evidence.{k}", default=k)} for k in f.evidence_kinds]
        return Question(field=name, text=text, type=f.type, optional=f.optional, evidence_kinds=kinds,
                        pattern=f.pattern)

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
        cap = self.config.intake_max_questions
        in_bot = getattr(case.owner, "channel", None) == "telegram"
        if cap < 0 and in_bot:
            cap = 4
        if missing and (cap < 0 or (cap and int((case.taxonomy or {}).get("asked", 0)) >= cap)):
            # PM 01.10: the draft after a few questions; what is still unknown stays a blank filled in the draft
            case.skipped_fields = [*(case.skipped_fields or []),
                                   *(DRAFT + n for n in missing if not sc.field(n).optional)]
            missing = []
        if missing:
            case.pending_field = missing[0]
            q = self.question_for(sc, pack, lang, missing[0])
            return Reply(message=q.text, question=q)
        case.pending_field = None
        if case.status == S.INTAKE.value:
            self._sync_parties_and_claim(session, case, sc, pack)
            self.transition(session, case, S.QUALIFIED, "system")
        message = pack.t(lang, "interview.done", summary=self.facts_summary(case, sc, pack))
        blanks = self.draft_blanks(case, sc)
        if blanks:
            labels = ", ".join(ai.field_label(sc, pack, lang, n) for n in blanks)
            message = pack.t(lang, "interview.done_blanks", blanks=labels, default=message)
        return Reply(message=message, intake_complete=True)

    def _count_question(self, case: Case, f: Any) -> None:
        if f.type != "evidence":
            case.taxonomy = {**(case.taxonomy or {}), "asked": int((case.taxonomy or {}).get("asked", 0)) + 1}

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
                self._count_question(case, f)
                if not f.optional and f.type != "evidence":
                    # «не помню» / «пропустить» on a required answer: never asked again and again (QA BUG-08) —
                    # it stays a blank the person fills in the draft before paying (PM 01.10)
                    case.skipped_fields = [*(case.skipped_fields or []), DRAFT + pending]
                    reply = self._next_step(session, case, sc, pack)
                    reply.message = f"{pack.t(lang, 'interview.left_blank')}\n\n{reply.message}".strip()
                    return reply
                if not f.optional:  # a required document: asked again with the reason
                    q = self.question_for(sc, pack, lang, pending)
                    return Reply(message=f"{pack.t(lang, 'interview.required')}\n{q.text}", question=q,
                                 error="required")
                case.skipped_fields = [*(case.skipped_fields or []), pending]
                return self._next_step(session, case, sc, pack)
            if f.type == "evidence":
                q = self.question_for(sc, pack, lang, pending)
                return Reply(message=f"{pack.t(lang, 'interview.upload_or_skip')}\n{q.text}", question=q)
            if f.pii or f.type == "longtext" or _reads_as_is(f, text, pack):
                # instant: personal data (never sent to the LLM), a story (other facts are taken from it in the
                # background) and any answer that already reads as the field (a name, a date, a sum, a BIN)
                values = {pending: text}
            else:  # «в прошлом месяце», «сто тысяч»: the model reads it
                values = ai.extract_fields(llm, sc, pack, lang, text, pending, self.missing_fields(case, sc))
                values.setdefault(pending, text)
            errors = self._apply_values(case, sc, pack, values, llm, strict=True)
            self._save_vault(case, llm)
            if pending not in errors:
                self._count_question(case, f)
                self.audit(session, case, "user", "answered", field=pending)  # typed by the person (the check's source)
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
        if ev not in case.evidence:  # loading the collection may already have picked up the new row
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
            self._read_evidence(case, self.scenario_of(case), self.pack_of(case), ev, data)
        self.audit(session, case, "user", "evidence_added", kind=ev.kind, filename=filename)
        return ev

    def _read_evidence(self, case: Case, sc: Scenario, pack: JurisdictionPack, ev: Evidence,
                       data: bytes | None = None) -> dict[str, Any]:
        """Read a document and put what it shows into the case's empty fields at once (no confirmation step):
        the person is only asked what the documents do not say. Scans and photos go to the model as files when
        EXTRACT_IMAGES_WITH_LLM is on. Returns the fields filled from this document."""
        if ev.kind == IDENTITY_KIND or ev.kind == "response":
            return {}
        llm = self.llm_for(case)
        attachments: tuple[Attachment, ...] = ()
        scan = ev.content_type.startswith("image/") or (ev.content_type == "application/pdf" and not ev.text)
        if scan and self.config.extract_images_with_llm:
            if data is None:
                data = self.storage.get(ev.storage_key)
            attachments = (Attachment(ev.content_type, data, ev.filename),)
        if not (ev.text or attachments):
            return {}
        kinds = [k for f in sc.intake if f.type == "evidence" for k in f.evidence_kinds if k != IDENTITY_KIND]
        facts, summary, kind = ai.extract_evidence(llm, sc, pack, case.language, ev.text, attachments, kinds)
        if ev.kind in ("other", "") and kinds:  # a file sent outside the documents question: file it by content
            ev.kind = kind if kind in kinds else kinds[0]
        valid: dict[str, Any] = {}
        today = pack.local_now().date()
        for name, raw in facts.items():
            try:
                valid[name] = normalize(sc.field(name), raw, today=today)
            except (FieldError, KeyError):
                continue
        ev.extracted_facts = valid
        before = dict(case.facts)
        self._apply_values(case, sc, pack, valid, llm, strict=False)
        ev.confirmed = True
        self._save_vault(case, llm)
        return {k: v for k, v in case.facts.items() if k not in before}

    def read_unread_evidence(self, case: Case, sc: Scenario, pack: JurisdictionPack) -> None:
        """Files uploaded before the case had a scenario are read once it has one."""
        for ev in case.evidence:
            if not ev.extracted_facts and not ev.confirmed:
                self._read_evidence(case, sc, pack, ev)

    def evidence_reply(self, session: Session, case: Case, ev: Evidence) -> Reply:
        """After a file: what was taken from it, then the next question (only what is still missing)."""
        if case.status != S.INTAKE.value or not case.scenario_id:
            return Reply(message="")
        sc, pack = self.scenario_of(case), self.pack_of(case)
        lang = case.language
        reply = self._next_step(session, case, sc, pack)
        # what the document gave; where it disagrees with what the case already has, say so (the case keeps its value)
        filled, differs = [], []
        for k, v in ev.extracted_facts.items():
            if k not in case.facts:
                continue
            label, doc = ai.field_label(sc, pack, lang, k), display(sc.field(k), v)
            if str(case.facts[k]) == str(v):
                filled.append(f"• {label}: {doc}")
            else:
                differs.append(pack.t(lang, "interview.evidence_differs", label=label, doc=doc,
                                      case=display(sc.field(k), case.facts[k]),
                                      default=f"• {label}: в документе {doc}, в деле {display(sc.field(k), case.facts[k])}"))
        head = pack.t(lang, "interview.evidence_read", name=ev.filename or "",
                      default="Прочитал документ «{name}». Взял из него:").replace("{name}", ev.filename or "")
        q = reply.question
        kinds = {k["kind"] for k in q.evidence_kinds} if q and q.type == "evidence" else set()
        if ev.kind in kinds:
            q.uploaded = sum(1 for e in case.evidence if e.kind in kinds)
        if differs:
            filled += [pack.t(lang, "interview.evidence_differs_head", default="Расходится с тем, что уже записано:")]
            filled += differs
        parts = [head + "\n" + "\n".join(filled)] if filled else [
            pack.t(lang, "interview.evidence_added", n=str(sum(1 for e in case.evidence if e.kind != "response")))]
        reply.message = "\n\n".join(parts + [reply.message]).strip()
        return reply

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
        forum = self.action_forum(case, spec)
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
        if spec.package:  # service scenario: the personal checklist of the package
            fmt = self.document_context(case, sc, pack, spec, addressee)["fmt"]
            attachments = package.checklist(spec, lang, pack.manifest.default_language, case.facts,
                                            case.skipped_fields or [], fmt)
        for f in sc.intake:  # the evidence the interview asks for
            if f.type == "evidence":
                attachments += [pack.t(lang, f"evidence.{k}", default=k) for k in f.evidence_kinds if k != "other"]
        seen: set[str] = set()
        attachments = [a for a in attachments if not (a in seen or seen.add(a))]
        return {"document": pack.localized(spec.title, lang),
                "addressee": addressee.get("name") or None,
                "channels": channels, "attachments": attachments,
                "lawyer_check": self.approval_required(session, case, spec)}

    def action_forum(self, case: Case, spec: ActionSpec) -> Any:
        """The registry forum an action goes to: its addressee forum, or — for a universal-path claim to the other
        party itself — the forum the generic scenario was built for. None for signed scenarios' own addressees."""
        cov = self.pack_of(case).coverage
        if cov is None:
            return None
        if spec.addressee and spec.addressee.forum:
            return cov.forums.get(spec.addressee.forum)
        if is_generic(case.scenario_id):
            ref = GenericRef.parse(case.scenario_id or "")
            return cov.forums.get(ref.forum_id) if ref else None
        return None

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
        # BUG-20 (QA run 5, 01.10): low qualification confidence (needs_review) no longer holds a pre-trial document
        # — when the model is out of quota, the keyword fallback caps confidence at 0.55 and every paid claim went to
        # the owner. The owner's rule (30.09): the manual check is for court documents only; needs_review still
        # shows the case to the owner in /ops.
        if self.config.self_service and case.hold_reason is None:
            if not is_generic(case.scenario_id):
                # level-1 scenarios: pre-trial documents go out directly; a lawsuit to a court
                # (e.g. kz.family.alimony) is filed only after a lawyer's check, as on the universal path
                return spec is not None and self._to_court(case, spec)
            if spec is not None and self.document_type(case, spec) in self.config.self_service_documents \
                    and not self._to_court(case, spec):
                return False
            return True  # court documents (lawsuit, appeal) are filed only after a lawyer's check
        if case.needs_review or case.coverage_level == qualifier.LEVEL_UNIVERSAL or is_generic(case.scenario_id):
            return True
        rank = session.scalar(select(func.count()).select_from(Case).where(
            Case.scenario_id == case.scenario_id, Case.created_at <= case.created_at))
        return (rank or 0) <= self.config.approval_required_first_n

    def subject_mismatch(self, case: Case) -> str | None:
        """PM 02.10 (QA BUG-24): the subject the person's words decide (routing.direct) must be the case's — a flood never
        gets a «poor service» document, a tour never an air-ticket one, a debt never a purchase. Returns the right
        scenario or dispute when the case has another one, else None."""
        pack = self.pack_of(case)
        text = " ".join(str(x) for x in (case.initial_text, (case.facts or {}).get("problem_description")) if x)
        rule = safety.direct_dispute(pack.coverage, text) if pack.coverage is not None else None
        if rule is None or not case.scenario_id:
            return None
        if case.scenario_id == rule.scenario:
            return None
        if (case.taxonomy or {}).get("dispute_id") == rule.dispute and ".generic." in case.scenario_id:
            return None
        return rule.scenario or rule.dispute

    def check_subject(self, case: Case) -> None:
        right = self.subject_mismatch(case)
        if right is not None:
            raise EngineError("subject_mismatch", f"the case is about {right}, not {case.scenario_id}")

    def prepare_next_action(self, session: Session, case: Case, actor: str) -> Action:
        if not case.scenario_id:
            raise EngineError("no_document_path")
        self.lock(session, case)
        sc, pack = self.scenario_of(case), self.pack_of(case)
        self.check_subject(case)
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
        # a document is prepared only once something pays for it: the case plan, a subscription or a paid document
        via = None
        if spec.kind != "handoff":
            via = self.unlock_source(session, case)
            if via is None and self.payments.method == "stub":  # tests, development: one document, paid at once
                self.create_invoice(session, user_id=case.owner_id, purpose="document", case=case, actor=actor)
                via = self.unlock_source(session, case)
            if via is None:
                raise EngineError("payment_required" if self.payments.available() else "payment_unavailable")
        if status == S.AWAITING_RESPONSE:
            self.transition(session, case, S.ESCALATED, actor, reason=case.actions[-1].response_class)
        action = Action(case_id=case.id, sequence=len(case.actions) + 1, action_id=spec.id, kind=spec.kind,
                        channel=spec.channel, is_draft_scenario=sc.is_draft)
        session.add(action)
        case.actions.append(action)
        if via is not None:
            action.unlocked_by = via
            if via == "credit":
                case.doc_credits -= 1
            elif via == "bonus":
                session.get(User, case.owner_id).bonus_documents -= 1
        if spec.kind == "handoff":
            action.status = "done"
            self.transition(session, case, S.HANDED_TO_LAWYER, actor, action=spec.id)
            self.notifier.notify(session, case, "handoff", pack.t(case.language, "notifications.handoff"))
            return action
        return self._render_action(session, case, sc, pack, spec, action, actor)

    # ================================================================ payment
    OPEN = ("pending", "awaiting_confirmation", "not_found")
    KASPI_WAYS = ("kaspi_link", "kaspi_qr")  # paid into the company's Kaspi Pay: its push confirms them
    UNPAID_AFTER = timedelta(minutes=15)  # «Оплатить» pressed, no Kaspi Pay push since: remind once, stop new bills

    def unpaid_kaspi_bill(self, session: Session, user_id: uuid.UUID, now: datetime | None = None) -> Invoice | None:
        """The person's Kaspi link / QR bill they pressed «Оплатить» for at least UNPAID_AFTER ago that no Kaspi Pay
        push (nor the desk) confirmed — while it is open the person gets no new bill (owner 01.10: «при неоплате —
        напоминание и стоп на новые документы»). Only while the pushes are on: without them the desk confirms by
        hand and a slow desk must not stop anyone."""
        if not self.config.kaspi_push:
            return None
        now = now or utcnow()
        return session.scalar(select(Invoice).where(
            Invoice.user_id == user_id, Invoice.status.in_(("awaiting_confirmation", "not_found")),
            Invoice.pay_way.in_(self.KASPI_WAYS), Invoice.claimed_at.is_not(None),
            Invoice.claimed_at <= now - self.UNPAID_AFTER).order_by(Invoice.id).limit(1))

    def _stop_if_unpaid(self, session: Session, user_id: uuid.UUID, but: Invoice | None = None) -> None:
        debt = self.unpaid_kaspi_bill(session, user_id)
        if debt is None or (but is not None and debt.id == but.id):
            return
        from .bill import BillWords

        amount = f"{Decimal(debt.amount):,.0f}".replace(",", " ")
        sign = BillWords.of(self.billing_pack(session, debt), debt.currency).sign
        raise EngineError("unpaid_invoice", f"Сначала оплатите предыдущий счёт {debt.code} на {amount} {sign} по "
                                            f"ссылке Kaspi Pay — мы пока не видим этот платёж. Если вы уже "
                                            f"оплатили, напишите в поддержку.")

    def price(self, case: Case) -> tuple[Decimal, str | None] | None:
        """What one document of the case costs (scenario price); None when the case's documents are free."""
        if not case.scenario_id:
            return None
        sc, pack = self.scenario_of(case), self.pack_of(case)
        if sc.pricing.model != "fixed" or not sc.pricing.amount or sc.pricing.amount <= 0:
            return None
        return Decimal(str(sc.pricing.amount)), sc.pricing.currency or pack.currency

    def plan_currency(self) -> str | None:
        """Currency of subscription bills: PLAN_CURRENCY, else the pack's (plans are sold where one pack runs)."""
        if self.config.plan_currency:
            return self.config.plan_currency
        pack = next(iter(self.packs.packs.values()), None)
        return pack.currency if pack is not None else None

    def active_subscription(self, session: Session, user_id: uuid.UUID) -> tuple[Subscription, int] | None:
        """The user's current «Бизнес» period with documents left, and how many are left."""
        now = utcnow()
        for sub in session.scalars(select(Subscription).where(
                Subscription.user_id == user_id, Subscription.starts_at <= now, Subscription.ends_at > now)
                .order_by(Subscription.ends_at)).all():
            used = session.scalar(select(func.count()).select_from(Action)
                                  .where(Action.unlocked_by == f"subscription:{sub.id}")) or 0
            if used < sub.documents:
                return sub, sub.documents - used
        return None

    def unlock_source(self, session: Session, case: Case) -> str | None:
        """What will pay for the next document of the case, or None when payment is needed first."""
        if self.price(case) is None:
            return "free"
        if self.in_debt(session, case.owner_id):
            return None  # a payment given on trust was not found: no new document until it is paid
        if case.paid:
            return "case"
        active = self.active_subscription(session, case.owner_id)
        if active is not None:
            return f"subscription:{active[0].id}"
        # a paid document of this case goes first: the referral bonus is kept, as it serves any case
        if case.doc_credits > 0:
            return "credit"
        if self.bonus_documents(session, case.owner_id) > 0:
            return "bonus"
        return None

    def bonus_documents(self, session: Session, user_id: uuid.UUID) -> int:
        owner = session.get(User, user_id)
        return owner.bonus_documents if owner is not None else 0

    def document_unlocked(self, case: Case, action: Action) -> bool:
        return case.paid or action.unlocked_by is not None or self.price(case) is None

    def invoice_of(self, session: Session, case: Case) -> Invoice | None:
        """The case's open document bill (a document or «Дело под ключ», not paid yet), if any. A lawyer bill
        (purpose lawyer, core/lawyer_pilot.py) lives beside it and never replaces or cancels it."""
        return session.scalar(select(Invoice).where(Invoice.case_id == case.id, Invoice.status.in_(self.OPEN),
                                                    Invoice.purpose.in_(("document", "case")))
                              .order_by(Invoice.id.desc()).limit(1))

    def plan_invoice_of(self, session: Session, user_id: uuid.UUID) -> Invoice | None:
        return session.scalar(select(Invoice).where(Invoice.user_id == user_id, Invoice.purpose == "plan",
                                                    Invoice.status.in_(self.OPEN)).order_by(Invoice.id.desc()).limit(1))

    def create_invoice(self, session: Session, *, user_id: uuid.UUID, purpose: str, case: Case | None = None,
                       plan: str | None = None, actor: str = "system") -> Invoice:
        """A bill for one document or the whole case (purpose document | case) or a subscription (plan). An open
        bill of the same kind is reused; an unclaimed bill of another kind for the same case is cancelled."""
        if case is not None and purpose in ("document", "case"):
            self.check_subject(case)  # never a bill for a document of another subject (PM 02.10)
        if purpose == "plan":
            if plan not in self.config.plans:
                raise EngineError("unknown_plan")
            amount, currency = Decimal(self.config.plans[plan][0]), self.plan_currency()
            open_inv = self.plan_invoice_of(session, user_id)
        else:
            if case is None or purpose not in ("document", "case"):
                raise EngineError("unknown_purpose")
            price = self.price(case)
            if price is None:
                raise EngineError("free")
            if purpose == "case" and case.paid:
                raise EngineError("already_paid")
            amount = price[0] if purpose == "document" else Decimal(self.config.case_price)
            currency = price[1]
            open_inv = self.invoice_of(session, case)
        if open_inv is not None:
            if open_inv.purpose == purpose and open_inv.plan == plan:
                return open_inv
            if open_inv.status == "awaiting_confirmation":
                raise EngineError("invoice_awaiting_confirmation")
        self._stop_if_unpaid(session, user_id)
        if not self.payments.available():
            raise EngineError("payment_unavailable")
        if open_inv is not None:
            open_inv.status = "cancelled"
            self._return_bonus(session, open_inv)
        owner = session.get(User, user_id)
        points = self.bonus_for(owner, amount) if purpose != "plan" else 0
        bill = self.payments.create_invoice(case_id=str(case.id) if case else "", amount=amount - points,
                                            currency=currency)
        inv = Invoice(case_id=case.id if case else None, user_id=user_id, purpose=purpose, plan=plan, code=bill.id,
                      method=self.payments.method, amount=bill.amount, currency=bill.currency, status=bill.status,
                      bonus_used=points)
        if points:
            owner.bonus_balance -= points
        session.add(inv)
        session.flush()
        if case is not None:
            self.audit(session, case, actor, "invoice_created", invoice=inv.code, purpose=purpose,
                       status=inv.status, amount=str(inv.amount), currency=inv.currency, bonus_used=points)
        if bill.status == "paid":
            inv.decided_at = utcnow()
            self._apply_paid(session, inv)
        return inv

    def bonus_for(self, owner: User | None, amount: Decimal) -> int:
        """Bonus points that pay part of a bill of `amount`: the whole balance, at most referral_bonus_max_share of
        the bill (whole points). The rest is paid as usual."""
        if owner is None or owner.bonus_balance <= 0:
            return 0
        cap = int(amount * Decimal(str(self.config.referral_bonus_max_share)))
        return max(0, min(owner.bonus_balance, cap))

    def _return_bonus(self, session: Session, inv: Invoice) -> None:
        """A bill cancelled before it was paid gives its bonus points back."""
        if inv.bonus_used:
            owner = session.get(User, inv.user_id)
            if owner is not None:
                owner.bonus_balance += inv.bonus_used
            inv.bonus_used = 0

    def _apply_paid(self, session: Session, inv: Invoice) -> None:
        """What a paid bill gives: a document credit, the whole case, or a subscription period (and, for an invited
        person's first payment, the referral bonus). A lawyer bill puts the lawyer on the case and nothing else."""
        if inv.purpose == "lawyer":
            from . import lawyer_pilot

            lawyer_pilot.apply_paid(session, self, inv)
            return
        self._referral_bonus(session, inv)
        if inv.purpose == "plan":
            now = utcnow()
            latest = session.scalar(select(func.max(Subscription.ends_at)).where(
                Subscription.user_id == inv.user_id, Subscription.plan == inv.plan, Subscription.ends_at > now))
            if latest is not None and latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            start = max(now, latest) if latest is not None else now
            session.add(Subscription(user_id=inv.user_id, plan=inv.plan, documents=self.config.plans[inv.plan][1],
                                     starts_at=start, ends_at=start + timedelta(days=self.config.plan_days),
                                     invoice_id=inv.id))
            return
        case = session.get(Case, inv.case_id)
        if inv.purpose == "document":
            case.doc_credits += 1
        else:
            case.paid = True

    def _referral_bonus(self, session: Session, inv: Invoice) -> None:
        """The first payment of an invited person: one free document to them and one to whoever invited them. Once
        per invited person (referral_rewarded_at), whatever they paid for; both are told."""
        payer = session.get(User, inv.user_id)
        if payer is None or payer.referred_by is None or payer.referral_rewarded_at is not None:
            return
        payer.referral_rewarded_at = utcnow()
        inviter = session.get(User, payer.referred_by)
        if inviter is None or inviter.id == payer.id:
            return
        case = session.get(Case, inv.case_id) if inv.case_id is not None else None
        pack = self.pack_of(case) if case is not None else next(iter(self.packs.packs.values()), None)
        points = self.config.referral_bonus_points
        if points > 0:  # the bonus account: the invited person got theirs on joining (referral.attribute)
            inviter.bonus_balance += points
            if case is not None:
                self.audit(session, case, "system", "referral_bonus", invoice=inv.code, inviter=str(inviter.id),
                           points=points)
            default = (f"Человек, которого вы пригласили, оплатил документ. Спасибо! На ваш бонусный счёт начислено "
                       f"{points} бонусов.")
            text = (pack.t(pack.lang(inviter.language), "notifications.referral_points_inviter", default=default,
                           n=points) if pack else default)
            self.notifier.notify_user(session, inviter, "referral", text, case=None)
            return
        payer.bonus_documents += 1
        inviter.bonus_documents += 1
        if case is not None:
            self.audit(session, case, "system", "referral_bonus", invoice=inv.code, inviter=str(inviter.id))
        for user, key, default in (
                (payer, "referral_bonus_invited",
                 "Вы пришли по приглашению друга — дарим ещё один документ бесплатно."),
                (inviter, "referral_bonus_inviter",
                 "Человек, которого вы пригласили, оплатил документ. Дарим вам один документ бесплатно.")):
            text = pack.t(pack.lang(user.language), f"notifications.{key}", default=default) if pack else default
            self.notifier.notify_user(session, user, "referral", text, case=case if user is payer else None)

    def claim_payment(self, session: Session, inv: Invoice | None, actor: str) -> Invoice:
        """The person reports the transfer ("I have paid"): the clients desk is to check and confirm it."""
        if inv is None or inv.status not in self.OPEN:
            raise EngineError("no_open_invoice")
        if inv.status in ("pending", "not_found"):
            self._stop_if_unpaid(session, inv.user_id, but=inv)
            inv.status, inv.claimed_at = "awaiting_confirmation", utcnow()
            if inv.case_id is not None:
                self.audit(session, session.get(Case, inv.case_id), actor, "payment_claimed", invoice=inv.code)
            self._trust(session, inv, actor)
        return inv

    def in_debt(self, session: Session, user_id: uuid.UUID) -> bool:
        """A document was given on trust and the desk did not find its payment."""
        return session.scalar(select(Invoice.id).where(Invoice.user_id == user_id, Invoice.trusted_at.is_not(None),
                                                       Invoice.status == "not_found").limit(1)) is not None

    def _trust(self, session: Session, inv: Invoice, actor: str) -> None:
        """Owner 01.10 «вернулся — сразу получил документ»: «Оплатить» with the Kaspi Pay link gives the document at
        once; the bill stays «ждёт сверки» in /ops and the desk matches it by amount and time. Once per bill, never
        for a person who owes a document already, never for a subscription or a lawyer bill."""
        trusted_way = self.config.trust_all or (self.config.trust_kaspi_link and inv.pay_way == "kaspi_link")
        if (not trusted_way or inv.trusted_at is not None
                or inv.purpose not in ("document", "case") or inv.case_id is None
                or self.in_debt(session, inv.user_id)):
            return
        inv.trusted_at = utcnow()
        case = session.get(Case, inv.case_id)
        if inv.purpose == "document":
            case.doc_credits += 1
        else:
            case.paid = True
        self.audit(session, case, actor, "payment_trusted", invoice=inv.code)

    def billing_pack(self, session: Session, inv: Invoice) -> JurisdictionPack | None:
        """The pack whose country words a bill uses: the case's, else the one pack plans are sold in."""
        case = session.get(Case, inv.case_id) if inv.case_id is not None else None
        if case is not None and case.scenario_id:
            return self.pack_of(case)
        return next(iter(self.packs.packs.values()), None)

    def way_view(self, inv: Invoice | None) -> dict[str, Any]:
        """The way the person chose for this bill and what they gave for it."""
        if inv is None:
            return {"way": None, "payer_phone": None, "buyer": None}
        buyer = ({"name": inv.buyer_name, "bin": inv.buyer_bin, "address": inv.buyer_address}
                 if inv.buyer_name else None)
        return {"way": inv.pay_way, "payer_phone": inv.payer_phone, "buyer": buyer}

    def choose_way(self, session: Session, inv: Invoice | None, way: str, actor: str, *, phone: str | None = None,
                   buyer_name: str | None = None, buyer_bin: str | None = None,
                   buyer_address: str | None = None) -> Invoice:
        """The person picks how to pay the open bill (adapters/payment.py WAYS). kaspi_invoice: the Kaspi number to
        bill — the request goes to the clients desk at once (awaiting_confirmation), which sends the Kaspi bill and
        confirms the payment. bank_invoice: the paying company's name and tax number for «Счёт на оплату»."""
        from .adapters.payment import kz_phone, valid_bin

        if inv is None or inv.status not in self.OPEN:
            raise EngineError("no_open_invoice")
        if inv.purpose == "lawyer":  # the company's channel only, shown with the bill (core/lawyer_pilot.py)
            raise EngineError("way_unavailable")
        if not self.payments.way_available(way):
            raise EngineError("way_unavailable")
        if inv.status == "awaiting_confirmation" and way != inv.pay_way:
            raise EngineError("invoice_awaiting_confirmation")
        if way == "kaspi_invoice":
            number = kz_phone(phone)
            if number is None:
                raise EngineError("invalid_phone")
            inv.payer_phone = number
        if way == "bank_invoice":
            name, bin_ = (buyer_name or "").strip(), valid_bin(buyer_bin)
            if len(name) < 3 or len(name) > 300:
                raise EngineError("invalid_buyer")
            if bin_ is None:
                raise EngineError("invalid_bin")
            inv.buyer_name, inv.buyer_bin = name, bin_
            inv.buyer_address = (buyer_address or "").strip()[:300] or None
        inv.pay_way = way
        case = session.get(Case, inv.case_id) if inv.case_id is not None else None
        if case is not None:
            self.audit(session, case, actor, "payment_way", invoice=inv.code, way=way)
        if way == "kaspi_invoice":
            self.claim_payment(session, inv, actor)
        return inv

    def decide_payment(self, session: Session, inv: Invoice, operator: str, received: bool,
                       note: str | None = None) -> None:
        """The clients desk found the transfer (→ paid) or did not (→ not_found); the person is told either way."""
        if inv.status == "paid":
            raise EngineError("already_paid")
        if inv.status == "cancelled":
            raise EngineError("cancelled")
        inv.status = "paid" if received else "not_found"
        inv.decided_at, inv.decided_by = utcnow(), operator
        if note is not None:
            inv.desk_note = note
        if received and inv.trusted_at is not None:
            self._referral_bonus(session, inv)  # the document was given at «Оплатить»
        elif received:
            self._apply_paid(session, inv)
        elif inv.trusted_at is not None and inv.case_id is not None:
            # not found: what the bill gave and is not used yet goes back; the person owes it (in_debt)
            owed = session.get(Case, inv.case_id)
            if inv.purpose == "case":
                owed.paid = False
            elif owed.doc_credits > 0:
                owed.doc_credits -= 1
        if inv.case_id is None:  # a subscription: the desk's e-mail tells the person
            return
        case = session.get(Case, inv.case_id)
        pack = self.pack_of(case)
        lang = pack.lang(case.language)
        if inv.purpose == "lawyer" and received:  # lawyer_pilot.apply_paid told the client and the lawyer
            self.audit(session, case, f"ops:{operator}", "payment_confirmed", invoice=inv.code)
            return
        if received:
            text = pack.t(lang, "notifications.payment_confirmed",
                          default="Оплата получена. Документ можно подготовить и скачать в карточке дела.")
        elif inv.trusted_at is not None:
            text = pack.t(lang, "notifications.payment_owed",
                          default="Мы не нашли вашу оплату документа в Kaspi. Пожалуйста, оплатите документ в карточке дела — "
                                  "новые документы будут доступны после оплаты.")
        else:
            text = pack.t(lang, "notifications.payment_not_found", code=inv.code,
                          default=f"Перевод с кодом {inv.code} не найден. Проверьте сумму и комментарий к переводу "
                                  f"и нажмите «Оплатить» ещё раз или напишите в поддержку.")
        self.audit(session, case, f"ops:{operator}", "payment_confirmed" if received else "payment_not_found",
                   invoice=inv.code)
        self.notifier.notify(session, case, "payment", text, sms="payment_confirmed" if received else None)

    def prepare_paid_documents(self, session: Session, now: datetime, *, after: timedelta = timedelta(seconds=90),
                               within: timedelta = timedelta(days=2)) -> int:
        """Scheduler job: once the desk confirms a transfer, the document is prepared without the person pressing
        the button again. The page does it at once while it is open; this picks up the rest after ``after``."""
        done = 0
        paid = session.scalars(select(Invoice).where(
            Invoice.status == "paid", Invoice.case_id.is_not(None), Invoice.purpose.in_(("document", "case")),
            Invoice.decided_at.is_not(None), Invoice.decided_at <= now - after, Invoice.decided_at >= now - within))
        for inv in paid.all():
            try:
                with session.begin_nested():
                    done += self.prepare_after_payment(session, inv) is not None
            except Exception:  # noqa: BLE001 — retried on the next tick
                log.exception("auto-prepare after payment %s failed", inv.code)
        return done

    def prepare_after_payment(self, session: Session, inv: Invoice) -> Action | None:
        """The document a confirmed payment is for, when it is not prepared yet (the desk's confirmation starts this
        at once; the scheduler retries). None when there is nothing to prepare."""
        case = session.get(Case, inv.case_id) if inv.case_id else None
        if inv.status != "paid" or inv.decided_at is None or case is None:
            return None
        self.lock(session, case)
        decided = inv.decided_at if inv.decided_at.tzinfo else inv.decided_at.replace(tzinfo=timezone.utc)
        if case.status != S.QUALIFIED.value or case.hold_reason is not None:
            return None
        if any((a.created_at if a.created_at.tzinfo else a.created_at.replace(tzinfo=timezone.utc)) >= decided
               for a in case.actions):
            return None  # already prepared after this payment
        if self.unlock_source(session, case) is None:
            return None
        action = self.prepare_next_action(session, case, "system:paid")
        pack = self.pack_of(case)
        self.notifier.notify(session, case, "document", pack.t(
            pack.lang(case.language), "notifications.document_ready",
            default="Документ готов: его можно скачать в карточке дела."), sms="document_ready")
        log.info("document %s prepared after payment %s", action.id, inv.code)
        return action

    def lock(self, session: Session, case: Case) -> None:
        """Row lock on the case (PostgreSQL) so the page and the background job never make the same document
        twice; the case is re-read after waiting for the lock."""
        if session.get_bind().dialect.name != "postgresql":
            return
        session.execute(select(Case.id).where(Case.id == case.id).with_for_update())
        if case not in session.dirty:
            session.refresh(case)
            session.expire(case, ["actions"])

    def subscription_view(self, session: Session, user_id: uuid.UUID) -> dict[str, Any] | None:
        active = self.active_subscription(session, user_id)
        if active is None:
            return None
        sub, left = active
        return {"plan": sub.plan, "documents": sub.documents, "left": left, "ends_at": sub.ends_at.isoformat()}

    def invoice_details(self, inv: Invoice | None) -> dict[str, Any] | None:
        if inv is None:
            return None
        if inv.purpose == "lawyer":  # never the Kaspi Gold of the document bills
            from . import lawyer_pilot

            return lawyer_pilot.payment_view(None, self, inv)
        view = {"id": inv.id, "code": inv.code, "purpose": inv.purpose, "plan": inv.plan, "amount": float(inv.amount),
                "currency": inv.currency, "status": inv.status, "recipient_name": None, "kaspi_phone": None,
                "ways": [], **self.way_view(inv)}
        if inv.status in self.OPEN:
            view.update(self.payments.details())
        return view

    def document_title(self, case: Case) -> str | None:
        """«Услуга» in the payment window: the document the case makes next («Претензия продавцу о возврате денег»),
        not a bare «Документ» (PM 02.10)."""
        if not case.scenario_id:
            return None
        try:
            sc = self.scenario_of(case)
            spec = self.next_action_spec(case, sc)
            if spec is None:
                return None
            pack = self.pack_of(case)
            return pack.localized(spec.title, pack.lang(case.language)) or None
        except Exception:  # noqa: BLE001 — the window falls back to «Документ»
            log.warning("document title for case %s", case.id, exc_info=True)
            return None

    def payment_view(self, session: Session, case: Case) -> dict[str, Any] | None:
        """What the payment screen shows: whether the next document is paid for, what can be bought, the open bill
        and, while it is unpaid, where to transfer. status "paid" = the next document can be prepared now."""
        price = self.price(case)
        if price is None:
            return None
        inv = self.invoice_of(session, case)
        via = self.unlock_source(session, case)
        status = "paid" if via is not None else (inv.status if inv is not None else "none")
        view: dict[str, Any] = {
            "amount": float(inv.amount if inv is not None else price[0]), "currency": price[1], "status": status,
            "purpose": inv.purpose if inv is not None else None, "method": self.payments.method,
            "available": self.payments.available(), "code": inv.code if inv is not None else None,
            "invoice_id": inv.id if inv is not None else None, "recipient_name": None, "kaspi_phone": None,
            "ways": [], **self.way_view(inv),
            "options": [] if case.paid else [
                {"purpose": "document", "amount": float(price[0])},
                {"purpose": "case", "amount": float(self.config.case_price)}],
            "case_paid": case.paid, "credits": case.doc_credits,
            "trusted": inv is not None and inv.trusted_at is not None, "owed": self.in_debt(session, case.owner_id),
            "bonus": self.bonus_documents(session, case.owner_id),
            "bonus_balance": (owner.bonus_balance if (owner := session.get(User, case.owner_id)) else 0),
            "bonus_used": inv.bonus_used if inv is not None else 0,
            "subscription": self.subscription_view(session, case.owner_id),
            "title": self.document_title(case)}
        if inv is not None and status != "paid":
            view.update(self.payments.details())
        # «status» is about the NEXT document; the last paid bill is shown apart (QA 01.10: «Оплачено» after the
        # document was given, not «none»)
        last = session.scalar(select(Invoice).where(Invoice.case_id == case.id, Invoice.status == "paid",
                                                    Invoice.purpose.in_(("document", "case")))
                              .order_by(Invoice.id.desc()).limit(1))
        view["last_paid"] = {"code": last.code, "amount": float(last.amount), "purpose": last.purpose,
                             "paid_at": last.decided_at.isoformat() if last.decided_at else None} if last else None
        return view

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
        if spec.addressee.name:  # service scenario: a named recipient (visa centre, university, customer…)
            return {"kind": "organization", "key": None, "name": pack.localized(spec.addressee.name, lang),
                    "address": "", "email": None, "submit_url": spec.addressee.url, "id": None}
        if spec.addressee.authority:
            auth = pack.manifest.authorities[spec.addressee.authority]
            return {"kind": "authority", "key": spec.addressee.authority, "name": pack.localized(auth.name, lang),
                    "address": pack.localized(auth.address, lang) if auth.address else "",
                    "email": auth.email, "submit_url": auth.submit_url, "id": None}
        party = sc.parties[spec.addressee.party]
        get = lambda attr: case.facts.get(getattr(party, attr)) if getattr(party, attr) else None  # noqa: E731
        name, email, address = get("name_field") or "", get("email_field"), get("address_field") or ""
        if spec.addressee.party != "applicant":
            # owner 01.10: never the person's own contact as the other side's, never a description as an address
            if email and str(email).strip().lower() in self._own_contacts(case, sc):
                email = None
            address = polish.tidy_address(address) if looks_like_address(str(address)) else ""
            name = polish.tidy_name(str(name))
        out = {"kind": party.kind, "key": spec.addressee.party, "name": name,
               "id": get("id_field"), "email": email, "address": address, "submit_url": None}
        if spec.addressee.heading:
            out["heading"] = pack.localized(spec.addressee.heading, lang).replace("{name}", str(name or "")).strip()
        return out

    def applicant_gender(self, case: Case, sc: Scenario, pack: JurisdictionPack) -> str:
        """From the name (patronymic, surname), else from the id number where the pack says how it tells."""
        gender = _grammatical_gender(self._applicant_name(case, sc))
        rule = pack.manifest.id_number_sex
        applicant = sc.parties.get("applicant")
        if gender == "unknown" and rule and applicant is not None and applicant.id_field:
            gender = polish.gender_from_id(str(case.facts.get(applicant.id_field) or ""), rule.position, rule.male,
                                           rule.female)
        return gender

    @staticmethod
    def doc_style(pack: JurisdictionPack) -> DocStyle:
        """The pack's official layout (document_style), over the defaults; unknown keys are ignored."""
        known = DocStyle.__dataclass_fields__
        return DocStyle(**{k: v for k, v in (pack.manifest.document_style or {}).items() if k in known})

    def _finishing(self, case: Case, sc: Scenario, pack: JurisdictionPack) -> Any:
        """The last pass over the document's text: gendered forms in brackets resolved for the applicant, amounts
        with the currency sign and in words (owner 01.10)."""
        lang = case.language
        gender = self.applicant_gender(case, sc, pack)
        code = case.currency or pack.currency
        symbol = pack.t(lang, f"currency_symbol.{code}", default=code)
        word = pack.t(lang, f"currency_word.{code}", default="")

        def finish(text: str) -> str:
            return polish.amounts_in_words(polish.gender_forms(text, gender), code, symbol, word, lang)
        return finish

    def _render_action(self, session: Session, case: Case, sc: Scenario, pack: JurisdictionPack,
                       spec: ActionSpec, action: Action, actor: str) -> Action:
        lang = case.language
        title = pack.localized(spec.title, lang)
        addressee = self._addressee(case, sc, pack, spec)
        self._ensure_text(case, sc, pack, title)
        ctx = self.document_context(case, sc, pack, spec, addressee)
        docx = render_docx(pack.packs_root / spec.template, ctx,
                           ai_label=pack.localized(pack.manifest.compliance.ai_label, lang),
                           draft_disclaimer=pack.localized(pack.manifest.compliance.draft_disclaimer, lang)
                           if sc.is_draft else None, finish=self._finishing(case, sc, pack), style=self.doc_style(pack),
                           lang=lang, drop_empty=self._drop_empty(pack, lang))
        problems = self.check_document(case, sc, pack, ctx, addressee, docx)
        lawyer_only = [p for p in problems if not p.client_can_fix]
        if problems and problems[0].client_can_fix:
            # the client fixes it first: one field, asked before the document is made (nothing is stored)
            raise EngineError("document_check", problems[0].detail, fields=[problems[0].field])
        base = f"cases/{case.id}/actions/{action.sequence:02d}-{spec.id}"
        action.docx_key = self.storage.put(f"{base}.docx", docx,
                                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        pdf = None if self.defer_pdf else self.pdf.convert(docx)
        action.pdf_key = self.storage.put(f"{base}.pdf", pdf, "application/pdf") if pdf else None
        return self._finish_action(session, case, sc, pack, spec, action, actor, addressee, ctx, bool(pdf),
                                   checked=lawyer_only)

    def _told(self, case: Case, sc: Scenario) -> tuple[dict[str, tuple[str, Any]], str, set[str]]:
        """What the check holds the document's names, sums and dates against (PM 02.10: nothing made up): the values,
        everything the person said or uploaded, and the fields they typed themselves."""
        from sqlalchemy.orm import object_session

        session = object_session(case)
        parties = {p.name_field for role, p in sc.parties.items() if role != "applicant" and p.name_field}
        values = {f.name: (f.type if f.type in ("money", "date") else "name", case.facts.get(f.name)) for f in sc.intake
                  if (f.type in ("money", "date") or f.name in parties) and not f.pii}
        said = [case.initial_text or ""]
        typed: set[str] = set()
        if session is not None:
            said += [m for m in session.scalars(select(ChatMessage.text).where(
                ChatMessage.case_id == case.id, ChatMessage.role == "user")).all() if m]
            for row in session.scalars(select(AuditLog).where(
                    AuditLog.case_id == case.id, AuditLog.event.in_(("answered", "draft_filled", "facts_corrected")))):
                data = row.data or {}
                typed |= set(data.get("fields") or []) | ({data["field"]} if data.get("field") else set())
        for e in case.evidence:
            said += [e.text or "", " ".join(str(v) for v in (e.extracted_facts or {}).values())]
        return values, "\n".join(said), typed

    @staticmethod
    def _drop_empty(pack: JurisdictionPack, lang: str) -> tuple[str, ...]:
        routing = pack.coverage.routing if pack.coverage else None
        return tuple((routing.document_drop_empty if routing else {}).get(lang, ()))

    def check_document(self, case: Case, sc: Scenario, pack: JurisdictionPack, ctx: dict[str, Any],
                       addressee: dict[str, Any], docx: bytes) -> list[docgate.Problem]:
        """PM 02.10 (owner: «грубые ошибки в документах»): the finished text, before it is stored — core/docgate.py."""
        routing = pack.coverage.routing if pack.coverage else None
        marks = routing.document_markers if routing else {}
        words = tuple(marks.get(case.language, ())) + tuple(marks.get("*", ()))
        norms = tuple((routing.norm_words if routing else {}).get(case.language, ()))
        roles = {role: ctx.get(role) or {} for role in ("applicant", "respondent") if role in sc.parties}
        fields = {role: {"name": p.name_field} for role, p in sc.parties.items() if p.name_field}
        required = {f.name: case.facts.get(f.name) for f in sc.intake if f.type in ("money", "date") and not f.optional}
        told = self._told(case, sc)
        return docgate.check(docx_text(docx), words=words, norm_words=norms, told=told, addressee=addressee, parties=roles, fields=fields,
                             required=required)

    def _ensure_text(self, case: Case, sc: Scenario, pack: JurisdictionPack, title: str) -> None:
        """The written parts of the document (statement of circumstances, demands): the slow LLM step. Kept on the
        case, so it can be written ahead (prewrite) while the person pays."""
        lang = case.language
        llm = self.llm_for(case)
        if not case.narrative:
            # the narrative needs no personal data: names/ids are printed in the header by the template
            facts = {fl.name: display(fl, case.facts[fl.name]) for fl in sc.intake
                     if fl.name in case.facts and fl.type != "evidence" and not fl.pii}
            attached = sorted({pack.t(lang, f"evidence.{e.kind}", default=e.kind) for e in case.evidence
                               if e.kind not in ("response", IDENTITY_KIND)})
            if sc.kind == "service":  # the person's own story for a cover / motivation letter
                case.narrative = ai.write_letter(llm, sc, pack, lang, facts, title)
            else:
                currency = pack.t(lang, f"currency_word.{case.currency or pack.currency}",
                                  default=case.currency or pack.currency)
                case.narrative = ai.write_narrative(llm, sc, pack, lang, facts, title, attached,
                                                    gender=self.applicant_gender(case, sc, pack),
                                                    currency=currency)
            self._save_vault(case, llm)
        if is_generic(sc.id) and not case.formal_demands and case.facts.get("desired_outcome"):
            claim = case.facts.get("claim_amount") or case.facts.get("amount")
            case.formal_demands = ai.write_demands(llm, pack, lang, str(case.facts["desired_outcome"]), title,
                                                   amount=f"{claim} {case.currency or pack.currency}" if claim else None)
            self._save_vault(case, llm)

    def prewrite(self, session: Session, case: Case) -> bool:
        """Write the next document's text ahead, while the person pays: after payment only the file is made."""
        if not case.scenario_id or case.status != S.QUALIFIED.value or case.hold_reason is not None:
            return False
        sc, pack = self.scenario_of(case), self.pack_of(case)
        spec = self.next_action_spec(case, sc)
        if spec is None or spec.kind == "handoff" or (case.narrative and not (
                is_generic(sc.id) and not case.formal_demands and case.facts.get("desired_outcome"))):
            return False
        self._ensure_text(case, sc, pack, pack.localized(spec.title, case.language))
        return True

    def ensure_pdf(self, session: Session, action: Action) -> bool:
        """The PDF of a document made without one (defer_pdf); True when there is one now."""
        if action.pdf_key:
            return True
        if not action.docx_key:
            return False
        pdf = self.pdf.convert(self.storage.get(action.docx_key))
        if not pdf:
            return False
        action.pdf_key = self.storage.put(action.docx_key.removesuffix(".docx") + ".pdf", pdf, "application/pdf")
        return True

    def _finish_action(self, session: Session, case: Case, sc: Scenario, pack: JurisdictionPack, spec: ActionSpec,
                       action: Action, actor: str, addressee: dict[str, Any], ctx: dict[str, Any],
                       pdf: bool, checked: list[docgate.Problem] | None = None) -> Action:
        lang = case.language
        action.addressee = addressee
        action.instructions = [
            _tidy(s.format_map(_Fmt(ctx["fmt"]))) for s in (spec.instructions.get(lang) or
                                                             spec.instructions.get(pack.manifest.default_language) or ())
        ]
        if checked:  # PM 02.10: what only a lawyer can fix («[рассчитает юрист]», a norm twice) — never to the client
            self.audit(session, case, "system", "document_check_failed", action=spec.id,
                       problems=[f"{p.kind}: {p.detail}" for p in checked])
        if checked or self.approval_required(session, case, spec):
            action.approval_status, action.status = "pending", "pending_approval"
            if self.on_approval_needed is not None:
                try:
                    self.on_approval_needed(session, case, action)
                except Exception:  # noqa: BLE001 — telling the lawyer must never stop the document
                    log.warning("approval notice for case %s failed", case.id, exc_info=True)
        else:
            action.approval_status, action.status = "not_required", "ready"
        if case.status != S.ACTION_READY.value:
            self.transition(session, case, S.ACTION_READY, actor, action=spec.id)
        self.audit(session, case, actor, "document_generated", action=spec.id,
                   approval=action.approval_status, pdf=pdf)
        return action

    def document_context(self, case: Case, sc: Scenario, pack: JurisdictionPack, spec: ActionSpec,
                         addressee: dict[str, Any], placeholders: bool = False) -> dict[str, Any]:
        lang = case.language
        f = {fl.name: display(fl, case.facts.get(fl.name)) for fl in sc.intake if fl.type != "evidence"}
        if placeholders:  # the draft: a blank shows what goes there («[Адрес продавца]»)
            for name in self.draft_blanks(case, sc):
                f[name] = f"[{ai.field_label(sc, pack, lang, name)}]"
        # requisites of every party (the header, "whose actions are complained of", the defendant of a lawsuit)
        parties = {role: {"name": f.get(p.name_field, ""), "id": f.get(p.id_field or "", ""),
                          "email": f.get(p.email_field or "", ""), "address": f.get(p.address_field or "", ""),
                          "kind": p.kind}
                   for role, p in sc.parties.items()}
        own = self._own_contacts(case, sc)
        for role, party in parties.items():  # owner 01.10: capitals, real addresses, nobody else's contacts
            party["name"] = polish.tidy_name(str(party["name"] or ""))
            address = str(party["address"] or "")
            if not address.startswith("["):  # a draft's blank («[Адрес продавца]») stays a blank
                party["address"] = polish.tidy_address(address) if role == "applicant" or looks_like_address(address) else ""
            if role != "applicant" and str(party["email"] or "").strip().lower() in own:
                party["email"] = ""
        applicant = parties.get("applicant", {})
        evidence = list(dict.fromkeys(  # the same file attached twice is listed once
            pack.t(lang, f"evidence.{e.kind}", default=e.kind) + (f" ({e.filename})" if e.filename else "")
            for e in case.evidence if e.kind != "response"))
        previous = [{"title": pack.localized(sc.action(a.action_id).title, lang),
                     # the filing day in the country's time (PM 02.10: after 19:00 UTC it is already tomorrow in Almaty)
                     "date": _aware(a.submitted_at).astimezone(pack.tz).strftime("%d.%m.%Y") if a.submitted_at else "",
                     "response": pack.t(lang, f"responses.{a.response_class}", default=a.response_class or "")}
                    for a in case.actions if a.action_id != spec.id and a.submitted_at]
        today = pack.local_now().date().strftime("%d.%m.%Y")
        fmt = {**f, "addressee": addressee.get("name", ""), "submit_url": addressee.get("submit_url") or "",
               "addressee_email": addressee.get("email") or "", "currency": case.currency or pack.currency,
               "today": today, "formal_demands": case.formal_demands or f.get("desired_outcome", "")}
        if spec.deadline:
            fmt["deadline_days"] = spec.deadline.calendar_days or spec.deadline.business_days
        demands = pack.localized(spec.demands, lang).format_map(_Fmt(fmt)) if spec.demands else ""
        if spec.deadline is not None and "в установленный законом срок" in demands:
            # P0 02.10: the term itself, not «в установленный законом срок»
            d = spec.deadline
            unit = "календарных" if d.calendar_days is not None else "рабочих"
            demands = demands.replace("в установленный законом срок",
                                      f"в течение {d.calendar_days or d.business_days} {unit} дней со дня получения")
        extra: dict[str, Any] = {}
        if spec.package:
            default = pack.manifest.default_language
            fmt_pkg = {**fmt, "narrative": case.narrative or f.get("problem_description", "")}
            extra = {"sections": package.sections(spec, lang, default, case.facts, case.skipped_fields or [], fmt_pkg),
                     "L": package.labels(lang, default), "sources": package.sources(sc, lang, default),
                     "disclaimer": pack.localized(sc.disclaimer, lang) if sc.disclaimer else "",
                     "scenario_title": pack.localized(sc.title, lang),
                     "id_label": ai.field_label(sc, pack, lang, sc.parties["applicant"].id_field)
                     if "applicant" in sc.parties and sc.parties["applicant"].id_field else ""}
        narrative = case.narrative or f.get("problem_description", "")
        purchase = str(f.get("purchase_date") or "")
        return {**extra,
            # the narrative already tells the purchase (date first): the template's own line is not repeated
            "narrative_tells_purchase": bool(purchase) and purchase in narrative,
            "title": pack.localized(spec.title, lang),
            "f": f,
            "applicant": applicant,
            "respondent": parties.get("respondent", {}),
            "labels": {fl.name: ai.field_label(sc, pack, lang, fl.name) for fl in sc.intake},
            "addressee": addressee,
            "narrative": narrative,
            "demands": demands,
            "norm_refs": group_norms(spec.norm_refs),  # unchecked («TODO») left out, each act named once
            "evidence": evidence,
            "previous_actions": previous,
            "date": today,
            "currency": case.currency or pack.currency,  # the code: the last pass prints «₸ (… тенге)»
            "fmt": fmt,
        }

    def draft(self, case: Case) -> dict[str, Any] | None:
        """PM 01.10: the document's draft before payment — rendered from what is known, blanks in brackets, with no
        model call (the story stands in for the statement of circumstances until the text is written)."""
        if not case.scenario_id:
            return None
        sc, pack = self.scenario_of(case), self.pack_of(case)
        spec = self.next_action_spec(case, sc)
        if spec is None or not spec.template:
            return None
        lang = case.language
        addressee = self._addressee(case, sc, pack, spec)
        party = sc.parties.get(spec.addressee.party) if spec.addressee and spec.addressee.party else None
        blank_names = set(self.draft_blanks(case, sc))
        for attr, key in (("name_field", "name"), ("id_field", "id"), ("address_field", "address")):
            name = getattr(party, attr, None) if party else None
            if name in blank_names and not addressee.get(key):
                addressee[key] = f"[{ai.field_label(sc, pack, lang, name)}]"
        ctx = self.document_context(case, sc, pack, spec, addressee, placeholders=True)
        data = render_docx(pack.packs_root / spec.template, ctx, ai_label="", draft_disclaimer=None,
                           drop_empty=self._drop_empty(pack, lang),
                           finish=self._finishing(case, sc, pack))  # QA BUG-22: the draft shows «₸ (… тенге)» too
        blanks = [{"field": n, "label": ai.field_label(sc, pack, lang, n), "type": sc.field(n).type,
                   "pattern": sc.field(n).pattern} for n in self.draft_blanks(case, sc)]
        return {"title": pack.localized(spec.title, lang), "text": docx_text(data).strip(), "blanks": blanks}

    def fill_blanks(self, session: Session, case: Case, values: dict[str, str]) -> dict[str, str]:
        """The person fills blanks (or corrects facts) in the draft. Returns {field: error code}."""
        if case.status not in (S.INTAKE.value, S.QUALIFIED.value) or not case.scenario_id:
            raise EngineError("not_editable")
        sc, pack = self.scenario_of(case), self.pack_of(case)
        llm = self.llm_for(case)
        values = {k: v for k, v in values.items() if (v or "").strip()}
        errors = self._apply_values(case, sc, pack, values, llm, strict=True, overwrite=True)
        self._save_vault(case, llm)
        self.audit(session, case, "user", "draft_filled", fields=sorted(set(values) - set(errors)))
        if case.status == S.INTAKE.value and not self.missing_fields(case, sc):
            self._next_step(session, case, sc, pack)
        return errors

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
        text = pack.t(case.language, key)
        if not approved and note:  # what to fix, in the reviewer's words
            text = f"{text}\n{note}"
        self.notifier.notify(session, case, "approval", text, sms="document_ready" if approved else None)

    def mark_submitted(self, session: Session, case: Case, action: Action, actor: str,
                       via: str = "user_submits", submitted_on: date | None = None, *, sent: bool = False) -> None:
        """The document went to its addressee. ``submitted_on`` — the filing date the person entered (manual filing
        on the appeal portal): the response deadline runs from it, not from today. ``sent``: the letter has already
        gone out (api/delivery.py, «Отправить по e-mail»), so nothing is sent here."""
        if action.kind != "document" or action.status != "ready":
            raise EngineError("document_not_ready")
        if case.status != S.ACTION_READY.value:
            raise EngineError("cannot_submit_now")
        sc, pack = self.scenario_of(case), self.pack_of(case)
        spec = sc.action(action.action_id)
        if via == "email" and not sent:
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
        start = now.astimezone(pack.tz).date()
        submitted_at = now
        if submitted_on is not None and submitted_on != start:
            # a past filing date: midday local time of that day (the time of day is not known)
            submitted_at = datetime.combine(submitted_on, time(12), tzinfo=pack.tz).astimezone(timezone.utc)
            start = submitted_on
        action.status, action.submitted_at, action.submitted_via = "submitted", submitted_at, via
        self.transition(session, case, S.SUBMITTED, actor, action=spec.id, via=via)
        rd = spec.deadline
        if rd is None and (action.addressee or {}).get("kind") == "forum":
            # a state body from the forum registry: its own term to answer (e.g. АППК, ст. 76 — 15 working days)
            forum = self.action_forum(case, spec)
            rd = forum.response_deadline if forum is not None else None
        if rd:
            due = pack.add_days(start, rd.calendar_days, rd.business_days)
            remind = list(rd.remind_before_days or pack.manifest.reminder_before_days)
            self.scheduler.schedule(session, case, action, due, rd.norm_ref, remind)
            self.audit(session, case, "system", "deadline_created", action=spec.id, due=due.isoformat(),
                       norm_ref=rd.norm_ref)
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


def _grammatical_gender(full_name: str) -> str:
    """For the document's grammar only (verb and adjective forms): from the patronymic, else the surname ending;
    'unknown' when neither tells — the text is then written without gendered forms."""
    return polish.gender_from_name(full_name)


DRAFT = "draft:"  # skipped_fields entry: a required answer left blank, filled in the draft before paying


def _reads_as_is(f: Any, text: str, pack: JurisdictionPack) -> bool:
    """The answer already is the field's value (no model needed): a date, a sum, a number, an e-mail, a phone, a
    code of the right format, or a short plain answer to a text question."""
    try:
        normalize(f, text, today=pack.local_now().date())
    except FieldError:
        return False
    # a text answer with a long number in it (a name and a registration number) goes to the model: two fields
    return f.type != "text" or bool(f.pattern) or (len(text.split()) <= 12 and not re.search(r"\d{9,}", text))


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
    if content_type == DOCX:
        try:
            from docx import Document

            doc = Document(io.BytesIO(data))
            lines = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    lines.append(" | ".join(cell.text.strip() for cell in row.cells))
            return "\n".join(line for line in lines if line.strip()).strip() or None
        except Exception as e:  # damaged file etc.
            log.warning("docx text extraction failed: %s", e)
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
