"""Kaspi Pay pushes from the payments phone (konsilier/kaspi_parse.py): the endpoint MacroDroid posts to, matching a push to
a bill, the 15-minute reminder and the desk's «Kaspi: не найдено» list in /ops.

POST /v1/payments/kaspi/push — 404 while PAYMENT_KASPI_PUSH_TOKEN is empty; 401 without the token in X-Konsilier-Token.
Body: JSON {"title", "text", "posted_at"?}, a form with the same fields, or plain text — anything, at most MAX_BODY
bytes. The answer comes at once: the bill is marked paid and the client's «Оплата получена» written in the same
request; e-mail, SMS, push and the document itself follow right after the commit."""

from __future__ import annotations

import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..container import Container
from .. import kaspi_parse as kp
from ..core.models import Case, Invoice, KaspiPush, User, utcnow
from ..team import notify_team
from .background import after_commit
from .deps import get_container, get_session
from .ops import _test_users, decide_invoice, invoice_view, operator

router = APIRouter(prefix="/v1")
log = logging.getLogger(__name__)

MAX_BODY = 16_384
ACTOR = "kaspi:push"
ALMATY = timezone(timedelta(hours=5))


# ------------------------------------------------------------------ the phone
@router.post("/payments/kaspi/push")
async def kaspi_push(request: Request, container: Container = Depends(get_container)) -> dict[str, Any]:
    token = container.settings.payment_kaspi_push_token
    if not token:
        raise HTTPException(404, "not found")
    if not hmac.compare_digest(request.headers.get("X-Konsilier-Token", "").encode(), token.encode()):
        raise HTTPException(401, "bad token")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY:
            break
    body = bytes(raw[:MAX_BODY]).decode("utf-8", errors="replace")
    ctype = request.headers.get("content-type", "")
    title, text, posted_at = read_body(body, ctype)
    return await run_in_threadpool(handle_push, container, title, text, posted_at, body, ctype[:100])


def read_body(body: str, ctype: str) -> tuple[str | None, str, str | None]:
    """(title, text, posted_at) from whatever the phone sent. MacroDroid pastes the notification into the JSON as is,
    so a quote or a line break in it breaks the JSON: then the fields are cut out by hand, else the body is the text."""
    def pick(d: dict[str, Any], *keys: str) -> str | None:
        for k in keys:
            v = d.get(k)
            if isinstance(v, list):
                v = v[0] if v else None
            if v not in (None, ""):
                return str(v)
        return None

    fields: dict[str, Any] | None = None
    if "x-www-form-urlencoded" in ctype:
        fields = parse_qs(body, keep_blank_values=True)
    else:
        try:
            data = json.loads(body, strict=False)
        except ValueError:
            data = None
        if isinstance(data, dict):
            fields = data
        elif isinstance(data, str):
            return None, data, None
        elif body.lstrip().startswith("{"):
            m = re.search(r'"title"\s*:\s*"(.*?)"\s*,\s*"text"\s*:\s*"(.*)"\s*(?:,\s*"posted_at"\s*:\s*"(.*?)"\s*)?}\s*$',
                          body, re.S)
            if m:
                return m.group(1), m.group(2), m.group(3)
    if fields is not None:
        text = pick(fields, "text", "notification", "message", "body", "big_text") or ""
        return pick(fields, "title", "notification_title"), text, pick(fields, "posted_at", "time", "timestamp")
    return None, body, None


