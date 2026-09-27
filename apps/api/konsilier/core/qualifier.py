"""Multi-level qualification (ADR 0001): verified scenario → universal path → lawyer.

Level 1 is decided by ``ai.qualify`` over published scenarios (unchanged). This module decides what happens
when there is no verified scenario: it maps the LLM's taxonomy guess onto the pack's data and applies the
pack's routing rules. It never picks a forum by LLM: candidates come from the registry; if there are
several, the user chooses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .coverage import DEFENCE_ROLES, Coverage, Forum

LEVEL_VERIFIED = "verified"
LEVEL_UNIVERSAL = "universal"
LEVEL_LAWYER = "lawyer"
# Display-only: a level-1 scenario that no lawyer has signed yet. Stored level stays "verified".
LEVEL_SCENARIO_DRAFT = "scenario_draft"


def display_level(stored: str, scenario_is_draft: bool) -> str:
    """The level shown to people: never "verified" for a scenario without a lawyer's sign-off."""
    return LEVEL_SCENARIO_DRAFT if stored == LEVEL_VERIFIED and scenario_is_draft else stored


@dataclass
class Route:
    level: str | None  # None → could not classify: ask the user for more details
    dispute_id: str | None = None
    role: str | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    forums: list[Forum] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_taxonomy(self) -> dict[str, Any]:
        return {"dispute_id": self.dispute_id, "role": self.role, "confidence": self.confidence,
                "flags": self.flags, "explanation": self.explanation}


def taxonomy_options(cov: Coverage, lang: str) -> list[dict[str, Any]]:
    """What the LLM may choose from (and the keyword fallback matches against)."""
    out = []
    for d in cov.disputes.values():
        out.append({
            "id": d.id,
            "title": d.title.get(lang) or next(iter(d.title.values())),
            "branch": d.branch,
            "applicant_roles": list(d.applicant_roles),
            "keywords": [kw for kws in d.keywords.values() for kw in kws],
        })
    return out


def route_universal(cov: Coverage, result: dict[str, Any], *, amount: Decimal | None = None,
                    include_religious: bool = False) -> Route:
    dispute_id, role = result.get("dispute_id"), result.get("role")
    confidence = float(result.get("confidence") or 0.0)
    route = Route(level=None, dispute_id=dispute_id, role=role, confidence=confidence,
                  flags=list(result.get("flags") or []), explanation=str(result.get("reason") or ""))
    if not dispute_id or dispute_id not in cov.disputes:
        return route
    dispute = cov.dispute(dispute_id)
    if role not in dispute.applicant_roles:
        role = route.role = dispute.applicant_roles[0]

    reasons: list[str] = []
    if role in DEFENCE_ROLES:
        reasons.append("defence")
    elif cov.is_lawyer_only(dispute, role):
        reasons.append("lawyer_only")
    if "children" in dispute.sensitive:
        reasons.append("children")
    if confidence < cov.routing.min_confidence:
        reasons.append("low_confidence")
    threshold = cov.routing.high_amount_threshold
    if threshold is not None and amount is not None and amount > Decimal(str(threshold)):
        reasons.append("high_amount")
    forums = [] if reasons else cov.candidate_forums(dispute, role, include_religious=include_religious)
    if not reasons and not forums:
        reasons.append("no_forum")
    route.reasons, route.forums = reasons, forums
    route.level = LEVEL_LAWYER if reasons else LEVEL_UNIVERSAL
    return route
