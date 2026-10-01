"""PII redaction: personal data never reaches the LLM.

Values are replaced by stable labels (``[PERSON_1]``, ``[ID_NUMBER_1]``) that are
stored per case in our DB and substituted back when documents are assembled.
Two sources of PII:
  * intake fields marked ``pii:`` in the scenario (known exact values);
  * generic patterns (long digit sequences, IBAN-like accounts, e-mails, phones).
Country-specific ID formats are expressed as field ``pattern`` in packs, not here.
"""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("ACCOUNT", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),  # IBAN-like
    ("CARD", re.compile(r"\b(?:\d[ -]?){15,18}\d\b")),
    ("ID_NUMBER", re.compile(r"\b\d{10,14}\b")),  # national ids / tax numbers
    ("PHONE", re.compile(r"(?<!\w)\+\d[\d\s()-]{8,}\d\b")),  # international format
]

_KIND_LABEL = {
    "person": "PERSON",
    "id_number": "ID_NUMBER",
    "account": "ACCOUNT",
    "phone": "PHONE",
    "email": "EMAIL",
    "address": "ADDRESS",
}

LABEL_RE = re.compile(r"\[(?:PERSON|ID_NUMBER|ACCOUNT|CARD|PHONE|EMAIL|ADDRESS)_\d+\]")


class PiiVault:
    """Bidirectional label ↔ value map; serializable into ``Case.pii_map``."""

    def __init__(self, mapping: dict[str, str] | None = None):
        self.mapping: dict[str, str] = dict(mapping or {})

    def _label_for(self, kind: str, value: str) -> str:
        for label, v in self.mapping.items():
            if v == value:
                return label
        n = 1 + sum(1 for label in self.mapping if label.startswith(f"[{kind}_"))
        label = f"[{kind}_{n}]"
        self.mapping[label] = value
        return label

    def register(self, kind: str, value: Any) -> None:
        if value is None:
            return
        value = str(value).strip()
        if len(value) >= 3:
            self._label_for(_KIND_LABEL.get(kind, kind.upper()), value)

    def redact(self, text: str | None) -> str:
        if not text:
            return text or ""
        # known values first, longest first so "Иванов Иван" wins over "Иванов"
        for label, value in sorted(self.mapping.items(), key=lambda kv: -len(kv[1])):
            text = re.sub(re.escape(value), label, text, flags=re.IGNORECASE)
        # a person's name also appears in parts — «И. Петров» under the signature, «Петрову» in the text: every part of
        # three letters or more goes too (with its endings)
        for label, value in self.mapping.items():
            if label.startswith("[PERSON_"):
                for part in re.findall(r"\w{3,}", value):
                    text = re.sub(rf"\b{re.escape(part)}\w{{0,3}}\b", label, text, flags=re.IGNORECASE)
        for kind, pattern in _PATTERNS:
            text = pattern.sub(lambda m, k=kind: self._label_for(k, m.group(0)), text)
        return text

    def redact_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {k: self.redact_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.redact_obj(v) for v in obj]
        return obj

    def restore(self, text: str | None) -> str:
        if not text:
            return text or ""
        return LABEL_RE.sub(lambda m: self.mapping.get(m.group(0), m.group(0)), text)

    def restore_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.restore(obj)
        if isinstance(obj, dict):
            return {k: self.restore_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.restore_obj(v) for v in obj]
        return obj
