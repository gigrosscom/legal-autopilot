"""Data schemas for universal coverage: taxonomy, forum registry, document types, routing rules.

Everything country-specific lives in ``packs/<cc>/`` (taxonomy extensions, forums, documents,
routing). The core holds only the global, country-neutral catalogue of branches of law.
See docs/adr/0001-universal-coverage.md.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..scenario.schema import DeadlineSpec, IntakeField

Localized = dict[str, str]

_DOTTED = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
_SIMPLE = re.compile(r"^[a-z][a-z0-9_]*$")

APPLICANT_ROLES = (
    "claimant", "victim", "complainant", "consumer", "borrower", "employee", "employer", "tenant",
    "landlord", "heir", "spouse", "parent", "taxpayer", "migrant", "business", "suspect", "accused",
)
# The platform never writes defence documents: these roles are always routed to a lawyer.
DEFENCE_ROLES = frozenset({"suspect", "accused"})
COUNTERPARTY_KINDS = (
    "person", "business", "bank", "employer", "landlord", "state_body", "police", "court", "insurer",
    "unknown",
)
SENSITIVE = Literal["health", "religion", "criminal_record", "children"]
FORUM_TYPES = (
    "court", "prosecutor", "police", "regulator", "ministry", "ombudsman", "local_authority",
    "arbitration", "mediation", "private_org",
)
DOCUMENT_TYPES = ("complaint", "claim_letter", "statement", "lawsuit", "motion", "appeal", "appeal_request")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- taxonomy
class DisputeType(_Strict):
    id: str  # "<branch>.<dispute>", local additions: "<cc>.<branch>.<dispute>"
    title: Localized
    applicant_roles: tuple[str, ...]
    counterparty_kinds: tuple[str, ...] = ("unknown",)
    sensitive: tuple[SENSITIVE, ...] = ()
    # Situations where the applicant may face criminal liability for a knowingly false report.
    false_report_warning: bool = False
    # lang → substrings; used only as an offline fallback when the LLM is unavailable
    keywords: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _DOTTED.match(v):
            raise ValueError("dispute type id must look like 'branch.dispute'")
        return v

    @field_validator("applicant_roles")
    @classmethod
    def _roles(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        bad = [r for r in v if r not in APPLICANT_ROLES]
        if bad or not v:
            raise ValueError(f"unknown applicant roles {bad}; allowed: {', '.join(APPLICANT_ROLES)}")
        return v

    @field_validator("counterparty_kinds")
    @classmethod
    def _kinds(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        bad = [k for k in v if k not in COUNTERPARTY_KINDS]
        if bad:
            raise ValueError(f"unknown counterparty kinds {bad}")
        return v

    @field_validator("id")
    @classmethod
    def _no_double_underscore(cls, v: str) -> str:
        if "__" in v:
            raise ValueError("dispute type id must not contain '__' (reserved for generic scenario ids)")
        return v

    @property
    def branch(self) -> str:
        parts = self.id.split(".")
        return parts[-2]


class Branch(_Strict):
    id: str
    title: Localized
    situation: Localized = Field(default_factory=dict)  # plain-language tile text
    disputes: tuple[DisputeType, ...]

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _SIMPLE.match(v):
            raise ValueError("branch id must be snake_case")
        return v

    @model_validator(mode="after")
    def _prefix(self) -> "Branch":
        for d in self.disputes:
            if d.branch != self.id:
                raise ValueError(f"dispute {d.id} does not belong to branch {self.id}")
        return self


class GlobalTaxonomy(_Strict):
    version: str
    branches: tuple[Branch, ...]


class PackTaxonomy(_Strict):
    """``packs/<cc>/taxonomy.yaml``: local additions to and exclusions from the global catalogue."""

    extends: Literal["global"] = "global"
    add: tuple[DisputeType, ...] = ()
    disable: tuple[str, ...] = ()


# ---------------------------------------------------------------- forums
class AcceptRule(_Strict):
    branches: tuple[str, ...] = ()
    dispute_types: tuple[str, ...] = ()  # empty = every dispute type of the listed branches
    applicant_roles: tuple[str, ...] = ()  # empty = any role

    @model_validator(mode="after")
    def _something(self) -> "AcceptRule":
        if not self.branches and not self.dispute_types:
            raise ValueError("accept rule needs branches or dispute_types")
        return self


class SubmissionChannel(_Strict):
    kind: Literal["portal", "email", "post", "in_person"]
    url: str | None = None
    email: str | None = None
    note: Localized = Field(default_factory=dict)

    @model_validator(mode="after")
    def _target(self) -> "SubmissionChannel":
        if self.kind == "portal" and not self.url:
            raise ValueError("portal submission needs url")
        return self


class Fee(_Strict):
    amount: float | None = None  # None = unknown → "a lawyer will confirm"
    currency: str | None = None
    note: Localized = Field(default_factory=dict)
    norm_ref: str = "TODO"


class ForumJurisdiction(_Strict):
    regions: tuple[str, ...] = ("*",)  # region codes from the pack, "*" = whole country
    rule: Localized = Field(default_factory=dict)  # territorial competence in words


class Forum(_Strict):
    id: str
    type: Literal[
        "court", "prosecutor", "police", "regulator", "ministry", "ombudsman", "local_authority",
        "arbitration", "mediation", "private_org",
    ]
    name: Localized
    jurisdiction: ForumJurisdiction = Field(default_factory=ForumJurisdiction)
    accepts: tuple[AcceptRule, ...]
    document_types: tuple[str, ...]
    submission: tuple[SubmissionChannel, ...]
    form_requirements: Localized = Field(default_factory=dict)
    languages: tuple[str, ...]
    fee: Fee | None = None
    response_deadline: DeadlineSpec | None = None
    appeals_to: tuple[str, ...] = ()
    instance: Literal["first", "appeal", "any"] = "any"  # "appeal" = reached only by escalation
    legal_effect: Literal["binding", "advisory", "none"]
    source: str
    verified_at: date | None = None
    verified_by: str | None = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _DOTTED.match(v):
            raise ValueError("forum id must look like 'cc.kind.name'")
        if "__" in v:
            raise ValueError("forum id must not contain '__' (reserved for generic scenario ids)")
        return v

    @field_validator("document_types")
    @classmethod
    def _docs(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        bad = [d for d in v if d not in DOCUMENT_TYPES]
        if bad or not v:
            raise ValueError(f"unknown document types {bad}; allowed: {', '.join(DOCUMENT_TYPES)}")
        return v

    @property
    def verified(self) -> bool:
        return self.verified_at is not None

    def accepts_case(self, dispute: DisputeType, role: str) -> bool:
        for rule in self.accepts:
            if rule.dispute_types and dispute.id not in rule.dispute_types:
                continue
            if not rule.dispute_types and dispute.branch not in rule.branches:
                continue
            if rule.applicant_roles and role not in rule.applicant_roles:
                continue
            return True
        return False


# ---------------------------------------------------------------- document types
class DocumentType(_Strict):
    id: str
    title: Localized
    required_fields: tuple[IntakeField, ...]
    template: str  # path relative to packs dir
    forum_types: tuple[str, ...]
    # what the applicant attaches, per language — shown as a checklist in the filing instructions
    attachments: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    verified_at: date | None = None
    verified_by: str | None = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if v not in DOCUMENT_TYPES:
            raise ValueError(f"unknown document type {v}; allowed: {', '.join(DOCUMENT_TYPES)}")
        return v

    @field_validator("forum_types")
    @classmethod
    def _forum_types(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        bad = [t for t in v if t not in FORUM_TYPES]
        if bad:
            raise ValueError(f"unknown forum types {bad}")
        return v


# ---------------------------------------------------------------- routing
class Checked(_Strict):
    """A country statement that must be verified before it is shown as fact."""

    text: Localized
    source: str = "TODO"
    verified_at: date | None = None


class EmergencyNumber(_Strict):
    label: Localized
    number: str
    source: str
    verified_at: date | None = None


class Emergency(_Strict):
    numbers: tuple[EmergencyNumber, ...] = ()
    keywords: dict[str, tuple[str, ...]] = Field(default_factory=dict)  # lang → substrings


class AbuseLimits(_Strict):
    window_days: int = 30
    max_cases_per_respondent: int = 3  # same private respondent from one applicant
    max_cases_per_applicant: int = 10


class Routing(_Strict):
    lawyer_only: tuple[str, ...] = ()  # branch ids or dispute type ids → always level 3
    high_amount_threshold: float | None = None  # None → rule not applied, "a lawyer will confirm"
    urgent_deadline_days: int = 5
    min_confidence: float = 0.6
    emergency: Emergency = Field(default_factory=Emergency)
    upl_notice: Checked | None = None  # unauthorised practice of law rules for this country
    false_report_norm: Checked | None = None
    abuse: AbuseLimits = Field(default_factory=AbuseLimits)
    # labels instead of facts ("вор", "мошенник"): in reports about crimes the user is asked once to describe facts
    evaluative_words: dict[str, tuple[str, ...]] = Field(default_factory=dict)