def handle_push(container: Container, title: str | None, text: str, posted_at: str | None, raw: str,
                ctype: str) -> dict[str, Any]:
    now = utcnow()
    parsed = kp.parse(title, text)
    row = dict(received_at=now, title=(title or "")[:500] or None, text=text, posted_at=(posted_at or "")[:64] or None,
               raw=raw, content_type=ctype or None, amount=parsed.amount, payer=(parsed.payer or "")[:200] or None,
               candidates=[])
    dig = kp.digest(title, text, posted_at, now)
    with container.session_factory() as session:
        first = session.scalar(select(KaspiPush.id).where(KaspiPush.digest == dig))
        if first is None:
            push = KaspiPush(digest=dig, status="unmatched", **row)
            session.add(push)
            try:
                session.flush()
            except IntegrityError:  # the same push at the same instant: the other request has it
                session.rollback()
                first = session.scalar(select(KaspiPush.id).where(KaspiPush.digest == dig))
        if first is not None:
            session.add(KaspiPush(status="duplicate", duplicate_of=first, **row))
            session.commit()
            return {"ok": True, "status": "duplicate", "duplicate_of": first}
        if not parsed.incoming or parsed.amount is None:
            push.status = "ignored"
            session.commit()
            return {"ok": True, "status": "ignored", "id": push.id}
        found = kp.candidates(session, container.engine, parsed.amount, now)
        if len(found) == 1:
            confirm(session, container, push, found[0], ACTOR, now)
            session.commit()
            return {"ok": True, "status": "matched", "id": push.id, "invoice": found[0].code}
        push.status = "ambiguous" if found else "unmatched"
        push.candidates = [candidate_view(session, inv) for inv in found]
        recent_paid = recently_paid(session, container, parsed.amount, now)
        after_commit(session, container, lambda _s, p=push_view(push), r=recent_paid: tell_desk(container, p, r),
                     "kaspi-push-desk")
        session.commit()
        return {"ok": True, "status": push.status, "id": push.id, "candidates": len(found)}


def confirm(session: Session, container: Container, push: KaspiPush, inv: Invoice, by: str, now: datetime) -> None:
    """The push is this bill's payment: «Оплата получена» like the desk's button — paid and the client's message
    now, the e-mails / SMS / push and the document right after the commit."""
    note = f"Kaspi Pay push #{push.id}: {(push.text or '')[:300]}"
    with container.engine.notifier.deferred() as later:
        if inv.status != "paid":
            decide_invoice(session, container, inv.id, by, True, note, later=later)
    push.status, push.invoice_id, push.decided_by, push.decided_at = "matched", inv.id, by, now
    push.candidates = []
    if later:
        def send(s: Session) -> None:
            for job in later:
                try:
                    job(s)
                except Exception:  # noqa: BLE001 — one failed letter never stops the rest
                    log.exception("kaspi push: a notification failed")
        after_commit(session, container, send, "kaspi-push-notify")


def candidate_view(session: Session, inv: Invoice) -> dict[str, Any]:
    owner = session.get(User, inv.user_id)
    return {"id": inv.id, "code": inv.code, "amount": float(inv.amount), "purpose": inv.purpose,
            "case_id": str(inv.case_id) if inv.case_id else None,
            "claimed_at": inv.claimed_at.isoformat() if inv.claimed_at else None,
            "client": (owner.email or owner.phone) if owner else None}


def recently_paid(session: Session, container: Container, amount: Decimal, now: datetime) -> list[str]:
    """Bills of this amount the desk already marked paid in the window — a push that came after the desk."""
    since = now - kp.MATCH_WINDOW
    rows = session.scalars(select(Invoice).where(Invoice.status == "paid", Invoice.decided_at >= since,
                                                 Invoice.pay_way.in_(container.engine.KASPI_WAYS))).all()
    return [i.code for i in rows if Decimal(i.amount).quantize(Decimal("0.01")) == amount]


def _local(d: datetime | None) -> str:
    if d is None:
        return "—"
    d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return d.astimezone(ALMATY).strftime("%d.%m.%Y %H:%M")


def push_view(push: KaspiPush) -> dict[str, Any]:
    return {"id": push.id, "received_at": push.received_at.isoformat() if push.received_at else None,
            "title": push.title, "text": push.text, "posted_at": push.posted_at,
            "amount": float(push.amount) if push.amount is not None else None, "payer": push.payer,
            "status": push.status, "candidates": push.candidates or [], "invoice_id": push.invoice_id,
            "decided_by": push.decided_by, "note": push.note}


