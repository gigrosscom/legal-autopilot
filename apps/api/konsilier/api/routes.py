from __future__ import annotations

import random
import uuid
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..container import Container
from ..team import notify_team
from .referral import attribute
from ..core.engine import OUTCOME_RESULTS, EngineError
from ..core.models import (Action, Consent, AuditLog, Case, Evidence, Identity, LawyerApplication, Notification, User, WaitlistEntry,
                           utcnow)
from ..core.scenario import RESPONSE_CLASSES
from .background import after_commit
from .deps import current_user, get_container, get_session, load_case, optional_user, require_bot
from .views import case_view

router = APIRouter(prefix="/v1")

MAX_UPLOAD = 15 * 1024 * 1024
ALLOWED_UPLOADS = ("image/jpeg", "image/png", "image/webp", "application/pdf", "text/plain",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def engine_error(e: EngineError) -> HTTPException:
    return HTTPException(409, {"code": e.code, "message": str(e)})


# ------------------------------------------------------------------ users
class NewUser(BaseModel):
    language: str = "ru"
    country: str | None = None
    email: str | None = None
    ref: str | None = None  # invite code from a ?ref= link
    src: str | None = None  # channel from ?src= / utm_source (tiktok, instagram, partner-…)


@router.post("/users")
def create_user(body: NewUser, session: Session = Depends(get_session)) -> dict[str, Any]:
    user = User(channel="web", language=body.language, country=(body.country or "").upper() or None,
                email=body.email)
    attribute(session, user, body.ref, body.src)
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
                "draft": s.is_draft, "beta": s.beta, "kind": s.kind,
            } for s in pack.scenarios.values() if container.packs.offered(s)],
        })
    return out


@router.get("/examples")
def examples(topics: str = "", lang: str = "ru", limit: int = 4, country: str | None = None,
             container: Container = Depends(get_container)) -> dict[str, list[str]]:
    """Suggestions for the consultation chat: how people describe problems of the chosen topics (taxonomy prefixes,
    e.g. "family" or "administrative.fine_appeal"; empty — any). Taken from the offered scenarios' classification
    examples and the taxonomy's dispute examples, so every new scenario brings its own; a random pick, one example
    per scenario or dispute first, so the four differ."""
    wanted = [t.strip() for t in topics.split(",") if t.strip()]

    def fits(tax: str | None) -> bool:
        return not wanted or bool(tax) and any(tax == w or tax.startswith(w + ".") or tax.startswith(w + "_")
                                               for w in wanted)
    sources: list[list[str]] = []
    covered: set[str] = set()
    for sc in container.packs.published(country):
        if fits(sc.taxonomy):
            ex = list(sc.classification.examples.get(lang) or ())
            if ex:
                sources.append(ex)
                covered.add(sc.taxonomy or "")
    for pack in container.packs.packs.values():
        if pack.coverage is None or (country and pack.country != country.upper()) or \
                (not country and pack.manifest.status != "live"):
            continue
        for d in pack.coverage.disputes.values():
            if fits(d.id) and d.id not in covered and d.examples.get(lang):
                sources.append(list(d.examples[lang]))
                covered.add(d.id)
    rng = random.Random()
    for s in sources:
        rng.shuffle(s)
    rng.shuffle(sources)
    out: list[str] = []
    for i in range(max((len(s) for s in sources), default=0)):
        for s in sources:
            if i < len(s) and s[i] not in out:
                out.append(s[i])
    return {"examples": out[:max(1, min(limit, 12))]}


def real_lawyers(session: Session, pack: Any, country: str, lg: str) -> list[dict[str, Any]]:
    """Lawyers whose application the desk verified (status checked by the registry, identity by ЭЦП)."""
    rows = session.scalars(select(LawyerApplication).where(
        LawyerApplication.country == country.upper(), LawyerApplication.status == "verified",
        LawyerApplication.iin_hash.is_not(None)).order_by(LawyerApplication.id)).all()
    kinds = pack.agreements.lawyer_kinds if pack.agreements is not None else {}
    out = []
    for a in rows:
        title = pack.localized(kinds[a.kind], lg) if a.kind in kinds else a.kind
        out.append({
            "id": f"lawyer-{a.id}", "demo": False, "name": a.full_name,
            "title": title[:1].upper() + title[1:], "organization": a.organization or "", "city": a.city or "",
            "years": None, "languages": [], "price_from": None, "response_hours": None, "reviews_count": 0,
            "pro_bono": a.kind == "human_rights",
            "verified": {"license": a.kind in ("advocate", "legal_consultant"), "identity": True, "registry": ""},
            "specializations": [{"key": k, "label": pack.t(lg, f"categories.{k}", default=k)}
                                for k in (a.specializations or [])],
            "results": [], "score": None,
        })
    return out


