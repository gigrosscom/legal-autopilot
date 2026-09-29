"""PaymentAdapter: how a document is paid for.

- ``stub`` (tests, development): every invoice is paid at once.
- ``manual_transfer``: the person transfers the amount to the Kaspi number shown on the payment screen and writes
  the invoice's payment code in the transfer comment; an operator of the clients desk confirms receipt in /ops.
  Recipient and number come from the environment (PAYMENT_RECIPIENT_NAME, PAYMENT_KASPI_PHONE) and are never
  stored in the code. With either missing, payment is unavailable and documents are not issued.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

# no 0/O, 1/I/L: the code is read from a phone screen and typed into a banking app
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def new_payment_code(prefix: str = "") -> str:
    body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
    prefix = "".join(ch for ch in prefix.strip().upper() if ch.isalnum())[:8]
    return f"{prefix}-{body}" if prefix else body


@dataclass
class Invoice:
    id: str  # the payment code the payer writes in the transfer comment
    amount: Decimal
    currency: str | None
    status: str  # pending | paid


class PaymentAdapter(Protocol):
    method: str

    def available(self) -> bool: ...

    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice: ...

    def details(self) -> dict[str, Any]: ...


class StubPaymentAdapter:
    method = "stub"

    def available(self) -> bool:
        return True

    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice:
        return Invoice(id=f"stub-{secrets.token_hex(4)}", amount=amount, currency=currency, status="paid")

    def details(self) -> dict[str, Any]:
        return {}


class ManualTransferPaymentAdapter:
    """Transfer to a Kaspi number; the invoice waits for the operator's confirmation."""

    method = "manual_transfer"

    def __init__(self, *, recipient_name: str | None, kaspi_phone: str | None, comment_prefix: str | None = None):
        self.recipient_name = (recipient_name or "").strip()
        self.kaspi_phone = (kaspi_phone or "").strip()
        self.comment_prefix = (comment_prefix or "").strip()

    def available(self) -> bool:
        return bool(self.recipient_name and self.kaspi_phone)

    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice:
        if not self.available():
            raise RuntimeError("manual transfer payment is not configured")
        return Invoice(id=new_payment_code(self.comment_prefix), amount=amount, currency=currency, status="pending")

    def details(self) -> dict[str, Any]:
        if not self.available():
            return {}
        return {"recipient_name": self.recipient_name, "kaspi_phone": self.kaspi_phone}


def build_payments(settings: Any) -> PaymentAdapter:
    mode = (getattr(settings, "payment_mode", "") or "").strip().lower()
    if mode == "stub":
        return StubPaymentAdapter()
    # any other value (manual_transfer, empty, a typo) → manual transfer: documents are never free by mistake
    return ManualTransferPaymentAdapter(recipient_name=settings.payment_recipient_name,
                                        kaspi_phone=settings.payment_kaspi_phone,
                                        comment_prefix=settings.payment_comment_prefix)
