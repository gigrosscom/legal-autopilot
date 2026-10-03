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

from ..scenario.schema import DeadlineSpec, FilingSpec, IntakeField

Localized = dict[str, str]

_DOTTED = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
_SIMPLE = re.compile(r"^[a-z][a-z0-9_]*$")

APPLICANT_ROLES = (
    "claimant", "victim", "complainant", "consumer", "borrower", "employee", "employer", "tenant",
    "landlord", "heir", "spouse", "parent", "taxpayer", "migrant", "business", "suspect", "accused",
    "beneficiary", "student",
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
    # lang → how people put it: suggestions in the consultation chat where no scenario covers the dispute yet
    examples: dict[str, tuple[str, ...]] = Field(default_factory=dict)

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


_MESSENGER = {"whatsapp": re.compile(r"^https://wa\.me/\d{10,15}$"),
              "telegram": re.compile(r"^https://t\.me/[A-Za-z0-9_]{5,32}$")}


class SubmissionChannel(_Strict):
    # whatsapp / telegram: only a body's OFFICIAL channel, published on its own site (source is required)
    kind: Literal["portal", "email", "post", "in_person", "whatsapp", "telegram"]
    url: str | None = None
    email: str | None = None
    source: str | None = None  # where the official channel is published (URL of the body's page)
    note: Localized = Field(default_factory=dict)

    @model_validator(mode="after")
    def _target(self) -> "SubmissionChannel":
        if self.kind == "portal" and not self.url:
            raise ValueError("portal submission needs url")
        if self.kind in _MESSENGER:
            if not self.url or not _MESSENGER[self.kind].match(self.url):
                raise ValueError(f"{self.kind} channel needs an official link like "
                                 + ("https://wa.me/77001234567" if self.kind == "whatsapp" else "https://t.me/name"))
            if not self.source:
                raise ValueError(f"{self.kind} channel needs source: the body's page that publishes it")
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
    # the term and form of filing to this forum (from_field refers to the generic intake); absent → «уточнит юрист»
    filing: FilingSpec | None = None
    appeals_to: tuple[str, ...] = ()
    instance: Literal["first", "appeal", "any"] = "any"  # "appeal" = reached only by escalation
    legal_effect: Literal["binding", "advisory", "none"]
    source: str
    verified_at: date | None = None
    verified_by: str | None = None
    # place in the «Куда подать» list (smaller first): the pre-trial step, then the authority or court, then optional ways
    order: int = 50
    # only where proceedings already run (a motion to the court or police handling the matter): offered only when the
    # person says so (routing.pending_markers)
    pending_only: bool = False
    # disputes / branches where this pre-trial step is required by law or usual contract (court returns the claim
    # without it): shown as «досудебный шаг — без него суд вернёт иск»; otherwise as voluntary settlement
    mandatory_for: tuple[str, ...] = ()
    # what the person should know about this forum for a dispute type or branch: term, competent court, norm
    hints: dict[str, Localized] = Field(default_factory=dict)

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


# ---------------------------------------------------------------- recipient routes
class RouteStep(_Strict):
    """One step of a recipient route (owner 02.10: the system, not the person, chooses who a document goes to).
    Exactly one of: a forum of the registry, an authority of the pack manifest, or the other side itself (party)."""

    forum: str | None = None
    authority: str | None = None
    party: bool = False
    label: Localized  # who, in plain words: «Продавец — досудебная претензия»
    when: Localized = Field(default_factory=dict)  # condition for a later step: «если не ответили за 10 дней»
    why: Localized  # one line: why this addressee
    norm: str  # the norm behind it, as checked (act, article); "не подтверждено" when not opened

    @model_validator(mode="after")
    def _one_target(self) -> "RouteStep":
        if sum((self.forum is not None, self.authority is not None, self.party)) != 1:
            raise ValueError("a route step needs exactly one of forum, authority, party")
        return self


class RecipientRoute(_Strict):
    steps: tuple[RouteStep, ...] = Field(min_length=1)
    note: Localized = Field(default_factory=dict)  # what the route does not cover («с несовершеннолетними детьми — …»)
    # the documents the chat asks for on this route (evidence kinds of the pack: i18n evidence.<kind>), for a dispute
    # of the universal path that has no scenario of its own (PM 03.10: a divorce was asked for «чек, гарантийный талон»)
    documents: tuple[str, ...] = ()
    # the title of the dispute's first document («Исковое заявление о расторжении брака»), in place of «<kind>: <body>»
    # where the body's label would end up in the document's subject line (ZANN 03.10, family pilot)
    document_title: Localized = Field(default_factory=dict)


class RecipientRoutes(_Strict):
    """routes.yaml: key = a dispute type id (universal path) or a scenario id of the pack."""

    routes: dict[str, RecipientRoute] = Field(default_factory=dict)


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


class DirectRule(_Strict):
    """A dispute the words alone decide (QA BUG-24: «долг по расписке» went to a consumer refund one time in two):
    any of `markers` (word starts) and none of `unless` → this dispute and role, no model guess."""

    dispute: str
    role: str
    # a published scenario of the pack for this subject (PM 02.10: a flood, a tour, a debt never get a neighbouring
    # scenario); when set and on offer, the case gets it directly, else the dispute on the universal path
    scenario: str | None = None
    markers: dict[str, tuple[str, ...]]
    unless: dict[str, tuple[str, ...]] = Field(default_factory=dict)


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
    # the person writes as a business (sole trader, company) about a dispute with a business: consumer law does not
    # apply; lang → phrases, matched on whole words
    business_markers: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # PM 02.10: the chat and the card name the same document — kind → word stems that name it (any language)
    document_kinds: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # words that must never reach a document given to a client (core/docgate.py): lang (or "*") → phrases
    document_markers: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # words that make a sentence a citation of a norm (статья, закон, кодекс): one cited twice in a row is stopped
    norm_words: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # labels of a document left with nothing after them («Правовое основание:» when no norm is checked): not printed
    document_drop_empty: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # the matter is already in a court or with the police (case number, hearing, investigator): only then the forums
    # marked pending_only are offered; lang → phrases, matched on whole words
    pending_markers: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # disputes decided by the words alone, before any model call (QA BUG-24)
    direct: tuple[DirectRule, ...] = ()
    # owner 02.10: the client does not choose where to file — the first forum of this order among the candidates is
    # the step's recipient; forums left out (mediation, a court or police already dealing with the case) are never
    # chosen by the system, only by «Другой адресат». forum id → the one line «почему» shown under «Кому».
    forum_order: tuple[str, ...] = ()
    forum_why: dict[str, Localized] = Field(default_factory=dict)
