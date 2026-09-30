"""PaymentAdapter: how a document is paid for.

- ``stub`` (tests, development): every invoice is paid at once.
- ``manual_transfer``: the person transfers the amount to the Kaspi number shown on the payment screen and writes
  the invoice's payment code in the transfer comment; an operator of the clients desk confirms receipt in /ops.
  Recipient and number come from the environment (PAYMENT_RECIPIENT_NAME, PAYMENT_KASPI_PHONE) and are never
  stored in the code. With either missing, payment is unavailable and documents are not issued.

Ways to pay (PAYMENT_METHODS, off by default — docs/kaspi-pay-plan.md). Kaspi has no public payment API: the
company's Kaspi Pay app gives a payment link, a printed (static) Kaspi QR and bills to a client's phone number, all
without an API. So every way below ends the same as the transfer: the person presses «Оплатить» (or asks for a
Kaspi bill), the clients desk sees the payment in Kaspi Pay (or the bank statement) and confirms it in /ops.

- ``kaspi_transfer`` — the transfer above (on whenever the recipient and number are set);
- ``kaspi_link`` — the «Ссылка для оплаты» of the Kaspi Pay app (PAYMENT_KASPI_PAY_LINK): the person opens it,
  enters the amount and writes the payment code in the message to the seller;
- ``kaspi_qr`` — the printed Kaspi QR of the point of sale (PAYMENT_KASPI_QR_IMAGE, an image URL): scanned in the
  Kaspi.kz app, the same amount and message;
- ``kaspi_invoice`` — the person gives their Kaspi number; the desk sends a bill for the exact amount from the Kaspi
  Pay app (Удалённая оплата → Выставить счёт; it lives 24 hours); the person pays it in Kaspi.kz;
- ``bank_invoice`` — «Счёт на оплату» (PDF) with the company's requisites (PAYMENT_LLP_*) for a company or an
  individual entrepreneur paying from its bank account.

With Kaspi Касса connected in the Kaspi Pay app, Kaspi sends the fiscal receipt for the three Kaspi Pay ways itself.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

# no 0/O, 1/I/L: the code is read from a phone screen and typed into a banking app
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

WAYS = ("kaspi_transfer", "kaspi_link", "kaspi_qr", "kaspi_invoice", "bank_invoice")


def new_payment_code(prefix: str = "") -> str:
    body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
    prefix = "".join(ch for ch in prefix.strip().upper() if ch.isalnum())[:8]
    return f"{prefix}-{body}" if prefix else body


def kz_phone(raw: str | None) -> str | None:
    """+7XXXXXXXXXX for a +7-zone mobile number (the Kaspi app's numbers) written any usual way (8 700…,
    +7 (700)…, 700…); else None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10 or digits[0] != "7":
        return None
    return "+7" + digits


def valid_bin(raw: str | None) -> str | None:
    """A 12-digit company / person tax number, spaces removed; None when it is not 12 digits."""
    digits = re.sub(r"\s", "", raw or "")
    return digits if re.fullmatch(r"\d{12}", digits) else None


@dataclass
class Invoice:
    id: str  # the payment code the payer writes in the transfer comment
    amount: Decimal
    currency: str | None
    status: str  # pending | paid


@dataclass
class Requisites:
    """The seller's bank requisites for «Счёт на оплату» (PAYMENT_LLP_*; values only in the server's .env)."""
    name: str = ""
    bin: str = ""
    address: str = ""
    bank: str = ""
    iik: str = ""  # IBAN KZ…
    bik: str = ""
    kbe: str = "17"
    knp: str = "859"
    director: str = ""
    vat: bool = False  # a VAT payer: the bill shows «в т. ч. НДС»; otherwise «Без НДС»
    due_days: int = 5

    def complete(self) -> bool:
        return all((self.name, self.bin, self.bank, self.iik, self.bik))


class PaymentAdapter(Protocol):
    method: str

    def available(self) -> bool: ...

    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice: ...

    def details(self) -> dict[str, Any]: ...

    def way_available(self, way: str) -> bool: ...


class StubPaymentAdapter:
    method = "stub"
    requisites = Requisites()

    def available(self) -> bool:
        return True

    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice:
        return Invoice(id=f"stub-{secrets.token_hex(4)}", amount=amount, currency=currency, status="paid")

    def details(self) -> dict[str, Any]:
        return {}

    def way_available(self, way: str) -> bool:
        return False


