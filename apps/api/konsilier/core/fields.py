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


_MULT = re.compile(r"(\d)\s*(тыс\w*|т\.|млн\w*|мың|млн)", re.IGNORECASE)


def parse_money(raw: Any) -> Decimal:
    mult = Decimal(1)
    m = _MULT.search(str(raw))  # «450 тыс» is 450 000, not 450 (PM 02.10)
    if m:
        mult = Decimal(1_000_000) if m.group(2).lower().startswith("млн") else Decimal(1000)
        raw = str(raw)[:m.start(2)]
    s = re.sub(r"[^\d.,]", "", str(raw)).replace(",", ".")
    if s.count(".") > 1:  # "1.500.000" → thousands separators
        s = s.replace(".", "")
    try:
        value = Decimal(s)
    except InvalidOperation as e:
        raise FieldError("money") from e
    value *= mult
    if value <= 0:
        raise FieldError("money")
    return value.quantize(Decimal("0.01"))


_MONEY_IN_TEXT = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[ \u00a0]\d{3})+|\d+(?:[.,]\d+)?)\s*(тыс\w*|т\.|млн\w*|мың)?\s*(тенге|тг\b|₸|kzt)?",
    re.IGNORECASE)
_DATE_IN_TEXT = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?:\.(\d{4}|\d{2}))?(?![\d.]*\d{3})")
_MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8, "сентябр": 9,
           "октябр": 10, "ноябр": 11, "декабр": 12}
_DATE_WORDS = re.compile(r"(?<!\d)(\d{1,2})\s+(январ\w*|феврал\w*|март\w*|апрел\w*|ма[яй]\w*|июн\w*|июл\w*|август\w*|"
                         r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)(?:\s+(\d{4}))?", re.IGNORECASE)


def money_in_text(text: str) -> Decimal | None:
    """The sum a person wrote in plain words: «ущерб примерно 450 000 тенге», «450 тыс», «450000 ₸». A number with a
    currency or «тыс/млн» wins; else the largest bare number from 1 000 that is not a year, a date or a phone."""
    marked, bare = [], []
    for m in _MONEY_IN_TEXT.finditer(text or ""):
        num, mult, cur = m.group(1), m.group(2), m.group(3)
        try:
            value = parse_money(num + (f" {mult}" if mult else ""))
        except FieldError:
            continue
        if mult or cur:
            marked.append(value)
        elif value >= 1000 and not (1900 <= value <= 2100 and " " not in num) and len(re.sub(r"\D", "", num)) < 10:
            bare.append(value)
    return marked[0] if marked else (max(bare) if bare else None)


def date_in_text(text: str, today: date) -> date | None:
    """«25.09», «25.09.2026», «25 сентября»: the year is this one unless that lands in the future."""
    for m in _DATE_IN_TEXT.finditer(text or ""):
        day, month, year = int(m[1]), int(m[2]), m[3]
        y = (int(year) + 2000 if len(year) == 2 else int(year)) if year else today.year
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        return d.replace(year=y - 1) if not year and d > today else d
    for m in _DATE_WORDS.finditer(text or ""):
        month = next(v for k, v in _MONTHS.items() if m[2].lower().startswith(k))
        y = int(m[3]) if m[3] else today.year
        try:
            d = date(y, month, int(m[1]))
        except ValueError:
            continue
        return d.replace(year=y - 1) if not m[3] and d > today else d
    return None


def looks_like_address(value: str) -> bool:
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
