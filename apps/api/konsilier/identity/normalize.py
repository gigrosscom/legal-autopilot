from __future__ import annotations

import hashlib
import hmac
import re

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")


class InvalidIdentifier(ValueError):
    pass


def keyed_hash(secret: str, kind: str, value: str) -> str:
    return hmac.new(secret.encode(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def email(value: str) -> str:
    v = value.strip().lower()
    if not EMAIL_RE.match(v):
        raise InvalidIdentifier("email")
    return v


def phone(value: str, default_country_code: str = "7") -> str:
    """E.164 digits with a leading '+'. With country code 7, local forms (8 701…, 701…) become +7…."""
    digits = re.sub(r"\D", "", value)
    if value.strip().startswith("+"):
        pass
    elif len(digits) == 11 and digits.startswith("8") and default_country_code == "7":
        digits = "7" + digits[1:]
    elif len(digits) == 10 and default_country_code == "7":
        digits = "7" + digits
    if not 10 <= len(digits) <= 15:
        raise InvalidIdentifier("phone")
    return "+" + digits


def iin(value: str) -> str:
    v = re.sub(r"\D", "", value or "")
    if len(v) != 12:
        raise InvalidIdentifier("iin")
    return v


def mask_email(v: str) -> str:
    name, _, domain = v.partition("@")
    return f"{name[:1]}•••@{domain}"


def mask_phone(v: str) -> str:
    return f"{v[:2]}•••••{v[-4:]}"


def mask_iin(v: str) -> str:
    return f"••••••••{v[-4:]}"
