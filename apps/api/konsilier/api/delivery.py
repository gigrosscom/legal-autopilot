"""«Отправить по e-mail»: the client sends their prepared, paid document to the other side (seller, bank, employer,
a foreign company) from the case — owner's «да» 01.10.2026.

We are a technical channel, not a representative: the client enters the address, sees the letter and presses
«Отправить» themselves. The letter goes from CLAIMS_EMAIL_FROM through Resend, Reply-To and a copy to the client's
confirmed e-mail; attachments are the document (PDF, or DOCX when there is no PDF) and, if the client signed it,
their ЭЦП CMS. Each sending is a `Filing` (the proof, docs/integrations-plan.md 7.3): who, to whom, when, the
document's SHA-256, Resend's id and every delivery event from Resend's webhook (Svix signature). The first sending
marks the document as submitted, so the response deadline and its reminders start from that day.

Abuse limits: paid documents only, one recipient per letter, EMAIL_SEND_PER_DOCUMENT letters per document,
EMAIL_SEND_PER_CASE_DAY per case in 24 hours, EMAIL_SEND_PER_USER_HOUR attempts per person in an hour.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.engine import EngineError
from ..core.models import Action, Case, Filing, Identity, User, utcnow
from ..identity.senders import SendError
from .deps import current_user, get_container, get_session, load_case

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")

CONSENT_VERSION = "email-v1"
MAX_ATTACHMENTS_BYTES = 30 * 1024 * 1024  # Resend takes up to 40 MB per letter after base64
# one address: no lists, no display names, no spaces; a dot in the domain
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                      r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
SIGNED_STATUSES = ("ready", "submitted")
# sent by the client from their own account (we never message third parties); the proof is their screenshot
CLIENT_CHANNELS = ("whatsapp", "telegram", "instagram", "app_dispute", "other")
MAX_PROOFS_PER_DOCUMENT = 10
RECEIPT_TYPES = ("image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf")
MAX_RECEIPT = 10 * 1024 * 1024  # a document that is ready (first sending) or already filed (again)
# Resend webhook event → our status; other events only go to the log
EVENT_STATUS = {"email.sent": "sent", "email.delivered": "delivered", "email.bounced": "bounced",
                "email.complained": "complained", "email.failed": "failed"}
FINAL = ("bounced", "complained", "failed")

TEXTS: dict[str, dict[str, str]] = {
    "ru": {
        "to": "Кому: {to}\n\n",
        "body": "Здравствуйте.\n\n{to}Направляю вам документ «{title}». Он во вложении{signed}.\n\n"
                "Прошу рассмотреть его и ответить в установленный срок. Ответ на это письмо придёт мне напрямую: "
                "{reply}.\n\nС уважением,\n{name}\n\n—\nОтправлено через сервис Konsiliér AI по поручению отправителя.",
        "signed": " вместе с файлом, подписанным моей ЭЦП (.cms)",
        "bounced": "Письмо «{title}» не доставлено на {to}: адрес не принимает почту. Проверьте адрес и отправьте ещё раз.",
        "delivered": "Письмо «{title}» доставлено на {to}.",
        "message": "Здравствуйте!\nНаправляю вам документ «{title}» — PDF прилагаю.\n"
                   "Прошу рассмотреть его и ответить в установленный срок.{name}",
        "replied": "Пришёл ответ на «{title}» от {sender}. Он сохранён в деле — откройте дело и отметьте, что в нём.",
        "followup": "Прошло {hours} ч с отправки «{title}». Вам ответили? Откройте дело и отметьте ответ — или подождём "
                    "до срока, мы напомним.",
    },
    "kk": {
        "to": "Кімге: {to}\n\n",
        "body": "Сәлеметсіз бе.\n\n{to}Сізге «{title}» құжатын жіберемін. Ол қосымшада{signed}.\n\n"
                "Оны қарап, белгіленген мерзімде жауап беруіңізді сұраймын. Бұл хатқа жауап маған тікелей келеді: "
                "{reply}.\n\nҚұрметпен,\n{name}\n\n—\nKonsiliér AI сервисі арқылы жіберушінің тапсырмасы бойынша жіберілді.",
        "signed": ", менің ЭЦҚ-мен қол қойылған файлмен бірге (.cms)",
        "bounced": "«{title}» хаты {to} мекенжайына жеткізілмеді: мекенжай хат қабылдамайды. Мекенжайды тексеріп, қайта жіберіңіз.",
        "delivered": "«{title}» хаты {to} мекенжайына жеткізілді.",
        "message": "Сәлеметсіз бе!\nСізге «{title}» құжатын жіберемін — PDF қоса беріліп отыр.\n"
                   "Оны қарап, белгіленген мерзімде жауап беруіңізді сұраймын.{name}",
        "replied": "«{title}» хатына {sender} жауап берді. Жауап іске сақталды — істі ашып, онда не жазылғанын белгілеңіз.",
        "followup": "«{title}» жіберілгеннен бері {hours} сағат өтті. Сізге жауап берді ме? Істі ашып, жауапты белгілеңіз — "
                    "әйтпесе мерзімге дейін күтеміз, еске саламыз.",
    },
    "en": {
        "to": "To: {to}\n\n",
        "body": "Hello,\n\n{to}Please find attached the document “{title}”{signed}.\n\n"
                "I kindly ask you to review it and reply within the applicable time limit. Replies to this e-mail "
                "come directly to me: {reply}.\n\nKind regards,\n{name}\n\n—\n"
                "Sent via the Konsiliér AI service on behalf of the sender.",
        "signed": ", together with the file signed with my electronic digital signature (.cms)",
        "bounced": "The letter “{title}” was not delivered to {to}: the address does not accept mail. Check the "
                   "address and send it again.",
        "delivered": "The letter “{title}” was delivered to {to}.",
        "message": "Hello,\nI am sending you the document “{title}” — the PDF is attached.\n"
                   "Please review it and reply within the applicable time limit.{name}",
        "replied": "A reply to “{title}” came from {sender}. It is saved in the case — open the case and record what it says.",
        "followup": "{hours} h have passed since you sent “{title}”. Have they replied? Open the case and record the "
                    "reply — or we wait until the deadline and remind you.",
    },
}


def _texts(lang: str) -> dict[str, str]:
    return TEXTS.get(lang) or TEXTS["en"]


def _http(status: int, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status, {"code": code, "message": code, **extra})


def valid_email(value: str) -> str | None:
    v = (value or "").strip()
    if len(v) > 254 or not EMAIL_RE.match(v) or ".." in v:
        return None
    return v.lower()


def confirmed_email(session: Session, user: User) -> str | None:
    """The client's own address, only when confirmed by a code (an e-mail identity): it gets Reply-To and the copy."""
    if not user.email:
        return None
    has = session.scalar(select(Identity.id).where(Identity.user_id == user.id, Identity.kind == "email"))
    return user.email if has else None