class ManualTransferPaymentAdapter:
    """Transfer to a Kaspi number (and, when switched on, the other ways above); the invoice waits for the operator's
    confirmation."""

    method = "manual_transfer"

    def __init__(self, *, recipient_name: str | None, kaspi_phone: str | None, comment_prefix: str | None = None,
                 ways: str | list[str] | None = None, kaspi_pay_link: str | None = None,
                 kaspi_qr_image: str | None = None, requisites: Requisites | None = None):
        self.recipient_name = (recipient_name or "").strip()
        self.kaspi_phone = (kaspi_phone or "").strip()
        self.comment_prefix = (comment_prefix or "").strip()
        if isinstance(ways, str):
            ways = [w.strip().lower() for w in ways.split(",")]
        self.ways = [w for w in WAYS if w in (ways or []) and w != "kaspi_transfer"]
        self.kaspi_pay_link = (kaspi_pay_link or "").strip()
        self.kaspi_qr_image = (kaspi_qr_image or "").strip()
        self.requisites = requisites or Requisites()

    def _transfer(self) -> bool:
        return bool(self.recipient_name and self.kaspi_phone)

    def way_available(self, way: str) -> bool:
        if way == "kaspi_transfer":
            return self._transfer()
        if way not in self.ways:
            return False
        if way == "kaspi_link":
            return self.kaspi_pay_link.startswith("https://")
        if way == "kaspi_qr":
            return bool(self.kaspi_qr_image)
        if way == "bank_invoice":
            return self.requisites.complete()
        return True  # kaspi_invoice: the desk sends the bill from the Kaspi Pay app

    def open_ways(self) -> list[str]:
        return [w for w in WAYS if self.way_available(w)]

    def available(self) -> bool:
        return bool(self.open_ways())

    def create_invoice(self, *, case_id: str, amount: Decimal, currency: str | None) -> Invoice:
        if not self.available():
            raise RuntimeError("manual transfer payment is not configured")
        return Invoice(id=new_payment_code(self.comment_prefix), amount=amount, currency=currency, status="pending")

    def details(self) -> dict[str, Any]:
        """What the payment screen shows. Without PAYMENT_METHODS: the transfer details only, as before."""
        view: dict[str, Any] = {}
        if self._transfer():
            view.update(recipient_name=self.recipient_name, kaspi_phone=self.kaspi_phone)
        if not self.ways:
            return view
        ways: list[dict[str, Any]] = []
        for w in self.open_ways():
            item: dict[str, Any] = {"id": w}
            if w == "kaspi_link":
                item["url"] = self.kaspi_pay_link
            elif w == "kaspi_qr":
                item["image"] = self.kaspi_qr_image
                if self.kaspi_pay_link.startswith("https://"):
                    item["url"] = self.kaspi_pay_link
            elif w == "bank_invoice":
                item["seller"] = self.requisites.name
            ways.append(item)
        view["ways"] = ways
        return view


def requisites_from(settings: Any) -> Requisites:
    return Requisites(
        name=(getattr(settings, "payment_llp_name", "") or "").strip(),
        bin=(getattr(settings, "payment_llp_bin", "") or "").strip(),
        address=(getattr(settings, "payment_llp_address", "") or "").strip(),
        bank=(getattr(settings, "payment_llp_bank", "") or "").strip(),
        iik=(getattr(settings, "payment_llp_iik", "") or "").replace(" ", "").strip(),
        bik=(getattr(settings, "payment_llp_bik", "") or "").strip(),
        kbe=(getattr(settings, "payment_llp_kbe", "") or "17").strip(),
        knp=(getattr(settings, "payment_llp_knp", "") or "859").strip(),
        director=(getattr(settings, "payment_llp_director", "") or "").strip(),
        vat=bool(getattr(settings, "payment_llp_vat", False)),
        due_days=int(getattr(settings, "payment_invoice_due_days", 5) or 5))


def build_payments(settings: Any) -> PaymentAdapter:
    mode = (getattr(settings, "payment_mode", "") or "").strip().lower()
    if mode == "stub":
        return StubPaymentAdapter()
    # any other value (manual_transfer, empty, a typo) → manual transfer: documents are never free by mistake
    return ManualTransferPaymentAdapter(recipient_name=settings.payment_recipient_name,
                                        kaspi_phone=settings.payment_kaspi_phone,
                                        comment_prefix=settings.payment_comment_prefix,
                                        ways=getattr(settings, "payment_methods", ""),
                                        kaspi_pay_link=getattr(settings, "payment_kaspi_pay_link", ""),
                                        kaspi_qr_image=getattr(settings, "payment_kaspi_qr_image", ""),
                                        requisites=requisites_from(settings))