def tell_desk(container: Container, p: dict[str, Any], recent_paid: list[str]) -> None:
    """No bill or several bills for a push: the clients desk and PAYMENT_NOTIFY_EMAILS get the push and the
    candidates; the bills wait for the desk («ждёт сверки»)."""
    amount = f"{Decimal(str(p['amount'])):,.0f}".replace(",", " ") + " ₸"
    received = datetime.fromisoformat(p["received_at"]) if p["received_at"] else None
    if p["candidates"]:
        subject = f"Kaspi: оплата {amount} — несколько счетов, выберите вручную"
        lines = [f"Пришла оплата {amount}, а «Оплатить» на эту сумму за последний час нажали несколько клиентов. "
                 f"Автоматически не отмечено: выберите счёт в оперативном центре.", "", "Кандидаты:"]
        lines += [f"• счёт №{c['id']}, код {c['code']}, {c['client'] or 'без контакта'}, «Оплатить» "
                  f"{_local(datetime.fromisoformat(c['claimed_at'])) if c['claimed_at'] else '—'}"
                  + (f", дело {c['case_id']}" if c['case_id'] else "") for c in p["candidates"]]
    else:
        subject = f"Kaspi: оплата {amount} не найдена среди счетов"
        lines = [f"Пришла оплата {amount}, но открытого счёта Kaspi на эту сумму с «Оплатить» за последний час нет. "
                 f"Проверьте в Kaspi Pay и при необходимости отметьте счёт вручную."]
    if recent_paid:
        lines += ["", f"Счета на эту сумму, уже отмеченные оплаченными за час: {', '.join(recent_paid)}."]
    lines += ["", f"Пуш №{p['id']}, получен {_local(received)} (Алматы):",
              f"Заголовок: {p['title'] or '—'}", f"Текст: {p['text'] or '—'}",
              f"Плательщик: {p['payer'] or 'не указан'}", "",
              f"Оперативный центр → «Оплаты документов» → «Kaspi: не найдено»: "
              f"{container.settings.public_site_url.rstrip('/')}/ops"]
    notify_team(container, subject, "\n".join(lines), desk="clients", also=container.settings.payment_notify_emails)


def push_confirms(container: Container, inv: Invoice) -> bool:
    """The pushes are on and this bill is paid into Kaspi Pay: its push confirms it, the desk is not mailed on
    «Оплатить» (only when a push finds no bill or several)."""
    return bool(container.settings.payment_kaspi_push_token and container.engine.config.kaspi_push
                and inv.pay_way in container.engine.KASPI_WAYS)


def match_waiting_push(session: Session, container: Container, inv: Invoice) -> bool:
    """The client pressed «Оплатить» after their payment's push came (it found no bill then): match it now, when
    this bill is its only candidate. True when the bill is paid by it."""
    eng = container.engine
    if not push_confirms(container, inv) or inv.status not in eng.OPEN:
        return False
    now = utcnow()
    amount = Decimal(inv.amount).quantize(Decimal("0.01"))
    for push in session.scalars(select(KaspiPush).where(
            KaspiPush.status == "unmatched", KaspiPush.received_at >= now - kp.MATCH_WINDOW)
            .order_by(KaspiPush.received_at)).all():
        if push.amount is None or Decimal(push.amount).quantize(Decimal("0.01")) != amount:
            continue
        found = kp.candidates(session, eng, amount, now)
        if [i.id for i in found] == [inv.id]:
            confirm(session, container, push, inv, ACTOR, now)
            session.flush()
            return True
        return False
    return False


