"""The only places where the LLM is used. Each returns data; none decides the next step.

LLM responsibilities (per product rules):
  * qualify: pick one of the *published* scenarios (+ confidence);
  * extract_fields / extract_evidence: pull intake values out of text/files;
  * narrative: write the "statement of circumstances" paragraph;
  * classify_response: classify a counterparty reply into generic response classes.
Norms, amounts, deadlines and addressees are never produced by the LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from .llm import Attachment, LLMError, RedactingLLM
from .packs import JurisdictionPack
from .scenario import RESPONSE_CLASSES, Scenario

log = logging.getLogger(__name__)

_COMMON_RULES = (
    "You are a component of Konsilier, a service that helps people prepare documents "
    "for everyday legal problems. You never give legal conclusions, never invent laws, "
    "article numbers, deadlines, amounts, names or addresses. Tokens like [PERSON_1], "
    "[ID_NUMBER_1], [ACCOUNT_1] are placeholders for personal data: keep them exactly "
    "as they are and never try to guess the real values."
)


def _field_specs(scenario: Scenario, pack: JurisdictionPack, lang: str,
                 only: list[str] | None = None) -> list[dict[str, Any]]:
    specs = []
    for f in scenario.intake:
        if f.type == "evidence" or (only is not None and f.name not in only):
            continue
        specs.append({
            "name": f.name,
            "type": f.type,
            "label": field_label(scenario, pack, lang, f.name),
        })
    return specs


def field_label(scenario: Scenario, pack: JurisdictionPack, lang: str, name: str) -> str:
    f = scenario.field(name)
    if f.label:
        return pack.localized(f.label, lang)
    return pack.t(lang, f"fields.{name}.label", default=name)


def _nullable_values_schema(names: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {n: {"type": ["string", "null"]} for n in names},
        "required": names,
        "additionalProperties": False,
    }


def qualify(llm: RedactingLLM, scenarios: list[Scenario], packs: dict[str, JurisdictionPack],
            text: str, lang: str) -> tuple[str | None, float, str]:
    if not scenarios:
        return None, 0.0, "no published scenarios"
    options = []
    for sc in scenarios:
        pack = packs[sc.jurisdiction]
        keywords = [kw for kws in sc.classification.keywords.values() for kw in kws]
        examples = list(sc.classification.examples.get(lang, ())) or [
            ex for exs in sc.classification.examples.values() for ex in exs]
        options.append({
            "id": sc.id,
            "title": pack.localized(sc.title, lang),
            "summary": pack.localized(sc.summary, lang) if sc.summary else "",
            "keywords": keywords,
            "examples": examples,
        })
    ids = [o["id"] for o in options]
    schema = {
        "type": "object",
        "properties": {
            "scenario_id": {"type": ["string", "null"], "enum": [*ids, None]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["scenario_id", "confidence", "reason"],
        "additionalProperties": False,
    }
    system = (
        f"{_COMMON_RULES}\nTask: read the user's description of their problem and choose the single "
        "scenario that fits it from the provided list, or null if none fits. Give confidence 0..1: "
        "use >= 0.8 only when the situation clearly matches the scenario's summary."
    )
    try:
        out = llm.complete_json(task="qualify", system=system,
                                payload={"text": text, "language": lang, "scenarios": options}, schema=schema)
    except LLMError as e:
        log.warning("qualify failed: %s", e)
        return None, 0.0, "llm_error"
    sid = out.get("scenario_id")
    if sid not in ids:
        return None, 0.0, out.get("reason", "")
    return sid, max(0.0, min(1.0, float(out.get("confidence", 0)))), out.get("reason", "")


def extract_fields(llm: RedactingLLM, scenario: Scenario, pack: JurisdictionPack, lang: str,
                   text: str, current_field: str | None, missing: list[str]) -> dict[str, Any]:
    specs = _field_specs(scenario, pack, lang, only=missing)
    if not specs:
        return {}
    names = [s["name"] for s in specs]
    schema = {
        "type": "object",
        "properties": {"values": _nullable_values_schema(names)},
        "required": ["values"],
        "additionalProperties": False,
    }
    system = (
        f"{_COMMON_RULES}\nTask: extract values for the listed fields from the user's message. "
        "If current_field is set, the message is the answer to that field's question. "
        "Return null for anything not stated explicitly. Dates as YYYY-MM-DD, money as a plain "
        "number without currency."
    )
    try:
        out = llm.complete_json(task="extract_fields", system=system, schema=schema, payload={
            "text": text, "language": lang, "current_field": current_field, "fields": specs})
    except LLMError as e:
        log.warning("extract_fields failed: %s", e)
        return {current_field: text} if current_field else {}
    return {k: v for k, v in (out.get("values") or {}).items() if v not in (None, "") and k in names}


def extract_evidence(llm: RedactingLLM, scenario: Scenario, pack: JurisdictionPack, lang: str,
                     text: str | None, attachments: tuple[Attachment, ...] = ()) -> tuple[dict[str, Any], str]:
    specs = _field_specs(scenario, pack, lang)
    names = [s["name"] for s in specs]
    schema = {
        "type": "object",
        "properties": {"facts": _nullable_values_schema(names), "summary": {"type": "string"}},
        "required": ["facts", "summary"],
        "additionalProperties": False,
    }
    system = (
        f"{_COMMON_RULES}\nTask: the user uploaded a document (receipt, screenshot, letter, statement). "
        "Extract only facts that are literally visible for the listed fields; null otherwise. "
        "Dates as YYYY-MM-DD, money as a plain number. Summary: one sentence describing the document."
    )
    try:
        out = llm.complete_json(task="extract_evidence", system=system, schema=schema,
                                payload={"text": text or "", "language": lang, "fields": specs},
                                attachments=attachments)
    except LLMError as e:
        log.warning("extract_evidence failed: %s", e)
        return {}, ""
    facts = {k: v for k, v in (out.get("facts") or {}).items() if v not in (None, "") and k in names}
    return facts, out.get("summary", "")


def write_narrative(llm: RedactingLLM, scenario: Scenario, pack: JurisdictionPack, lang: str,
                    facts: dict[str, Any], action_title: str) -> str:
    specs = _field_specs(scenario, pack, lang)
    schema = {
        "type": "object",
        "properties": {"narrative": {"type": "string"}},
        "required": ["narrative"],
        "additionalProperties": False,
    }
    language_name = pack.t(lang, "language_name", default=lang)
    system = (
        f"{_COMMON_RULES}\nTask: write the 'statement of circumstances' section of the document "
        f"'{action_title}' in {language_name}, formal written style, first person of the applicant, "
        "3-6 sentences, chronological. Use only the provided facts. Do not cite laws, do not state "
        "demands (they are added separately), do not add greetings or signatures."
    )
    try:
        out = llm.complete_json(task="narrative", system=system, schema=schema,
                                payload={"language": lang, "facts": facts, "fields": specs})
        return (out.get("narrative") or "").strip()
    except LLMError as e:
        log.warning("narrative failed: %s", e)
        return ""


def classify_response(llm: RedactingLLM, pack: JurisdictionPack, lang: str, text: str,
                      action_title: str) -> tuple[str, str]:
    schema = {
        "type": "object",
        "properties": {
            "response_class": {"type": "string", "enum": list(RESPONSE_CLASSES)},
            "summary": {"type": "string"},
        },
        "required": ["response_class", "summary"],
        "additionalProperties": False,
    }
    hints = pack.i18n.get(lang, {}).get("llm_hints", {}).get("response", {}) or \
        pack.i18n.get(pack.manifest.default_language, {}).get("llm_hints", {}).get("response", {})
    system = (
        f"{_COMMON_RULES}\nTask: the applicant sent '{action_title}' and received the reply below. "
        "Classify it: full = demands satisfied in full; partial = satisfied in part; refusal = refused "
        "or excuses without satisfying; none = no reply / empty; unclear = cannot tell. "
        "Summary: one neutral sentence in the reply's language."
    )
    try:
        out = llm.complete_json(task="classify_response", system=system, schema=schema,
                                payload={"text": text, "language": lang, "hints": hints})
    except LLMError as e:
        log.warning("classify_response failed: %s", e)
        return "unclear", ""
    cls = out.get("response_class")
    return (cls if cls in RESPONSE_CLASSES else "unclear"), out.get("summary", "")
