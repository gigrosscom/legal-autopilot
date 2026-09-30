"""Deterministic normalization/validation of intake values (no LLM here)."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .scenario import IntakeField

_DMY = re.compile(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*$")
_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")
_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


class FieldError(ValueError):
    """``code`` is an i18n key suffix (errors.<code>) so channels can localize it."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def parse_date(raw: Any) -> date:
    if isinstance(raw, date):
        return raw
    s = str(raw)
    m = _ISO.match(s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = _DMY.match(s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    raise FieldError("date")


def parse_money(raw: Any) -> Decimal:
    s = re.sub(r"[^\d.,]", "", str(raw)).replace(",", ".")
    if s.count(".") > 1:  # "1.500.000" → thousands separators
        s = s.replace(".", "")
    try:
        value = Decimal(s)
    except InvalidOperation as e:
        raise FieldError("money") from e
    if value <= 0:
        raise FieldError("money")
    return value.quantize(Decimal("0.01"))


def _looks_like_address(value: str) -> bool:
    """A soft check of a postal address: some words and a house number; not an id number or a name alone."""
    words = re.findall(r"\w+", value)
    has_number = bool(re.search(r"(?<!\d)\d{1,5}(?!\d)", value))  # a house / flat number, not a 12-digit BIN
    return len(words) >= 2 and has_number


def normalize(field: IntakeField, raw: Any, today: date | None = None) -> Any:
    """Return a JSON-serializable normalized value or raise FieldError."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise FieldError("empty")
    if field.type == "date":
        d = parse_date(raw)
        if today and d > today:
            raise FieldError("date_future")
        return d.isoformat()
    if field.type == "money":
        return str(parse_money(raw))
    if field.type == "number":
        try:
            return str(Decimal(str(raw).replace(" ", "").replace(",", ".")))
        except InvalidOperation as e:
            raise FieldError("number") from e
    value = str(raw).strip()
    if field.type == "email" and not _EMAIL.match(value):
        raise FieldError("email")
    if field.pattern:
        compact = re.sub(r"[\s-]", "", value)
        if not re.fullmatch(field.pattern, compact):
            raise FieldError("pattern")
        value = compact
    if field.name.endswith("_address") and field.type in ("text", "string", None) and not _looks_like_address(value):
        raise FieldError("address")  # QA BUG-10: a company name or a BIN given instead of the postal address
    if field.type == "phone":
        digits = re.sub(r"[^\d+]", "", value)
        if len(re.sub(r"\D", "", digits)) < 10:
            raise FieldError("phone")
        value = digits
    return value


def display(field: IntakeField, value: Any) -> str:
    if value is None:
        return ""
    if field.type == "date":
        try:
            return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y")
        except ValueError:
            return str(value)
    if field.type == "money":
        d = Decimal(str(value))
        whole = f"{int(d):,}".replace(",", " ")
        frac = d - int(d)
        return whole if frac == 0 else f"{whole},{int(frac * 100):02d}"
    return str(value)
