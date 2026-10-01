"""Kaspi Pay pushes: confirming a Kaspi link / QR payment without an operator (owner 01.10, «Автоподтверждение Kaspi
без оператора»).

Kaspi has no public API for a small merchant. The company's Kaspi Pay app runs on a separate Android phone; MacroDroid
forwards every notification of the app to POST /v1/payments/kaspi/push (konsilier/api/kaspi_push.py). One Kaspi Pay
link serves every product, the client types the amount, so a payment is matched by AMOUNT and TIME: the open Kaspi
link / QR bills of that amount whose «Оплатить» (the way chosen, or «Я оплатил(а)») was pressed in the last
MATCH_WINDOW. Exactly one → paid at once, as the desk's «Оплата получена». None or several → the bill waits for the
desk (awaiting_confirmation) and the operators get the push with the candidates.

The exact wording of a Kaspi Pay push is not documented, so the parser is lenient (₸ / тг / KZT, «+1990 ₸»,
«1 990 ₸» with ordinary, no-break or thin spaces, decimals) and every push is kept (models.KaspiPush) for tuning.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, Invoice, User

MATCH_WINDOW = timedelta(minutes=60)  # «Оплатить» this long before the push at most

_NUM = r"(?P<sign>[+\-])?\s?(?P<int>\d{1,3}(?:[ .,]\d{3})+|\d+)(?:[.,](?P<frac>\d{1,2}))?(?!\d)"
_CUR = r"(?:₸|тг\b\.?|тенге|kzt\b)"
_AFTER = re.compile(_NUM + r"\s*" + _CUR, re.I)  # «1 990 ₸», «+1990 тг», «1990.00 KZT»
_BEFORE = re.compile(r"(?:₸|kzt)\s*" + _NUM, re.I)  # «KZT 1990»
# a sum that is not the payment: the balance after it, a fee
_NOT_PAYMENT = re.compile(r"(баланс|остаток|доступно|комисси|қалдық)[^\d+\-]{0,20}$", re.I)
# not money coming in
_OUTGOING = re.compile(r"возврат|отмен|списан|вывод|қайтар", re.I)
_UP = "A-ZА-ЯЁӘҒҚҢӨҰҮҺІ"
_PAYER = re.compile(rf"\bот\s+([{_UP}][\w\-]*(?:\s+[{_UP}][\w\-]*\.?){{0,2}})")


@dataclass
class Parsed:
    amount: Decimal | None
    payer: str | None
    incoming: bool  # money came in: a payment to match


def normalize(s: str) -> str:
    """No-break and thin spaces (U+00A0, U+202F, U+2009…) become plain spaces, the minus sign a hyphen."""
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFKC", s or "").replace("−", "-"))


def _amount(m: re.Match[str]) -> Decimal | None:
    whole = re.sub(r"[ .,]", "", m.group("int"))
    try:
        return Decimal(f"{whole}.{m.group('frac') or '0'}").quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse(title: str | None, text: str | None) -> Parsed:
    body = normalize(f"{title or ''}\n{text or ''}")
    found: list[tuple[re.Match[str], Decimal]] = []
    for rx in (_AFTER, _BEFORE):
        for m in rx.finditer(body):
            value = _amount(m)
            if value is not None and value > 0 and not _NOT_PAYMENT.search(body[:m.start()]):
                found.append((m, value))
    found.sort(key=lambda f: f[0].start())
    plus = [f for f in found if f[0].group("sign") == "+"]
    pick = (plus or found or [None])[0]
    payer = _PAYER.search(body)
    if pick is None:
        return Parsed(None, payer.group(1).strip() if payer else None, False)
    incoming = pick[0].group("sign") != "-" and not _OUTGOING.search(body)
    return Parsed(pick[1], payer.group(1).strip() if payer else None, incoming)


def digest(title: str | None, text: str | None, posted_at: str | None, received: datetime) -> str:
    """The same push twice (MacroDroid retries, the app re-posts it): the same text and the same posting time — or,
    when the phone sends no time, the same minute of arrival."""
    when = (posted_at or "").strip() or received.strftime("%Y-%m-%dT%H:%M")
    return hashlib.sha256(f"{normalize(title or '')}\n{normalize(text or '')}\n{when}".encode()).hexdigest()


def _aware(d: datetime) -> datetime:
    from datetime import timezone

    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def candidates(session: Session, engine: Any, amount: Decimal, now: datetime) -> list[Invoice]:
    """Open Kaspi link / QR bills of ``amount`` whose «Оплатить» was pressed within MATCH_WINDOW before ``now``: the
    way chosen («Оплатить в Kaspi», the payment_way audit entry) or «Я оплатил(а)» (claimed_at). Test accounts'
    bills never take a real payment."""
    since = now - MATCH_WINDOW
    opened = {(r.data or {}).get("invoice") for r in session.scalars(select(AuditLog).where(
        AuditLog.event.in_(("payment_way", "payment_claimed")), AuditLog.created_at >= since)).all()}
    opened.discard(None)
    tests = select(User.id).where(User.is_test.is_(True))
    rows = session.scalars(select(Invoice).where(
        Invoice.status.in_(engine.OPEN), Invoice.pay_way.in_(engine.KASPI_WAYS), Invoice.user_id.not_in(tests),
        Invoice.updated_at >= since).order_by(Invoice.id)).all()  # choosing the way or claiming updates the row
    out = []
    for inv in rows:
        if Decimal(inv.amount).quantize(Decimal("0.01")) != amount:
            continue
        claimed = inv.claimed_at is not None and since <= _aware(inv.claimed_at) <= now
        if claimed or inv.code in opened:
            out.append(inv)
    return out