# ------------------------------------------------------------------ the 15-minute reminder (scheduler)
def reminders(container: Container):
    """Scheduler job: a Kaspi link / QR bill the client pressed «Оплатить» for, with no push 15 minutes later — one
    soft «оплатите, пожалуйста» to the client (owner 01.10). Only while the pushes are on."""
    def job(session: Session, now: datetime) -> int:
        eng = container.engine
        if not (container.settings.payment_kaspi_push_token and eng.config.kaspi_push):
            return 0
        rows = session.scalars(select(Invoice).where(
            Invoice.status == "awaiting_confirmation", Invoice.pay_way.in_(eng.KASPI_WAYS),
            Invoice.pay_reminded_at.is_(None), Invoice.claimed_at.is_not(None),
            Invoice.claimed_at <= now - eng.UNPAID_AFTER, Invoice.claimed_at >= now - timedelta(days=2),
            Invoice.user_id.not_in(_test_users()))).all()
        for inv in rows:
            inv.pay_reminded_at = now
            amount = f"{Decimal(inv.amount):,.0f}".replace(",", " ")
            default = (f"Мы пока не видим оплату {amount} ₸ по ссылке Kaspi Pay (счёт {inv.code}). Если вы ещё не "
                       f"оплатили — оплатите, пожалуйста: следующий документ можно будет оформить после оплаты. "
                       f"Если уже оплатили — напишите нам в поддержку, мы проверим.")
            case = session.get(Case, inv.case_id) if inv.case_id else None
            owner = session.get(User, inv.user_id)
            text = default
            if case is not None:
                pack = eng.pack_of(case)
                text = pack.t(pack.lang(case.language), "notifications.payment_reminder", amount=amount,
                              code=inv.code, default=default)
            if owner is not None:  # the inbox, the channel and push; the letter below, as the desk's letters go
                eng.notifier.notify_user(session, owner, "payment_reminder", text, case=case)
            if owner is not None and owner.email and container.email_sender is not None:
                where = f"{container.settings.public_site_url.rstrip('/')}/" + (
                    f"case/{inv.case_id}" if inv.case_id else "plans")
                try:
                    container.email_sender.send(owner.email, f"Konsilier AI: оплата {inv.code}",
                                                f"{text}\n\n{where}")
                except Exception:  # noqa: BLE001
                    log.warning("payment reminder e-mail failed", exc_info=True)
        return len(rows)
    return job


# ------------------------------------------------------------------ the desk: «Kaspi: не найдено»
@router.get("/ops/clients/payments/kaspi")
def unmatched(all: bool = False, session: Session = Depends(get_session),
              container: Container = Depends(get_container),
              _: User = Depends(operator("clients"))) -> dict[str, Any]:
    """Pushes no bill was matched to (unmatched, ambiguous; ``all`` — every push of 14 days, for tuning the parser)
    and the Kaspi bills whose «Оплатить» no push confirmed within 15 minutes."""
    since = utcnow() - timedelta(days=14)
    q = select(KaspiPush).where(KaspiPush.received_at >= since).order_by(KaspiPush.id.desc()).limit(300)
    if not all:
        q = q.where(KaspiPush.status.in_(("unmatched", "ambiguous")))
    eng = container.engine
    bills = session.scalars(select(Invoice).where(
        Invoice.status.in_(("awaiting_confirmation", "not_found")), Invoice.pay_way.in_(eng.KASPI_WAYS),
        Invoice.claimed_at.is_not(None), Invoice.claimed_at <= utcnow() - eng.UNPAID_AFTER,
        Invoice.user_id.not_in(_test_users())).order_by(Invoice.id.desc()).limit(300)).all()
    return {"enabled": bool(container.settings.payment_kaspi_push_token),
            "pushes": [push_view(p) for p in session.scalars(q).all()],
            "invoices": [invoice_view(session, container, i) for i in bills]}


class PushDecision(BaseModel):
    decision: Literal["match", "dismiss"]
    invoice_id: int | None = None


@router.post("/ops/clients/payments/kaspi/{push_id}")
def decide_push(push_id: int, body: PushDecision, session: Session = Depends(get_session),
                container: Container = Depends(get_container),
                op: User = Depends(operator("clients"))) -> dict[str, Any]:
    """The owner's / desk's hand: «это оплата счёта №…» (the bill is confirmed as by «Оплата получена») or «не наша
    оплата» (the push is put aside)."""
    push = session.get(KaspiPush, push_id)
    if push is None:
        raise HTTPException(404, "push not found")
    if push.status == "matched":
        raise HTTPException(409, {"code": "already_matched", "message": "already_matched"})
    who = op.email or "operator"
    if body.decision == "dismiss":
        push.status, push.decided_by, push.decided_at = "ignored", who, utcnow()
        session.flush()
        return push_view(push)
    inv = session.get(Invoice, body.invoice_id) if body.invoice_id else None
    if inv is None:
        raise HTTPException(404, "invoice not found")
    if inv.status == "cancelled":
        raise HTTPException(409, {"code": "cancelled", "message": "cancelled"})
    confirm(session, container, push, inv, who, utcnow())
    session.flush()
    return push_view(push)
