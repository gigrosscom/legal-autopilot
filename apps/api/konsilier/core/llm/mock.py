"""Deterministic LLM stand-in for local dev (no API key) and tests.

It only uses data present in the payload (scenario keywords, pack hints), so it
stays country-agnostic like the rest of the core.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import Attachment

_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMBER = re.compile(r"\d[\d\s ]*(?:[.,]\d{1,2})?")


def _first_date(text: str) -> str | None:
    m = _DATE.search(text)
    if not m:
        return None
    if m.group(1):
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return f"{m.group(4)}-{m.group(5)}-{m.group(6)}"


def _largest_amount(text: str) -> str | None:
    # ignore dates and PII labels before looking for amounts
    cleaned = _DATE.sub(" ", re.sub(r"\[[A-Z_]+_\d+\]", " ", text))
    best: float | None = None
    for m in _NUMBER.finditer(cleaned):
        raw = re.sub(r"[\s ]", "", m.group(0)).replace(",", ".")
        try:
            val = float(raw)
        except ValueError:
            continue
        if val >= 100 and (best is None or val > best):
            best = val
    if best is None:
        return None
    return str(int(best)) if best == int(best) else str(best)


class HeuristicMockProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, task: str, system: str, user: str, schema: dict[str, Any],
                      attachments: tuple[Attachment, ...] = ()) -> dict[str, Any]:
        payload = json.loads(user)
        self.calls.append({"task": task, "payload": payload, "user": user})
        handler = getattr(self, f"_{task}", None)
        if handler is None:
            raise ValueError(f"mock has no handler for task {task!r}")
        return handler(payload)

    # ---- tasks ---------------------------------------------------------
    def _qualify(self, p: dict[str, Any]) -> dict[str, Any]:
        text = p["text"].lower()
        best_id, best_hits = None, 0
        for sc in p["scenarios"]:
            hits = sum(1 for kw in sc.get("keywords", []) if kw.lower() in text)
            if hits > best_hits:
                best_id, best_hits = sc["id"], hits
        if best_id is None:
            return {"scenario_id": None, "confidence": 0.0, "reason": "no keywords matched"}
        return {"scenario_id": best_id, "confidence": min(0.95, 0.35 + 0.15 * best_hits),
                "reason": f"{best_hits} keyword(s) matched"}

    def _extract_fields(self, p: dict[str, Any]) -> dict[str, Any]:
        text: str = p["text"]
        fields = {f["name"]: f for f in p["fields"]}
        values: dict[str, Any] = {name: None for name in fields}
        current = p.get("current_field")
        if current and current in fields:
            ftype = fields[current]["type"]
            if ftype == "date":
                values[current] = _first_date(text) or text.strip()
            elif ftype in ("money", "number"):
                values[current] = _largest_amount(text) or text.strip()
            else:
                values[current] = text.strip()
            return {"values": values}
        # free story: fill the description-like field, a date and an amount if present
        for name, f in fields.items():
            if f["type"] == "longtext" and values[name] is None:
                values[name] = text.strip()
                break
        for name, f in fields.items():
            if f["type"] == "date" and values[name] is None:
                values[name] = _first_date(text)
                break
        for name, f in fields.items():
            if f["type"] == "money" and values[name] is None:
                values[name] = _largest_amount(text)
                break
        return {"values": values}

    def _extract_evidence(self, p: dict[str, Any]) -> dict[str, Any]:
        text: str = p.get("text") or ""
        fields = {f["name"]: f for f in p["fields"]}
        facts: dict[str, Any] = {name: None for name in fields}
        for name, f in fields.items():
            if f["type"] == "date":
                facts[name] = _first_date(text)
                break
        for name, f in fields.items():
            if f["type"] == "money":
                facts[name] = _largest_amount(text)
                break
        return {"facts": facts, "summary": text[:200]}

    def _classify_taxonomy(self, p: dict[str, Any]) -> dict[str, Any]:
        text = p["text"].lower()
        best, best_hits = None, 0
        for d in p["disputes"]:
            hits = sum(1 for kw in d.get("keywords", []) if kw.lower() in text)
            if hits > best_hits:
                best, best_hits = d, hits
        flags = [f for f, words in (("emergency", ("убьёт", "убьет", "угрожает убить")),
                                    ("harassment", ("затравить", "буду жаловаться каждый день")))
                 if any(w in text for w in words)]
        if best is None:
            return {"dispute_id": None, "role": None, "confidence": 0.0, "flags": flags, "reason": "no keywords"}
        return {"dispute_id": best["id"], "role": best["applicant_roles"][0],
                "confidence": min(0.95, 0.5 + 0.2 * best_hits), "flags": flags, "reason": f"{best_hits} keyword(s)"}

    def _generic_demands(self, p: dict[str, Any]) -> dict[str, Any]:
        return {"demands": f"1. {p['goal'].strip()}"}

    def _narrative(self, p: dict[str, Any]) -> dict[str, Any]:
        facts = p["facts"]
        texts = [str(facts[f["name"]]).strip() for f in p["fields"]
                 if f["type"] == "longtext" and facts.get(f["name"])]
        return {"narrative": " ".join(t if t.endswith(".") else f"{t}." for t in texts)}

    def _classify_response(self, p: dict[str, Any]) -> dict[str, Any]:
        original = (p.get("text") or "").strip()
        text = original.lower()
        if not text:
            return {"response_class": "none", "summary": ""}
        hints: dict[str, list[str]] = p.get("hints", {})
        for cls in ("partial", "refusal", "full"):  # partial first: "частично отказать"
            if any(h.lower() in text for h in hints.get(cls, [])):
                return {"response_class": cls, "summary": original[:200]}
        return {"response_class": "unclear", "summary": original[:200]}
