"""The check of every document before it is given (PM 02.10, owner: «грубые ошибки в документах»). Run on the
finished text, before the DOCX/PDF is stored; a document that fails is not given:

1. markers left in the text: [square brackets], the pack's lawyer markers («уточнит юрист», «рассчитает юрист») and
   forbidden phrases («Проверьте данные перед подачей»);
2. the applicant's own name in the place of the other side (seller, employer, landlord, bank);
3. empty requisites: the addressee, the other side's name, the applicant's name (the signature), a required sum or date;
4. one norm or sentence repeated twice in a row.

Each problem says whether the client can answer it (a field to fill — the client is asked that one field) or only a
lawyer can (the document goes to the lawyer's check instead of the client)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

BRACKETS = re.compile(r"\[[^\[\]\n]{1,120}\]")
_SPACE = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.;!?])\s+|\n+")


@dataclass(frozen=True)
class Problem:
    kind: str           # marker | swapped_party | empty | repeated
    detail: str
    field: str | None = None  # the field the client fills to fix it; None → only a lawyer can

    @property
    def client_can_fix(self) -> bool:
        return self.field is not None


def _norm(s: Any) -> str:
    return _SPACE.sub(" ", str(s or "")).strip().lower().replace("ё", "е")


def markers(text: str, words: tuple[str, ...]) -> list[Problem]:
    out = [Problem("marker", m.group(0)) for m in BRACKETS.finditer(text)]
    low = _norm(text)
    out += [Problem("marker", w) for w in words if w and _norm(w) in low]
    return out


def swapped_parties(parties: dict[str, dict[str, Any]], fields: dict[str, dict[str, str]]) -> list[Problem]:
    """The applicant's name printed as another party's (seller, landlord…): that party's name field is asked again."""
    me = _norm(parties.get("applicant", {}).get("name"))
    if not me:
        return []
    return [Problem("swapped_party", f"{role}: {p.get('name')}", fields.get(role, {}).get("name"))
            for role, p in parties.items() if role != "applicant" and _norm(p.get("name")) == me]


def empty_requisites(addressee: dict[str, Any], parties: dict[str, dict[str, Any]],
                     fields: dict[str, dict[str, str]], required: dict[str, Any]) -> list[Problem]:
    out: list[Problem] = []
    if not _norm(addressee.get("name")):
        out.append(Problem("empty", "addressee", fields.get("respondent", {}).get("name")))
    for role, p in parties.items():
        if not _norm(p.get("name")):
            out.append(Problem("empty", f"{role}.name", fields.get(role, {}).get("name")))
    out += [Problem("empty", name, name) for name, value in required.items() if not _norm(value)]
    return out


def repeated(text: str, norm_words: tuple[str, ...]) -> list[Problem]:
    """The same norm or law cited twice in a row (a sentence naming one of the pack's norm words)."""
    parts = [_norm(p) for p in _SENTENCE.split(text) if _norm(p)]
    words = tuple(_norm(w) for w in norm_words if w)
    return [Problem("repeated", a[:120]) for a, b in zip(parts, parts[1:])
            if a == b and any(w in a for w in words) and "__" not in a and not a.startswith("☐")]  # a form's rows


def check(text: str, *, words: tuple[str, ...], norm_words: tuple[str, ...] = (), addressee: dict[str, Any], parties: dict[str, dict[str, Any]],
          fields: dict[str, dict[str, str]], required: dict[str, Any]) -> list[Problem]:
    found = [*swapped_parties(parties, fields), *empty_requisites(addressee, parties, fields, required),
             *markers(text, words), *repeated(text, norm_words)]
    # the client is asked one thing: what they can fix first, then the rest
    return sorted(found, key=lambda p: not p.client_can_fix)