def addressee_of(action: Action) -> dict[str, Any]:
    """The addressee organisation of the step for the filing record (``body`` / ``body_key``)."""
    a = action.addressee or {}
    name = a.get("name")
    return {"body": str(name)[:500] if name else None,
            "body_key": f"{a['kind']}:{a['key']}"[:100] if a.get("key") and a.get("kind") else None}


def filing_view(f: Filing) -> dict[str, Any]:
    return {"id": str(f.id), "channel": f.channel, "recipient": f.recipient, "status": f.status,
            "has_receipt": bool(f.receipt_key), "replied_at": f.replied_at.isoformat() if f.replied_at else None,
            "sent_at": f.sent_at.isoformat() if f.sent_at else None,
            "delivered_at": f.delivered_at.isoformat() if f.delivered_at else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "doc_sha256": f.doc_sha256, "attachments": f.attachments,
            "events": [{"at": e.get("at"), "type": e.get("type")} for e in (f.events or [])]}


def filings_of(session: Session, case_id: uuid.UUID) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Letters and the client's own sendings per document. The registered appeal on the appeal portal (the row with
    an appeal number) is shown on its own (``filed`` in the case view, core/appeal_portal.py)."""
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for f in session.scalars(select(Filing).where(Filing.case_id == case_id, Filing.appeal_number.is_(None))
                             .order_by(Filing.created_at)):
        out.setdefault(f.action_id, []).append(filing_view(f))
    return out


def is_paid(container: Container, case: Case, action: Action) -> bool:
    """Paid: the whole case, a paid single document, a subscription or a referral bonus — not a free document."""
    return bool(case.paid) or action.unlocked_by not in (None, "free")


def send_state(container: Container, session: Session, case: Case, action: Action) -> dict[str, Any]:
    """For the case page: may this document be sent by e-mail now, and if not, why."""
    st = container.settings
    reason = None
    if action.kind != "document" or action.status not in SIGNED_STATUSES:
        reason = "not_ready"
    elif not is_paid(container, case, action):
        reason = "payment_required"
    elif getattr(container, "claims_mailer", None) is None:
        reason = "unavailable"
    sent = _count(session, Filing.action_id == action.id, Filing.channel == "email", Filing.status != "failed")
    left = max(0, st.email_send_per_document - sent)
    if reason is None and left == 0:
        reason = "limit_document"
    return {"available": reason is None, "reason": reason, "left": left}


def _count(session: Session, *where: Any) -> int:
    return session.scalar(select(func.count()).select_from(Filing).where(*where)) or 0


# ------------------------------------------------------------------ the letter
@dataclass
class Letter:
    to: str
    reply_to: list[str]
    copy_to: str
    subject: str
    text: str
    attachments: list[tuple[str, bytes]]
    doc_sha256: str
    signature_id: uuid.UUID | None
    token: str


def inbound_address(container: Container, token: str) -> str | None:
    """claims+<token>@domain, when replies are received by Resend (CLAIMS_INBOUND): a reply sent to it is attached
    to the case by itself. Off → None (replies go only to the client)."""
    if not container.settings.claims_inbound:
        return None
    m = re.search(r"([A-Za-z0-9._-]+)@([A-Za-z0-9.-]+)", container.settings.claims_email_from)
    domain = container.settings.claims_reply_domain or (m.group(2) if m else "")
    return f"{m.group(1)}+{token}@{domain}" if m and domain else None


def _main_file(container: Container, session: Session, action: Action) -> tuple[str, bytes]:
    if not action.pdf_key and action.docx_key:  # made in the background; not there yet
        container.engine.ensure_pdf(session, action)
    name = f"{action.sequence:02d}-{action.action_id}"
    if action.pdf_key:
        return f"{name}.pdf", container.storage.get(action.pdf_key)
    if action.docx_key:
        return f"{name}.docx", container.storage.get(action.docx_key)
    raise _http(409, "not_ready")


def build_letter(container: Container, session: Session, case: Case, action: Action, user: User,
                 to: str, token: str | None = None) -> Letter:
    reply = confirmed_email(session, user)
    if not reply:
        raise _http(409, "email_required")
    token = token or secrets.token_hex(5)
    engine = container.engine
    sc, pack = engine.scenario_of(case), engine.pack_of(case)
    spec = sc.action(action.action_id)
    title = pack.localized(spec.title, case.language)
    doc_name, doc = _main_file(container, session, action)
    files = [(doc_name, doc)]
    sig = next((g for g in reversed(action.signatures) if g.role == "applicant"), None)
    if sig is not None:
        files.append((f"{doc_name.rsplit('.', 1)[0]}.{sig.file_format}.cms", container.storage.get(sig.cms_key)))
    if sum(len(d) for _, d in files) > MAX_ATTACHMENTS_BYTES:
        raise _http(413, "too_large")
    tx = _texts(case.language)
    addressee = (action.addressee or {}).get("name")
    name = (sig.signer_name if sig is not None else None) or user.display_name or reply
    text = tx["body"].format(to=tx["to"].format(to=addressee) if addressee else "", title=title,
                             signed=tx["signed"] if sig is not None else "", reply=reply, name=name)
    inbound = inbound_address(container, token)
    subject = title[:280] + (f" [K-{token}]" if inbound else "")
    return Letter(to=to, reply_to=[reply, inbound] if inbound else [reply], copy_to=reply, subject=subject,
                  text=text, attachments=files, doc_sha256=hashlib.sha256(doc).hexdigest(),
                  signature_id=sig.id if sig is not None else None, token=token)


def _check(container: Container, session: Session, case: Case, action: Action, user: User, to: str) -> str:
    """Everything that must hold before a letter is shown or sent; the recipient, normalised."""
    if action.kind != "document" or action.status not in SIGNED_STATUSES:
        raise _http(409, "not_ready")
    if not is_paid(container, case, action):
        raise _http(402, "payment_required")
    if action.status == "ready" and case.status != "action_ready":
        raise _http(409, "cannot_submit_now")
    if getattr(container, "claims_mailer", None) is None:
        raise _http(503, "unavailable")
    addr = valid_email(to)
    if addr is None:
        raise _http(422, "bad_email")
    return addr


def _limits(container: Container, session: Session, case: Case, action: Action, user: User) -> None:
    st, now = container.settings, utcnow()
    if _count(session, Filing.user_id == user.id, Filing.created_at >= now - timedelta(hours=1)) \
            >= st.email_send_per_user_hour:
        raise _http(429, "too_many")
    if _count(session, Filing.action_id == action.id, Filing.channel == "email",
              Filing.status != "failed") >= st.email_send_per_document:
        raise _http(429, "limit_document")
    if _count(session, Filing.case_id == case.id, Filing.channel == "email", Filing.status != "failed",
              Filing.created_at >= now - timedelta(days=1)) >= st.email_send_per_case_day:
        raise _http(429, "limit_case_day")


class EmailIn(BaseModel):
    to: str = Field(min_length=3, max_length=254)


class SendIn(EmailIn):
    confirm: bool = False  # the client saw the letter and pressed «Отправить»


@router.post("/cases/{case_id}/actions/{action_id}/email/preview")
def preview(case_id: uuid.UUID, action_id: uuid.UUID, body: EmailIn, user: User = Depends(current_user),
            session: Session = Depends(get_session), container: Container = Depends(get_container)):
    case, action = _load(session, user, case_id, action_id)
    to = _check(container, session, case, action, user, body.to)
    letter = build_letter(container, session, case, action, user, to)
    return {"from": container.settings.claims_email_from, "to": letter.to, "reply_to": letter.reply_to[0],
            "cc": letter.copy_to, "subject": letter.subject, "text": letter.text,
            "attachments": [{"name": n, "size": len(d)} for n, d in letter.attachments],
            "state": send_state(container, session, case, action)}


def send_email(container: Container, session: Session, case: Case, action: Action, user: User, to: str, *,
               consent: str = CONSENT_VERSION) -> Filing:
    """One letter to one address, with its proof. Raises (after keeping the failed attempt) when Resend refuses."""
    to = _check(container, session, case, action, user, to)
    _limits(container, session, case, action, user)
    letter = build_letter(container, session, case, action, user, to)
    now = utcnow()
    filing = Filing(case_id=case.id, action_id=action.id, user_id=user.id, signature_id=letter.signature_id,
                    channel="email", recipient=letter.to, **addressee_of(action), reply_to=", ".join(letter.reply_to)[:254],
                    cc=letter.copy_to, sender=container.settings.claims_email_from, subject=letter.subject,
                    message=letter.text, status="sending", doc_sha256=letter.doc_sha256, reply_token=letter.token,
                    consent_text_version=consent, consent_at=now,
                    events=[{"at": now.isoformat(), "type": "confirmed", "source": "client"}],
                    attachments=[{"name": n, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                                 for n, d in letter.attachments])
    session.add(filing)
    session.flush()
    actor = f"user:{user.id}"
    try:
        external = container.claims_mailer.send_letter(
            to=letter.to, subject=letter.subject, text=letter.text, reply_to=letter.reply_to, cc=[letter.copy_to],
            attachments=letter.attachments, idempotency_key=f"filing-{filing.id}")
    except SendError as e:
        filing.status, filing.error = "failed", str(e)[:300]
        filing.events = [*filing.events, {"at": utcnow().isoformat(), "type": "failed", "source": "api"}]
        container.engine.audit(session, case, actor, "email_failed", action=action.action_id, filing=str(filing.id))
        session.commit()  # the failed attempt stays in the proof and counts towards the hourly limit
        raise _http(502, "send_failed") from e
    sent_at = utcnow()
    filing.status, filing.external_id, filing.sent_at = "sent", external, sent_at
    filing.events = [*filing.events, {"at": sent_at.isoformat(), "type": "sent", "source": "api", "id": external}]
    container.engine.audit(session, case, actor, "email_sent", action=action.action_id, filing=str(filing.id),
                           doc_sha256=letter.doc_sha256, resend_id=external)
    _mark_filed(container, session, case, action, actor, "email")
    session.flush()
    return filing


@router.post("/cases/{case_id}/actions/{action_id}/email")
def send(case_id: uuid.UUID, action_id: uuid.UUID, body: SendIn, user: User = Depends(current_user),
         session: Session = Depends(get_session), container: Container = Depends(get_container)):
    from .views import case_view

    case, action = _load(session, user, case_id, action_id)
    _check(container, session, case, action, user, body.to)
    if not body.confirm:
        raise _http(422, "confirm_required")
    filing = send_email(container, session, case, action, user, body.to)
    return {"filing": filing_view(filing), "case": case_view(container.engine, session, case)}


def _mark_filed(container: Container, session: Session, case: Case, action: Action, actor: str, via: str) -> None:
    """The first sending of a document: the response deadline and reminders start today."""
    if action.status != "ready":
        return
    try:
        container.engine.mark_submitted(session, case, action, actor, via=via, sent=True)
    except EngineError as e:  # it has gone; the client can still mark «подано» by hand
        log.warning("document sent, but not marked submitted: %s", e)


def _load(session: Session, user: User, case_id: uuid.UUID, action_id: uuid.UUID) -> tuple[Case, Action]:
    case = load_case(case_id, session, user)
    action = session.get(Action, action_id)
    if action is None or action.case_id != case.id:
        raise HTTPException(404, "action not found")
    return case, action


# ------------------------------------------------------------------ «Мастер отправки»
def _require_sendable(container: Container, case: Case, action: Action) -> None:
    if action.kind != "document" or action.status not in SIGNED_STATUSES:
        raise _http(409, "not_ready")
    if not is_paid(container, case, action):
        raise _http(402, "payment_required")


def short_message(container: Container, case: Case, action: Action, user: User) -> str:
    """3–4 lines for a messenger; the full text is the PDF sent with it."""
    engine = container.engine
    title = engine.pack_of(case).localized(engine.scenario_of(case).action(action.action_id).title, case.language)
    sig = next((g for g in reversed(action.signatures) if g.role == "applicant"), None)
    name = (sig.signer_name if sig is not None else None) or user.display_name
    return _texts(case.language)["message"].format(title=title, name=f"\n{name}" if name else "")


@router.get("/cases/{case_id}/actions/{action_id}/send")
def send_plan(case_id: uuid.UUID, action_id: uuid.UUID, user: User = Depends(current_user),
              session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """What the wizard needs: the other side's contacts found in the case (with where each came from), the short
    messenger text, whether e-mail can go now, and what has been sent already."""
    from ..contacts import find_contacts

    case, action = _load(session, user, case_id, action_id)
    _require_sendable(container, case, action)
    pack = container.engine.pack_of(case)
    lang = pack.lang(case.language)
    own = {x for x in (user.email, user.phone) if x}
    contacts = find_contacts(case, action, own=own,
                             evidence_label=lambda kind: pack.t(lang, f"evidence.{kind}", default=kind),
                             id_labels=pack.t(lang, "contacts.id_labels", default=""))
    email = send_state(container, session, case, action)
    return {"contacts": contacts, "message": short_message(container, case, action, user), "email": email,
            "route": route_plan(action, contacts, email, short_message(container, case, action, user),
                                *_portal(session, container, case, action)),
            "reply_to": confirmed_email(session, user),
            "filings": filings_of(session, case.id).get(action.id, [])}


GOV_KINDS = ("authority", "forum")


def _portal(session: Session, container: Container, case: Case, action: Action) -> tuple[dict[str, Any] | None, bool]:
    """The appeal portal target of the step (None → not filed there) and whether it is filed there already."""
    from ..core.appeal_portal import portal_filing, portal_target

    target = portal_target(container.engine.pack_of(case), case.language, action)
    return target, target is not None and portal_filing(session, action.id) is not None


def route_plan(action: Action, contacts: list[dict[str, Any]], email: dict[str, Any],
               message: str, portal: dict[str, Any] | None = None, filed: bool = False) -> list[dict[str, Any]]:
    """«Принцип 3 клика» (owner 01.10.2026): WE pick where the document goes. A state body → the state portal (a step of its
    own, done on the portal by the client); the other side → every messenger found (WhatsApp, Telegram, Instagram — one
    button each, fastest first), then e-mail if an address was found (sent by us at once, `auto`). Nothing found → the client adds an address.

    ``portal`` — the appeal portal target of the step (core/appeal_portal.py ``portal_target``): the step is
    ``channel = "portal"`` and the wizard opens the portal bridge (what to pick, the text, the PDF, then the number
    and date read from the confirmation); ``filed`` — the appeal is registered there already."""
    addressee = action.addressee or {}
    steps: list[dict[str, Any]] = []
    if portal is not None:
        steps.append({"channel": "portal", "to": portal.get("recipient") or portal.get("body") or "",
                      "portal": portal.get("name"), "auto": False, "href": portal.get("portal"),
                      **({"done": True} if filed else {})})
        return steps
    if addressee.get("kind") in GOV_KINDS:
        steps.append({"channel": "gov", "to": addressee.get("name") or "", "auto": False,
                      "href": addressee.get("submit_url")})
        return steps
    first = {k: next((c["value"] for c in contacts if c["kind"] in kinds), None)
             for k, kinds in (("email", ("email",)), ("whatsapp", ("whatsapp", "phone")),
                              ("telegram", ("telegram",)), ("instagram", ("instagram",)))}
    from urllib.parse import quote

    # fastest channels first (owner 01.10): WhatsApp and the social networks, then e-mail
    if first["whatsapp"]:
        steps.append({"channel": "whatsapp", "to": first["whatsapp"], "auto": False,
                      "href": f"https://wa.me/{re.sub(r'[^0-9]', '', first['whatsapp'])}?text={quote(message)}"})
    if first["telegram"]:
        steps.append({"channel": "telegram", "to": f"@{first['telegram']}", "auto": False,
                      "href": f"https://t.me/{first['telegram']}"})
    if first["instagram"]:
        steps.append({"channel": "instagram", "to": f"@{first['instagram']}", "auto": False,
                      "href": f"https://ig.me/m/{first['instagram']}"})
    if first["email"]:
        steps.append({"channel": "email", "to": first["email"], "auto": bool(email.get("available")),
                      "reason": email.get("reason")})
    if not steps:
        steps.append({"channel": "manual", "to": "", "auto": False})
    return steps


class GoIn(BaseModel):
    confirm: bool = False  # «Подписать и отправить» / «Отправить»: the client's instruction


@router.post("/cases/{case_id}/actions/{action_id}/send/go")
def send_go(case_id: uuid.UUID, action_id: uuid.UUID, body: GoIn, user: User = Depends(current_user),
            session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """The one button: everything that can go without the client goes now (e-mail to the address found in the
    case); the rest of the plan (a messenger, the state portal) comes back as steps of one tap each."""
    from ..contacts import find_contacts
    from .views import case_view

    if not body.confirm:
        raise _http(422, "confirm_required")
    case, action = _load(session, user, case_id, action_id)
    _require_sendable(container, case, action)
    pack = container.engine.pack_of(case)
    lang = pack.lang(case.language)
    contacts = find_contacts(case, action, own={x for x in (user.email, user.phone) if x},
                             evidence_label=lambda kind: pack.t(lang, f"evidence.{kind}", default=kind),
                             id_labels=pack.t(lang, "contacts.id_labels", default=""))
    message = short_message(container, case, action, user)
    steps = route_plan(action, contacts, send_state(container, session, case, action), message,
                       *_portal(session, container, case, action))
    sent, errors = [], []
    for step in steps:
        if not step["auto"]:
            continue
        done = session.scalar(select(Filing.id).where(Filing.action_id == action.id, Filing.channel == "email",
                                                      Filing.recipient == step["to"], Filing.status != "failed"))
        if done is not None:  # pressed twice: the letter has gone already
            step["done"] = True
            continue
        if not confirmed_email(session, user):
            raise _http(409, "email_required")  # the reply must reach the client: confirm the e-mail, then again
        try:
            filing = send_email(container, session, case, action, user, step["to"], consent="go-v1")
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {}
            errors.append({"channel": step["channel"], "to": step["to"], "code": detail.get("code", "send_failed")})
            continue
        step["done"] = True
        sent.append(filing_view(filing))
    return {"sent": sent, "errors": errors, "steps": steps, "message": message,
            "case": case_view(container.engine, session, case)}


async def _read_receipt(file: UploadFile | None) -> tuple[bytes, str, str] | None:
    if file is None or not file.filename:
        return None
    ctype = (file.content_type or "").split(";")[0]
    if ctype not in RECEIPT_TYPES:
        raise _http(415, "bad_file")
    data = await file.read(MAX_RECEIPT + 1)
    if len(data) > MAX_RECEIPT:
        raise _http(413, "too_large")
    return data, ctype, file.filename


def _store_receipt(container: Container, filing: Filing, receipt: tuple[bytes, str, str]) -> None:
    data, ctype, name = receipt
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}.get(ctype, "img")
    n = len(filing.events or [])
    filing.receipt_key = container.storage.put(f"cases/{filing.case_id}/filings/{filing.id}/receipt-{n}.{ext}",
                                               data, ctype)
    filing.receipt_sha256 = hashlib.sha256(data).hexdigest()
    filing.events = [*(filing.events or []), {"at": utcnow().isoformat(), "type": "receipt", "source": "client",
                                              "sha256": filing.receipt_sha256, "name": name[:120]}]


@router.post("/cases/{case_id}/actions/{action_id}/send/proof")
async def send_proof(case_id: uuid.UUID, action_id: uuid.UUID, channel: str = Form(...),
                     recipient: str = Form(default="", max_length=254), file: UploadFile | None = File(default=None),
                     user: User = Depends(current_user), session: Session = Depends(get_session),
                     container: Container = Depends(get_container)):
    """«Я отправил»: the client sent the document from their own WhatsApp, Telegram, Instagram or an app dispute.
    We keep the time (and their screenshot, if any); the response deadline starts from it."""
    from .views import case_view

    if channel not in CLIENT_CHANNELS:
        raise _http(422, "bad_channel")
    receipt = await _read_receipt(file)

    def record() -> dict[str, Any]:
        case, action = _load(session, user, case_id, action_id)
        _require_sendable(container, case, action)
        if action.status == "ready" and case.status != "action_ready":
            raise _http(409, "cannot_submit_now")
        now = utcnow()
        if _count(session, Filing.user_id == user.id, Filing.created_at >= now - timedelta(hours=1)) \
                >= container.settings.email_send_per_user_hour:
            raise _http(429, "too_many")
        if _count(session, Filing.action_id == action.id, Filing.channel != "email",
                  Filing.appeal_number.is_(None)) >= MAX_PROOFS_PER_DOCUMENT:
            raise _http(429, "limit_document")
        _, doc = _main_file(container, session, action)
        filing = Filing(case_id=case.id, action_id=action.id, user_id=user.id, channel=channel,
                        recipient=recipient.strip()[:254], **addressee_of(action), status="sent", doc_sha256=hashlib.sha256(doc).hexdigest(),
                        sent_at=now, attachments=[], events=[{"at": now.isoformat(), "type": "sent", "source": "client"}])
        session.add(filing)
        session.flush()
        if receipt is not None:
            _store_receipt(container, filing, receipt)
        actor = f"user:{user.id}"
        container.engine.audit(session, case, actor, "document_sent", action=action.action_id, channel=channel,
                               filing=str(filing.id), receipt=bool(receipt))
        _mark_filed(container, session, case, action, actor, channel)
        session.flush()
        return {"filing": filing_view(filing), "case": case_view(container.engine, session, case)}

    return await run_in_threadpool(record)


def _load_filing(session: Session, user: User, case_id: uuid.UUID, filing_id: uuid.UUID) -> tuple[Case, Filing]:
    case = load_case(case_id, session, user)
    filing = session.get(Filing, filing_id)
    if filing is None or filing.case_id != case.id:
        raise HTTPException(404, "filing not found")
    return case, filing


@router.post("/cases/{case_id}/filings/{filing_id}/receipt")
async def add_receipt(case_id: uuid.UUID, filing_id: uuid.UUID, file: UploadFile = File(...),
                      user: User = Depends(current_user), session: Session = Depends(get_session),
                      container: Container = Depends(get_container)):
    """A screenshot «доставлено / прочитано» added later to a sending the client made themselves."""
    receipt = await _read_receipt(file)
    if receipt is None:
        raise _http(422, "file_required")

    def store() -> dict[str, Any]:
        case, filing = _load_filing(session, user, case_id, filing_id)
        if filing.channel == "email":
            raise _http(409, "email_has_statuses")
        if filing.appeal_number:  # the portal's confirmation is case evidence: .../portal-filing/receipt
            raise _http(409, "portal_receipt")
        if len(filing.events or []) >= 20:
            raise _http(429, "too_many")
        _store_receipt(container, filing, receipt)
        container.engine.audit(session, case, f"user:{user.id}", "filing_receipt", filing=str(filing.id))
        session.flush()
        return {"filing": filing_view(filing)}

    return await run_in_threadpool(store)


@router.get("/cases/{case_id}/filings/{filing_id}/receipt")
def get_receipt(case_id: uuid.UUID, filing_id: uuid.UUID, user: User = Depends(current_user),
                session: Session = Depends(get_session), container: Container = Depends(get_container)):
    _, filing = _load_filing(session, user, case_id, filing_id)
    if not filing.receipt_key:
        raise HTTPException(404, "no receipt")
    ext = filing.receipt_key.rsplit(".", 1)[-1]
    media = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "pdf": "application/pdf"}.get(
        ext, "application/octet-stream")
    return Response(container.storage.get(filing.receipt_key), media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="receipt-{filing.id}.{ext}"'})


def followups(container: Container) -> Any:
    """Scheduler job: a day after a document went out with no answer recorded — «Ответили?» once per document.
    Later reminders come from the response deadline (core/deadlines.py)."""

    def job(session: Session, now: datetime) -> int:
        due = session.scalars(select(Filing).where(Filing.followup_at.is_(None), Filing.sent_at.is_not(None),
                                                   Filing.status.notin_(FINAL),
                                                   Filing.sent_at <= now - timedelta(hours=container.settings.send_followup_hours))).all()
        sent, asked = 0, set()
        for f in due:
            already = f.action_id in asked or session.scalar(select(func.count()).select_from(Filing).where(
                Filing.action_id == f.action_id, Filing.followup_at.is_not(None)))
            f.followup_at = now
            if already:
                continue
            asked.add(f.action_id)
            action, case = session.get(Action, f.action_id), session.get(Case, f.case_id)
            if action is None or case is None or action.status != "submitted" \
                    or case.status != "awaiting_response" or action.responded_at is not None:
                continue
            if session.scalar(select(Filing.id).where(Filing.action_id == f.action_id,
                                                      Filing.replied_at.is_not(None)).limit(1)):
                continue  # the reply came by itself (claims+<token>@…)
            engine = container.engine
            title = engine.pack_of(case).localized(engine.scenario_of(case).action(action.action_id).title,
                                                   case.language)
            engine.notifier.notify(session, case, "delivery", _texts(case.language)["followup"].format(
                title=title, hours=f"{container.settings.send_followup_hours:g}"))
            sent += 1
        return sent

    return job


# ------------------------------------------------------------------ Resend → delivery status
def verify_svix(secret: str, headers: Any, raw: bytes, tolerance: int = 300, now: float | None = None) -> bool:
    """Svix signature (how Resend signs webhooks): base64 HMAC-SHA256 of "{svix-id}.{svix-timestamp}.{body}" with
    the secret after «whsec_», in svix-signature as space-separated «v1,<sig>»; the timestamp within 5 minutes."""
    msg_id, ts, sigs = headers.get("svix-id"), headers.get("svix-timestamp"), headers.get("svix-signature")
    if not (msg_id and ts and sigs):
        return False
    try:
        if abs((now if now is not None else time.time()) - int(ts)) > tolerance:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except (ValueError, TypeError):
        return False
    want = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + raw, hashlib.sha256).digest()).decode()
    for part in sigs.split():
        version, _, sig = part.partition(",")
        if version == "v1" and hmac.compare_digest(sig, want):
            return True
    return False


@router.post("/webhooks/resend")
async def resend_webhook(request: Request, container: Container = Depends(get_container)) -> dict[str, Any]:
    secret = container.settings.resend_webhook_secret
    if not secret:
        raise HTTPException(404, "not found")
    raw = await request.body()
    if not verify_svix(secret, request.headers, raw):
        raise HTTPException(401, "bad signature")
    return await run_in_threadpool(_resend_event, container, raw)


def _resend_event(container: Container, raw: bytes) -> dict[str, Any]:
    try:
        event = json.loads(raw)
        kind, data = str(event["type"]), event.get("data") or {}
        email_id = str(data.get("email_id") or "")
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, "bad payload") from e
    if not email_id:
        return {"ok": True, "matched": False}
    if kind == "email.received":
        return _inbound(container, data, email_id)
    with container.session_factory() as session:
        filing = session.scalar(select(Filing).where(Filing.external_id == email_id))
        if filing is None:  # a sign-in code or another letter of ours
            return {"ok": True, "matched": False}
        at = str(event.get("created_at") or utcnow().isoformat())
        entry: dict[str, Any] = {"at": at, "type": kind.removeprefix("email."), "source": "resend"}
        bounce = data.get("bounce") or {}
        if isinstance(bounce, dict) and bounce.get("type"):
            entry["bounce"] = str(bounce.get("type"))[:40]
        filing.events = [*(filing.events or []), entry]
        new = EVENT_STATUS.get(kind)
        old = filing.status
        if new and old not in FINAL and not (new == "sent" and old == "delivered"):
            filing.status = new
            if new == "delivered":
                filing.delivered_at = utcnow()
        case = session.get(Case, filing.case_id)
        if case is not None and filing.status != old:
            container.engine.audit(session, case, "resend", f"email_{filing.status}", filing=str(filing.id))
            if filing.status in ("delivered", "bounced"):
                action = session.get(Action, filing.action_id)
                engine = container.engine
                title = engine.pack_of(case).localized(engine.scenario_of(case).action(action.action_id).title,
                                                       case.language) if action else ""
                engine.notifier.notify(session, case, "delivery",
                                       _texts(case.language)[filing.status].format(title=title, to=filing.recipient))
        session.commit()
        return {"ok": True, "matched": True, "status": filing.status}


TOKEN_IN_ADDRESS = re.compile(r"\+([0-9a-f]{6,16})@", re.IGNORECASE)
TOKEN_IN_SUBJECT = re.compile(r"\[K-([0-9a-f]{6,16})\]", re.IGNORECASE)


def _inbound(container: Container, data: dict[str, Any], email_id: str) -> dict[str, Any]:
    """A reply of the other side to claims+<token>@… (Resend «email.received», CLAIMS_INBOUND): a copy goes into
    the case as a response document, the sending is marked «ответили», the client is told."""
    if not container.settings.claims_inbound:
        return {"ok": True, "matched": False}
    rcpt = " ".join(str(x) for key in ("to", "cc") for x in (data.get(key) or []) if x)
    m = TOKEN_IN_ADDRESS.search(rcpt) or TOKEN_IN_SUBJECT.search(str(data.get("subject") or ""))
    if not m:
        return {"ok": True, "matched": False}
    sender = str(data.get("from") or "")[:200]
    with container.session_factory() as session:
        filing = session.scalar(select(Filing).where(Filing.reply_token == m.group(1).lower()))
        if filing is None:
            return {"ok": True, "matched": False}
        if any(e.get("id") == email_id for e in filing.events or []):
            return {"ok": True, "matched": True, "status": filing.status}  # the same webhook again
        now = utcnow()
        filing.replied_at = filing.replied_at or now
        filing.events = [*(filing.events or []), {"at": now.isoformat(), "type": "replied", "source": "resend",
                                                  "id": email_id, "from": sender}]
        case = session.get(Case, filing.case_id)
        engine = container.engine
        text = str(data.get("text") or "")
        fetch = getattr(container.claims_mailer, "received", None)
        if not text and fetch is not None:
            try:
                text = fetch(email_id) or ""
            except Exception as e:  # noqa: BLE001 — the reply is still marked; the text is in the client's mail
                log.warning("inbound: could not fetch the reply: %s", e.__class__.__name__)
        body = f"From: {sender}\nSubject: {data.get('subject') or ''}\n\n{text}".strip()
        engine.add_evidence(session, case, kind="response", filename=f"reply-{now:%Y%m%d-%H%M}.txt",
                            content_type="text/plain", data=body.encode())
        action = session.get(Action, filing.action_id)
        title = engine.pack_of(case).localized(engine.scenario_of(case).action(action.action_id).title,
                                               case.language) if action else ""
        engine.audit(session, case, "resend", "email_replied", filing=str(filing.id))
        engine.notifier.notify(session, case, "delivery",
                               _texts(case.language)["replied"].format(title=title, sender=sender))
        session.commit()
        return {"ok": True, "matched": True, "status": filing.status, "replied": True}


@router.post("/cases/{case_id}/actions/{action_id}/copy-to-me")
def copy_to_me(case_id: uuid.UUID, action_id: uuid.UUID, user: User = Depends(current_user),
               session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict[str, Any]:
    """Owner 02.10: «Копию мне на e-mail» — the document (PDF and Word) to the client's own confirmed e-mail. Only an
    address confirmed by a code is used (User.email is set by the sign-in), so a copy never goes to someone else."""
    case = load_case(case_id, session, user)
    action = session.get(Action, action_id)
    if action is None or action.case_id != case.id or not action.docx_key:
        raise _http(404, "not_found")
    if action.status not in ("ready", "submitted", "responded") or not container.engine.document_unlocked(case, action):
        raise _http(409, "payment_required")
    owner = session.get(User, case.owner_id)
    to = (owner.email or "").strip() if owner else ""
    if not to:
        raise _http(422, "email_required")  # the page offers to confirm an e-mail first
    mailer = container.claims_mailer
    if mailer is None:
        raise _http(503, "email_unavailable")
    storage = container.engine.storage
    files = [(f"{action.action_id}.docx", storage.get(action.docx_key))]
    if action.pdf_key:
        files.insert(0, (f"{action.action_id}.pdf", storage.get(action.pdf_key)))
    pack = container.engine.pack_of(case)
    lang = pack.lang(case.language)
    title = pack.localized(container.engine.scenario_of(case).action(action.action_id).title, lang)
    text = pack.t(lang, "copy_to_me.text", title=title,
                  default=f"Ваш документ «{title}» во вложении: PDF для печати и Word для правок.\n\nKonsiliér AI")
    try:
        mailer.send_letter(to=to, subject=pack.t(lang, "copy_to_me.subject", title=title, default=title),
                           text=text, attachments=files, idempotency_key=f"copy-{action.id}-{int(time.time() // 60)}")
    except SendError as e:
        raise _http(502, "send_failed") from e
    container.engine.audit(session, case, f"user:{user.id}", "copy_to_me", action=action.action_id)
    session.flush()
    return {"sent_to": to}
