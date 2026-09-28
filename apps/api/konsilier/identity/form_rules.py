"""Field rules for the people-facing forms (lawyer application, client request to a lawyer).

Each check returns an error *code* (or None); the API sends {field: code} and the site shows its own text for
the code. The same rules live in apps/web/lib/formRules.ts — keep the two in step.
"""

from __future__ import annotations

import re

# Letters of the Cyrillic (incl. the extra letters Ә Ғ Қ Ң Ө Ұ Ү Һ І) and Latin alphabets, incl. Latin with diacritics.
_LETTER = "A-Za-zÀ-ÖØ-öø-ɏА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі"
_APOS = "'’ʼ`"
_NAME_WORD = re.compile(rf"^[{_LETTER}]+(?:[-{_APOS}][{_LETTER}]+)*$")
_NAME_CHARS = re.compile(rf"^[{_LETTER}\s\-{_APOS}]+$")
_CITY = re.compile(rf"^[{_LETTER}]+(?:[\s\-.{_APOS}]+[{_LETTER}]+)*\.?$")
_LICENSE = re.compile(rf"^[0-9{_LETTER}№#/\-. ]+$")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)*\.[^\s@.]{2,}$")
_PHONE_CHARS = re.compile(r"^\+?[\d\s()\-.]+$")

LICENSED_KINDS = ("advocate", "legal_consultant")
LAWYER_KINDS = ("advocate", "legal_consultant", "human_rights")


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def check_full_name(value: str | None) -> str | None:
    v = clean(value)
    if not v:
        return "required"
    if len(v) < 2 or len(v) > 100:
        return "name_length"
    if not _NAME_CHARS.match(v):
        return "name_chars"  # digits, dots, other symbols
    words = v.split(" ")
    if not all(_NAME_WORD.match(w) for w in words):
        return "name_chars"  # a hyphen or apostrophe hanging on its own
    if sum(1 for w in words if len(re.sub(f"[-{_APOS}]", "", w)) >= 2) < 2:
        return "name_words"  # surname and given name, in full
    return None


def normalize_kz_phone(value: str | None) -> tuple[str | None, str | None]:
    """(+7XXXXXXXXXX, None) or (None, error code). Accepts 8…, +7…, 7…, and spaces/brackets/dashes."""
    v = (value or "").strip()
    if not v:
        return None, "required"
    if not _PHONE_CHARS.match(v):
        return None, "phone_format"
    digits = re.sub(r"\D", "", v)
    if v.startswith("+"):
        if not digits.startswith("7") or len(digits) != 11:
            return None, "phone_format"
        rest = digits[1:]
    elif len(digits) == 11 and digits[0] in "78":
        rest = digits[1:]
    elif len(digits) == 10:
        rest = digits
    else:
        return None, "phone_format"
    if rest[0] != "7":  # +7 7xx … is the KZ numbering; +7 9xx, +7 4xx belong to RU
        return None, "phone_operator"
    return "+7" + rest, None


def check_email(value: str | None, required: bool = False) -> str | None:
    v = (value or "").strip()
    if not v:
        return "required" if required else None
    if len(v) > 200 or not _EMAIL.match(v):
        return "email_format"
    return None


def check_city(value: str | None) -> str | None:
    v = clean(value)
    if not v:
        return "required"
    if len(v) < 2 or len(v) > 100 or not _CITY.match(v):
        return "city_format"
    return None


def check_license(value: str | None, kind: str | None) -> str | None:
    v = clean(value)
    if not v:
        return "required" if kind in LICENSED_KINDS else None
    if len(v) < 2 or len(v) > 40 or not _LICENSE.match(v) or not re.search(r"\d", v):
        return "license_format"
    return None