@router.get("/lawyers")
def list_lawyers(country: str, lang: str = "ru", session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> dict[str, Any]:
    """Lawyer directory. Verified lawyers of the platform once there is at least one; until then the pack's demo
    profiles, marked as demo (no «verified» promise for people who do not exist)."""
    from ..core.rating import CategoryStats, LawyerStats, score

    try:
        pack = container.packs.pack(country)
    except KeyError as e:
        raise HTTPException(404, "unknown country") from e
    real = real_lawyers(session, pack, country, pack.lang(lang))
    if real:
        return {"demo": False, "disclaimer": "", "currency": pack.currency, "lawyers": real}
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
        profile["demo"] = True
        # a made-up person is not «verified»: the demo card never shows the registry/ЭЦП badges
        profile["verified"] = {"license": False, "identity": False, "registry": ""}
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
    # the Terms of Use accepted with the first message: the wording's version, or true for the current one
    accept_terms: bool | str | None = None


@router.post("/cases", status_code=201)
def create_case(body: NewCase, user: User = Depends(current_user), session: Session = Depends(get_session),
                container: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        case, reply = container.engine.start_case(session, user, body.text, language=body.language,
                                                  country=body.country)
        if body.accept_terms:
            version = body.accept_terms if isinstance(body.accept_terms, str) else container.settings.terms_version
            session.add(Consent(case_id=case.id, kind=f"terms:{version[:32]}"))
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
    if case.status == "qualified" and not case.narrative:  # the document's text is written while they look it over
        prewrite_later(session, container, case.id)
    return {"reply": reply.to_dict(), "case": case_view(container.engine, session, case)}


def prewrite_later(session: Session, container: Container, case_id: uuid.UUID) -> None:
    def job(s: Session) -> None:
        case = s.get(Case, case_id)
        if case is not None:
            container.engine.prewrite(s, case)
    after_commit(session, container, job, "prewrite")


def pdf_later(session: Session, container: Container, action_id: uuid.UUID) -> None:
    def job(s: Session) -> None:
        action = s.get(Action, action_id)
        if action is not None:
            container.engine.ensure_pdf(s, action)
    after_commit(session, container, job, "pdf")


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

    def read() -> tuple[Evidence, Any]:  # reading a document calls the model: off the event loop
        ev = container.engine.add_evidence(session, case, kind=kind, filename=file.filename or "file",
                                           content_type=ctype, data=data)
        return ev, container.engine.evidence_reply(session, case, ev)
    ev, reply = await run_in_threadpool(read)
    session.flush()
    # what the document showed is already in the case; "reply" says what was taken and asks only what is missing
    return {"evidence": {"id": str(ev.id), "kind": ev.kind, "filename": ev.filename,
                         "extracted_facts": ev.extracted_facts, "has_text": bool(ev.text), "applied": ev.confirmed},
            "reply": reply.to_dict(), "case": case_view(container.engine, session, case)}


@router.get("/cases/{case_id}/gov-services")
def case_gov_services(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                      container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    """Certificates the person can get themselves on official portals, relevant to this case's branch of law."""
    case = load_case(case_id, session, user)
    pack = container.engine.pack_of(case)
    if pack.gov_services is None:
        return []
    lang = pack.lang(case.language)
    branch = None
    dispute_id = (case.taxonomy or {}).get("dispute_id")
    if not dispute_id and case.scenario_id:
        try:
            dispute_id = container.packs.scenario(case.scenario_id).taxonomy
        except KeyError:
            dispute_id = None
    if dispute_id and pack.coverage and dispute_id in pack.coverage.disputes:
        branch = pack.coverage.dispute(dispute_id).branch
    return [{"id": g.id, "title": pack.localized(g.title, lang), "url": g.url, "provider": g.provider, "auth": g.auth,
             "note": pack.localized(g.note, lang) if g.note else None}
            for g in pack.gov_services.services if not g.evidence_for or branch is None or branch in g.evidence_for]


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
                          "cells": cells, "legal_sources": [_legal_source_view(s, lang, lg) for s in pack.manifest.legal_sources]})
    return {"branches": branches, "countries": countries}


def _legal_source_view(src: Any, lang: str, pack_lang: str) -> dict[str, Any]:
    """Public view of an official legal database: name in the asked language, link and kind."""
    return {"id": src.id, "name": src.name.get(lang) or src.name.get(pack_lang) or src.name["en"], "url": src.url, "operator": src.operator,
            "kind": src.kind, "languages": list(src.languages), "access": src.access,
            "verified_on": src.verified_on.isoformat() if src.verified_on else None}


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
        if e.code == "payment_required":  # not an error: the payment screen is shown
            session.flush()
            view = case_view(container.engine, session, case)
            return {"action_id": None, "payment": view["payment"], "case": view}
        raise engine_error(e) from e
    session.flush()
    if not action.pdf_key and action.docx_key:
        pdf_later(session, container, action.id)
    return {"action_id": str(action.id), "case": case_view(container.engine, session, case)}


class TrainingConsentIn(BaseModel):
    given: bool


@router.put("/cases/{case_id}/training-consent")
def training_consent(case_id: uuid.UUID, body: TrainingConsentIn, user: User = Depends(current_user),
                     session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """The owner allows (or withdraws) the use of this case, anonymised, to teach Konsilier's own model. Off by
    default; withdrawing removes the case from every later training export."""
    case = load_case(case_id, session, user)
    rows = session.scalars(select(Consent).where(Consent.case_id == case.id, Consent.kind == "training")).all()
    if body.given and not rows:
        session.add(Consent(case_id=case.id, kind="training"))
    if not body.given:
        for row in rows:
            session.delete(row)
    container.engine.audit(session, case, f"user:{user.id}", "training_consent", given=body.given)
    session.flush()
    return {"case": case_view(container.engine, session, case)}


PURPOSE_RU = {"document": "Оплата документа", "case": "Оплата «Дело под ключ»", "plan": "Оплата тарифа"}


class PaymentIn(BaseModel):
    purpose: Literal["document", "case"]


def contact_to_confirm(container: Container, owner: User) -> list[str]:
    """How the case owner is to confirm a contact before paying: ["phone"] (SMS code), or ["email"] where SMS sign-in
    is not configured; [] when a confirmed contact is there, the person is in Telegram, it is a test account (smoke
    checks) or nothing can be sent."""
    if not container.settings.payment_requires_contact or owner.channel == "telegram" or owner.is_test:
        return []
    methods = container.identity_methods()
    kinds = {i.kind for i in owner.identities}
    if methods["phone"]:
        return [] if "phone" in kinds else ["phone"]
    if methods["email"]:
        return [] if kinds & {"phone", "email"} else ["email"]
    return []


@router.post("/cases/{case_id}/payment")
def create_payment(case_id: uuid.UUID, body: PaymentIn, user: User = Depends(current_user),
                   session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """A bill for one document (scenario price) or «Дело под ключ» (every document of the case). The owner confirms
    a phone first: the document and deadline reminders reach them, and the case is not lost with the browser."""
    case = load_case(case_id, session, user)
    methods = contact_to_confirm(container, session.get(User, case.owner_id))
    if methods:
        raise HTTPException(422, {"code": "contact_required", "message": "contact_required", "methods": methods})
    try:
        container.engine.create_invoice(session, user_id=case.owner_id, purpose=body.purpose, case=case,
                                        actor=f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    if not case.narrative:  # the payment window is open: the document's text is written meanwhile
        prewrite_later(session, container, case.id)
    return {"case": case_view(container.engine, session, case)}


def _tell_desk_claimed(container: Container, inv, where: str) -> None:
    notify_team(container, f"{PURPOSE_RU.get(inv.purpose, 'Оплата')} {inv.code}: проверьте перевод",
                f"Клиент сообщил о переводе {inv.amount} {inv.currency or ''} с кодом {inv.code} в комментарии.\n"
                f"Счёт №{inv.id}, {where}.\n\n"
                f"Найдите перевод в Kaspi и отметьте «Оплата получена» или «Не найдена» в оперативном центре: "
                f"https://konsilier.com/ops", desk="clients",
                also=container.settings.payment_notify_emails)


@router.post("/cases/{case_id}/payment/claim")
def claim_payment(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                  container: Container = Depends(get_container)):
    """"I have paid": the invoice waits for the clients desk to find the transfer; the desk gets an e-mail."""
    case = load_case(case_id, session, user)
    try:
        inv = container.engine.claim_payment(session, container.engine.invoice_of(session, case), f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    if inv.status == "awaiting_confirmation" and not user.is_test:
        _tell_desk_claimed(container, inv, f"дело {case.id}")
    if not case.narrative:
        prewrite_later(session, container, case.id)
    return {"case": case_view(container.engine, session, case)}


# ------------------------------------------------------------------ plans («Бизнес», «Бизнес Про»)
def plans_view(container: Container, session: Session, user: User) -> dict[str, Any]:
    eng = container.engine
    cfg = eng.config
    return {"plans": {k: {"price": v[0], "documents": v[1], "days": cfg.plan_days} for k, v in cfg.plans.items()},
            "case_price": cfg.case_price, "currency": eng.plan_currency(), "available": eng.payments.available(),
            "signed_in": bool(user.email or user.phone),
            "subscription": eng.subscription_view(session, user.id),
            "invoice": eng.invoice_details(eng.plan_invoice_of(session, user.id))}


@router.get("/plans")
def plans(user: User = Depends(current_user), session: Session = Depends(get_session),
          container: Container = Depends(get_container)) -> dict[str, Any]:
    return plans_view(container, session, user)


@router.post("/plans/{plan}/invoice")
def plan_invoice(plan: str, user: User = Depends(current_user), session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> dict[str, Any]:
    """A bill for a subscription. The person must be signed in: the desk contacts them and the period is theirs."""
    if not (user.email or user.phone):
        raise HTTPException(422, {"code": "contact_required", "message": "contact_required"})
    try:
        container.engine.create_invoice(session, user_id=user.id, purpose="plan", plan=plan,
                                        actor=f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    return plans_view(container, session, user)


@router.post("/plans/invoice/claim")
def plan_claim(user: User = Depends(current_user), session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        inv = container.engine.claim_payment(session, container.engine.plan_invoice_of(session, user.id),
                                             f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    if inv.status == "awaiting_confirmation" and not user.is_test:
        _tell_desk_claimed(container, inv, f"тариф «{inv.plan}», клиент {user.email or user.phone}")
    return plans_view(container, session, user)


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
    if not container.engine.document_unlocked(case, action):
        raise HTTPException(402, {"code": "payment_required", "message": "document is available after payment"})
    if format == "pdf" and not action.pdf_key and action.docx_key:  # made in the background; not there yet
        container.engine.ensure_pdf(session, action)
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
    """Loose types on purpose: every field is checked below, so the answer is 422 with a code per field."""
    country: str = Field(min_length=2, max_length=2)
    full_name: str | None = Field(default=None, max_length=300)
    kind: str | None = Field(default=None, max_length=40)
    organization: str | None = Field(default=None, max_length=300)
    license_number: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=200)
    specializations: list[str] = Field(default_factory=list, max_length=10)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=300)
    consent: bool = False
    message: str | None = Field(default=None, max_length=2000)
    referred_by: str | None = Field(default=None, max_length=16)
    wants_expert: bool = False
    website: str | None = Field(default=None, max_length=300)  # honeypot: hidden from people, bots fill it


APPS_PER_IP_HOUR = 5


def validate_lawyer_application(body: LawyerApplicationIn) -> tuple[dict[str, str], str | None]:
    """({field: error code}, normalized phone)."""
    from ..identity import form_rules as R

    phone, phone_err = R.normalize_kz_phone(body.phone)
    checks = {
        "full_name": R.check_full_name(body.full_name),
        "kind": None if body.kind in R.LAWYER_KINDS else "required",
        "license_number": R.check_license(body.license_number, body.kind),
        "city": R.check_city(body.city),
        "phone": phone_err,
        "email": R.check_email(body.email),
        "consent": None if body.consent else "required",
        "specializations": None if all(0 < len(x) <= 40 for x in body.specializations) else "invalid",
    }
    errors = {k: v for k, v in checks.items() if v}
    if body.organization and len(body.organization.strip()) > 300:
        errors["organization"] = "too_long"
    return errors, phone


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


@router.post("/lawyer-applications", status_code=201)
def apply_as_lawyer(body: LawyerApplicationIn, request: Request, response: Response,
                    session: Session = Depends(get_session), user: User | None = Depends(optional_user),
                    container: Container = Depends(get_container)) -> dict[str, Any]:
    import secrets

    from ..identity.form_rules import clean

    if (body.website or "").strip():
        raise HTTPException(422, {"code": "spam", "message": "spam", "fields": {}})
    errors, phone = validate_lawyer_application(body)
    if errors:
        raise HTTPException(422, {"code": "invalid_application", "message": "invalid_application", "fields": errors})

    ip = _client_ip(request)
    ip_hash = container.identities.h("ip", ip) if ip else None
    if ip_hash and (session.scalar(select(func.count()).select_from(LawyerApplication).where(
            LawyerApplication.ip_hash == ip_hash, LawyerApplication.created_at > utcnow() - timedelta(hours=1))) or 0) \
            >= APPS_PER_IP_HOUR:
        raise HTTPException(429, {"code": "too_many", "message": "too_many"})

    ident = session.scalar(select(Identity).where(Identity.user_id == user.id, Identity.kind == "iin")) if user else None
    active = (LawyerApplication.status.in_(("new", "verified")))
    same_phone = session.scalar(select(LawyerApplication).where(LawyerApplication.phone == phone, active)
                                .order_by(LawyerApplication.id.desc()))
    if same_phone is None:  # applications sent before the form had a phone field: the number is in `contact`
        from ..identity.form_rules import normalize_kz_phone
        for old in session.scalars(select(LawyerApplication).where(LawyerApplication.phone.is_(None), active)).all():
            if normalize_kz_phone(old.contact)[0] == phone:
                old.phone, same_phone = phone, old
                break
    if same_phone is not None:
        if ident is not None and not same_phone.iin_hash and user is not None:
            # applied on the phone, confirmed ЭЦП on the computer: the same number ties the two together
            same_phone.user_id, same_phone.iin_hash, same_phone.ecp_name = user.id, ident.subject_hash, user.display_name
            fresh = {"license_number": clean(body.license_number), "city": clean(body.city),
                     "organization": clean(body.organization), "email": (body.email or "").strip()}
            for k, v in fresh.items():  # the old form may have left these empty
                if v and not getattr(same_phone, k):
                    setattr(same_phone, k, v)
            response.status_code = 200
            notify_team(container, f"Заявка юриста №{same_phone.id}: ЭЦП подтверждена",
                        f"{same_phone.full_name}: к заявке привязана ЭЦП ({user.display_name or '—'}). "
                        f"Сверьте ФИО по ЭЦП с ФИО в заявке и статус по реестру в оперативном центре.")
            return {"id": same_phone.id, "referral_code": same_phone.referral_code, "linked": True,
                    "ecp_verified": True, "invited": 0}
        raise HTTPException(409, {"code": "duplicate_application", "message": "duplicate_application",
                                  "fields": {"phone": "duplicate"}})
    if ident is not None and session.scalar(select(LawyerApplication.id).where(
            LawyerApplication.iin_hash == ident.subject_hash, active)):
        raise HTTPException(409, {"code": "duplicate_application", "message": "duplicate_application",
                                  "fields": {"ecp": "duplicate"}})

    code = secrets.token_urlsafe(5).replace("-", "x").replace("_", "y")[:7].upper()
    ref = (body.referred_by or "").strip().upper() or None
    if ref and not session.scalar(select(LawyerApplication.id).where(LawyerApplication.referral_code == ref)):
        ref = None  # unknown code is ignored, not an error
    email = (body.email or "").strip() or None
    app_row = LawyerApplication(
        country=body.country.upper(), full_name=clean(body.full_name), kind=body.kind,
        organization=clean(body.organization) or None, license_number=clean(body.license_number) or None,
        city=clean(body.city), specializations=body.specializations, phone=phone, email=email,
        contact=email or phone, message=(body.message or "").strip() or None, wants_expert=body.wants_expert,
        referral_code=code, referred_by=ref, ip_hash=ip_hash)
    if user is not None:  # the application belongs to this browser's account, even before ЭЦП
        app_row.user_id = user.id
    if ident is not None:  # applied signed in with ЭЦП: who they are, per the certificate
        app_row.iin_hash, app_row.ecp_name = ident.subject_hash, user.display_name
    session.add(app_row)
    session.flush()
    notify_team(container, f"Новая заявка юриста №{app_row.id}: {app_row.full_name}",
                 f"{app_row.full_name} ({app_row.kind})\nОрганизация: {app_row.organization or '—'}\n"
                 f"Лицензия / удостоверение: {app_row.license_number or '—'}\nГород: {app_row.city or '—'}\n"
                 f"Телефон: {app_row.phone}\nE-mail: {app_row.email or '—'}\n"
                 f"Специализации: {', '.join(app_row.specializations or []) or '—'}\n"
                 f"ЭЦП: {'подтверждена' if ident is not None else 'ещё нет'}\n\n"
                 f"Сверьте данные по чек-листу и реестру в оперативном центре: https://konsilier.com/ops")
    invited = session.scalar(select(func.count()).select_from(LawyerApplication)
                             .where(LawyerApplication.referred_by == code))
    return {"id": app_row.id, "referral_code": code, "invited": invited or 0, "ecp_verified": ident is not None,
            "linked": False}


class ClientErrorIn(BaseModel):
    message: str = Field(max_length=1000)
    stack: str | None = Field(default=None, max_length=4000)
    digest: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=300)
    user_agent: str | None = Field(default=None, max_length=300)
    translated: bool | None = None


@router.post("/client-errors", status_code=204)
def client_error(body: ClientErrorIn, session: Session = Depends(get_session)) -> None:
    """Browser crash reports → server log and audit_log (no personal data: message, stack, path only).

    Stored so they can be read in the admin (GET /v1/admin/client-errors) without server access.
    """
    import logging

    logging.getLogger("konsilier.client").warning(
        "client error at %s: %s | translated=%s | ua=%s | stack=%s",
        body.url, body.message, body.translated, body.user_agent, (body.stack or "").replace("\n", " ⏎ ")[:1500])
    recent = session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.event == "client_error", AuditLog.created_at > utcnow() - timedelta(minutes=1)))
    if (recent or 0) < 30:  # an open endpoint: cap the flood a broken or hostile client can write
        session.add(AuditLog(case_id=None, actor="browser", event="client_error", data=body.model_dump()))


def _unread(session: Session, user: User) -> int:
    return session.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0


@router.get("/notifications")
def notifications(unread: bool = False, user: User = Depends(current_user),
                  session: Session = Depends(get_session)) -> dict[str, Any]:
    """The site inbox (the bell): newest first; `unread=1` → only those not opened yet. `unread` in the answer is
    always the count of unread ones."""
    q = select(Notification).where(Notification.user_id == user.id)
    if unread:
        q = q.where(Notification.read_at.is_(None))
    rows = session.scalars(q.order_by(Notification.id.desc()).limit(50)).all()
    return {"items": [{"id": n.id, "case_id": str(n.case_id) if n.case_id else None, "kind": n.kind, "text": n.text,
                       "created_at": n.created_at.isoformat(),
                       "read_at": n.read_at.isoformat() if n.read_at else None} for n in rows],
            "unread": _unread(session, user)}


class ReadIn(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=200)
    all: bool = False


@router.post("/notifications/read")
def notifications_read(body: ReadIn, user: User = Depends(current_user),
                       session: Session = Depends(get_session)) -> dict[str, int]:
    """Marks the given notifications (or all of them) read; only the person's own ones are touched."""
    q = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if not body.all:
        if not body.ids:
            return {"unread": _unread(session, user)}
        q = q.where(Notification.id.in_(body.ids))
    session.execute(q.values(read_at=utcnow()))
    return {"unread": _unread(session, user)}
