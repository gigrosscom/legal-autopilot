"""Safety rules (ADR 0001 §7): emergency detection, required acknowledgements, abuse detection.

All thresholds, numbers, keywords and texts come from the pack (``routing.yaml`` and i18n).
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .coverage import Coverage
from .models import Case, Consent, utcnow

ACK_FALSE_REPORT = "false_report"
ACK_SPECIAL_CATEGORY = "special_category"
SPECIAL_CATEGORIES = frozenset({"health", "religion", "criminal_record"})
ABUSE_FLAGS = frozenset({"harassment", "blackmail", "defamation", "knowingly_false"})


def detect_emergency(cov: Coverage | None, text: str) -> bool:
    """Keyword check from pack data — works without the LLM and before any intake."""
    if cov is None:
        return False
    low = text.lower()
    return any(kw.lower() in low for kws in cov.routing.emergency.keywords.values() for kw in kws)


def emergency_numbers(cov: Coverage | None, lang: str, default_lang: str) -> list[dict[str, Any]]:
    if cov is None:
        return []
    return [{"label": n.label.get(lang) or n.label.get(default_lang) or next(iter(n.label.values())),
             "number": n.number, "verified": n.verified_at is not None} for n in cov.routing.emergency.numbers]


def required_acks(cov: Coverage | None, case: Case) -> list[str]:
    """Acknowledgements this case needs before intake continues."""
    if cov is None or not case.taxonomy or case.taxonomy.get("dispute_id") not in cov.disputes:
        return []
    dispute = cov.dispute(case.taxonomy["dispute_id"])
    out = []
    if dispute.false_report_warning:
        out.append(ACK_FALSE_REPORT)
    if SPECIAL_CATEGORIES & set(dispute.sensitive):
        out.append(ACK_SPECIAL_CATEGORY)
    return out


def given_acks(session: Session, case: Case) -> set[str]:
    return set(session.scalars(select(Consent.kind).where(Consent.case_id == case.id)))


def pending_ack(session: Session, cov: Coverage | None, case: Case) -> str | None:
    given = given_acks(session, case)
    return next((k for k in required_acks(cov, case) if k not in given), None)


def labels_instead_of_facts(cov: Coverage | None, case: Case, text: str) -> bool:
    """True once per case when a crime report describes people with labels rather than facts."""
    if cov is None or (case.taxonomy or {}).get("labels_warned"):
        return False
    dispute_id = (case.taxonomy or {}).get("dispute_id")
    if dispute_id not in cov.disputes or not cov.dispute(dispute_id).false_report_warning:
        return False
    low = text.lower()
    return any(w.lower() in low for ws in cov.routing.evaluative_words.values() for w in ws)


def _norm(name: str) -> str:
    return re.sub(r"[^\w]+", " ", name.lower()).strip()


def abuse_reason(session: Session, cov: Coverage | None, case: Case) -> str | None:
    """Repeated/mass complaints by one applicant, or against one private person. Returns a hold reason."""
    if cov is None:
        return None
    flags = set((case.taxonomy or {}).get("flags") or [])
    if flags & ABUSE_FLAGS:
        return "abuse_suspected"
    limits = cov.routing.abuse
    since = utcnow() - timedelta(days=limits.window_days)
    # owner 02.10 (on_hold on his own tests): every chat opens a case, so «cases» counted conversations — only the
    # cases that reached a document count towards the limit of mass complaints
    from .models import Action

    recent = session.scalar(select(func.count(func.distinct(Action.case_id))).join(Case, Case.id == Action.case_id).where(
        Case.owner_id == case.owner_id, Case.id != case.id, Action.created_at >= since))
    if (recent or 0) > limits.max_cases_per_applicant:
        return "too_many_cases"
    respondent = case.facts.get("respondent_name")
    dispute_id = (case.taxonomy or {}).get("dispute_id")
    if respondent and dispute_id in cov.disputes and set(cov.dispute(dispute_id).counterparty_kinds) <= {"person"}:
        target = _norm(str(respondent))
        same = 0
        for other in session.scalars(select(Case).where(Case.owner_id == case.owner_id, Case.created_at >= since)):
            if other.facts and _norm(str(other.facts.get("respondent_name") or "")) == target:
                same += 1
        if same > limits.max_cases_per_respondent:
            return "repeated_against_person"
    return None


def _says_any(markers: dict[str, tuple[str, ...]], text: str) -> bool:
    def words(t: str) -> str:
        return " ".join(re.findall(r"\w+", t.lower()))

    low = words(text)
    return any(re.search(r"(?<!\w)" + re.escape(words(m)) + r"(?!\w)", low)
               for ms in markers.values() for m in ms if words(m))


def direct_dispute(cov: Coverage | None, text: str):
    """The pack's direct rule the words decide (routing.direct): any marker (a word start) and no `unless` word."""
    if cov is None or not text:
        return None
    low = " ".join(re.findall(r"\w+", text.lower()))

    def starts(words: dict[str, tuple[str, ...]]) -> bool:
        return any(re.search(r"(?<!\w)" + re.escape(" ".join(re.findall(r"\w+", w.lower()))), low)
                   for ws in words.values() for w in ws if w.strip())

    return next((r for r in cov.routing.direct if starts(r.markers) and not starts(r.unless)), None)


def matter_pending(cov: Coverage | None, text: str) -> bool:
    """The person says the matter is already in a court or with the police (routing.pending_markers, whole
    words): only then a motion to «the court where your case is» is offered."""
    return cov is not None and bool(text) and _says_any(cov.routing.pending_markers, text)


def writes_as_business(cov: Coverage | None, text: str) -> bool:
    """The person writes as a sole trader or a company about a dispute with a business (routing.business_markers,
    whole words): consumer-protection scenarios do not apply to them."""
    if cov is None or not text:
        return False

    def words(t: str) -> str:
        return " ".join(re.findall(r"\w+", t.lower()))

    low = words(text)
    return any(re.search(r"(?<!\w)" + re.escape(words(m)) + r"(?!\w)", low)
               for ms in cov.routing.business_markers.values() for m in ms if words(m))
