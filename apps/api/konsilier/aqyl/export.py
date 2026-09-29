"""Training data for Aqyl: cases whose owners allowed it (consent "training"), anonymised.

Each record: the story, the route the case took (scenario / dispute / forum), the facts (non-personal fields),
the documents' text, the response classes and the outcome. Personal data is removed twice: every value the case's
PII vault knows is replaced by its label, then 12-digit id numbers, phones and e-mails are masked. Uploaded
evidence is left out unless asked for (it may name people the vault never saw). Test accounts are never exported.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.documents import docx_text
from ..core.models import Case, Consent, User
from ..core.pii import PiiVault

TRAINING = "training"
_MASKS = ((re.compile(r"(?<!\d)\d{12}(?!\d)"), "[номер]"),  # personal or company id numbers
          (re.compile(r"\+?\d[\d\s()-]{9,}\d"), "[телефон]"),
          (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[e-mail]"))


def scrub(text: str | None, vault: PiiVault) -> str:
    out = vault.redact(text or "")
    for pattern, label in _MASKS:
        out = pattern.sub(label, out)
    return out


def consented(session: Session) -> set[Any]:
    return set(session.scalars(select(Consent.case_id).where(Consent.kind == TRAINING)).all())


def export(session: Session, engine: Any, *, with_evidence: bool = False) -> Iterator[dict[str, Any]]:
    ids = consented(session)
    tests = set(session.scalars(select(User.id).where(User.is_test.is_(True))).all())
    for case in session.scalars(select(Case).where(Case.id.in_(ids)).order_by(Case.created_at)).all():
        if case.owner_id in tests:
            continue
        vault = PiiVault(case.pii_map)
        sc = engine.scenario_of(case) if case.scenario_id else None
        personal = {f.name for f in sc.intake if f.pii} if sc else set()
        facts = {k: scrub(str(v), vault) for k, v in (case.facts or {}).items() if k not in personal}
        documents = []
        for a in case.actions:
            text = ""
            if a.docx_key:
                try:
                    text = scrub(docx_text(engine.storage.get(a.docx_key)), vault)
                except Exception:  # noqa: BLE001 — a missing file skips the text, not the case
                    text = ""
            documents.append({"action": a.action_id, "kind": a.kind, "text": text, "status": a.status,
                              "response": a.response_class, "response_summary": scrub(a.response_summary, vault)})
        outcome = case.outcome
        record = {
            "id": hashlib.sha256(str(case.id).encode()).hexdigest()[:16],
            "country": case.jurisdiction, "language": case.language,
            "story": scrub(case.initial_text, vault),
            "route": {"scenario": case.scenario_id, "dispute": (sc.taxonomy if sc else None)
                      or (case.taxonomy or {}).get("dispute_id"), "forum": case.forum_id,
                      "level": case.coverage_level},
            "facts": facts,
            "evidence_kinds": [e.kind for e in case.evidence],
            "documents": documents,
            "outcome": {"result": outcome.result, "amount_recovered": str(outcome.amount_recovered or ""),
                        "days": outcome.days_to_resolution} if outcome else None,
        }
        if with_evidence:
            record["evidence"] = [{"kind": e.kind, "text": scrub(e.text, vault)[:20000]} for e in case.evidence
                                  if e.kind != "id_document"]
        yield record
