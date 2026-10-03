"""PaymentAdapter. MVP: a stub that marks every invoice as paid."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass
class Invoice:
    id: str
    amount: Decimal
    currency: str | None
    status: str  # pending | paid


class PaymentAdapter(Protocol):
    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice: ...


class StubPaymentAdapter:
    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice:
        return Invoice(id=f"stub-{uuid.uuid4().hex[:8]}", amount=amount, currency=currency, status="paid")
