"""Scenario schema. A scenario is DATA (YAML) owned by a jurisdiction pack.

The core only understands generic concepts: intake fields, actions, conditions,
deadlines, pricing. Legal content (norms, addressees, texts) comes from YAML.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .conditions import Condition, parse_condition

# Generic classes of a counterparty response. Scenario conditions may use only these.
RESPONSE_CLASSES = ("full", "partial", "refusal", "none", "unclear")

FieldType = Literal["text", "longtext", "date", "money", "number", "email", "phone", "evidence"]
PiiKind = Literal["person", "id_number", "account", "phone", "email", "address"]
Localized = dict[str, str]

_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SCENARIO_ID = re.compile(r"^[a-z]{2}(\.[a-z0-9_]+)+$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntakeField(_Strict):
    name: str
    type: FieldType = "text"
    optional: bool = False
    currency: str | None = None  # for money
    pattern: str | None = None  # regex the normalized value must match
    pii: PiiKind | None = None  # value is replaced by a label before reaching the LLM
    evidence_kinds: tuple[str, ...] = ()  # for type == evidence
    label: Localized = Field(default_factory=dict)  # inline override of pack i18n
    question: Localized = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError(f"field name {v!r} must be snake_case")
        return v

    @field_validator("pattern")
    @classmethod
    def _pattern(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"invalid regex {v!r}: {e}") from e
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "IntakeField":
        if self.type == "evidence" and not self.evidence_kinds:
            raise ValueError(f"evidence field {self.name!r} must list evidence kinds")
        if self.type != "evidence" and self.evidence_kinds:
            raise ValueError(f"field {self.name!r}: evidence kinds only allowed for evidence")
        return self


class DeadlineSpec(_Strict):
    calendar_days: int | None = Field(default=None, ge=1, le=365)
    business_days: int | None = Field(default=None, ge=1, le=365)
    norm_ref: str = "TODO"
    remind_before_days: tuple[int, ...] | None = None  # None → pack default

    @model_validator(mode="after")
    def _one_of(self) -> "DeadlineSpec":
        if (self.calendar_days is None) == (self.business_days is None):
            raise ValueError("deadline needs exactly one of calendar_days / business_days")
        return self


class AddresseeSpec(_Strict):
    """Who receives the document: a case party, a pack-level authority or a forum from the pack registry."""

    party: str | None = None  # e.g. "respondent"
    authority: str | None = None  # key in pack.authorities
    forum: str | None = None  # forum id in the pack's coverage registry (universal path)

    @model_validator(mode="after")
    def _one_of(self) -> "AddresseeSpec":
        if sum(x is not None for x in (self.party, self.authority, self.forum)) != 1:
            raise ValueError("addressee needs exactly one of party / authority / forum")
        return self


class ActionSpec(_Strict):
    id: str
    kind: Literal["document", "handoff"] = "document"
    title: Localized = Field(default_factory=dict)
    template: str | None = None  # path relative to packs dir
    channel: Literal["user_submits", "email", "email_or_user_submits"] = "user_submits"
    addressee: AddresseeSpec | None = None
    deadline: DeadlineSpec | None = None
    norm_refs: tuple[str, ...] = ()
    when: str | None = None
    instructions: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    demands: Localized = Field(default_factory=dict)  # "requirement" paragraph of the document

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError(f"action id {v!r} must be snake_case")
        return v

    @model_validator(mode="after")
    def _kind(self) -> "ActionSpec":
        if self.kind == "document":
            if not self.template:
                raise ValueError(f"document action {self.id!r} needs a template")
            if self.addressee is None:
                raise ValueError(f"document action {self.id!r} needs an addressee")
        if self.kind == "handoff" and self.template:
            raise ValueError(f"handoff action {self.id!r} must not have a template")
        if self.when is not None:
            parse_condition(self.when)  # raises ConditionError (a ValueError)
        return self

    @property
    def condition(self) -> Condition | None:
        return parse_condition(self.when) if self.when else None


class PartySpec(_Strict):
    kind: Literal["business", "person", "authority"] = "business"
    name_field: str
    id_field: str | None = None
    email_field: str | None = None
    address_field: str | None = None


class ClaimSpec(_Strict):
    type: str
    amount_field: str | None = None


class PricingSpec(_Strict):
    model: Literal["fixed", "free"] = "fixed"
    amount: float = 0
    currency: str | None = None


class ClassificationSpec(_Strict):
    keywords: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    examples: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class Scenario(_Strict):
    id: str
    version: str
    ontology: str
    taxonomy: str | None = None  # dispute type id in the coverage taxonomy (e.g. "consumer.refund")
    jurisdiction: str
    languages: tuple[str, ...]
    owner: str
    reviewed_at: date | None = None
    published: bool = False
    title: Localized
    summary: Localized = Field(default_factory=dict)
    classification: ClassificationSpec = Field(default_factory=ClassificationSpec)
    claim: ClaimSpec | None = None
    intake: tuple[IntakeField, ...]
    parties: dict[str, PartySpec] = Field(default_factory=dict)
    actions: tuple[ActionSpec, ...]
    pricing: PricingSpec = Field(default_factory=PricingSpec)

    @field_validator("intake", mode="before")
    @classmethod
    def _normalize_intake(cls, v: Any) -> Any:
        """Accept the compact YAML form::

            - seller_name
            - seller_bin: {optional: true}
            - evidence: [receipt, order_screenshot]
        """
        if not isinstance(v, list):
            raise ValueError("intake must be a list")
        out = []
        for i, item in enumerate(v):
            if isinstance(item, str):
                out.append({"name": item})
            elif isinstance(item, dict) and len(item) == 1:
                (name, spec), = item.items()
                if spec is None:
                    out.append({"name": name})
                elif isinstance(spec, list):
                    out.append({"name": name, "type": "evidence", "evidence_kinds": spec,
                                "optional": True})
                elif isinstance(spec, dict):
                    out.append({"name": name, **spec})
                else:
                    raise ValueError(f"intake[{i}] ({name}): expected mapping or list")
            elif isinstance(item, dict) and "name" in item:
                out.append(item)
            else:
                raise ValueError(f"intake[{i}]: expected 'field' or 'field: {{...}}'")
        return out

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _SCENARIO_ID.match(v):
            raise ValueError(f"scenario id {v!r} must look like 'cc.domain.name'")
        return v

    @field_validator("version")
    @classmethod
    def _version(cls, v: str) -> str:
        if not _VERSION.match(str(v)):
            raise ValueError(f"version {v!r} must be semver MAJOR.MINOR.PATCH")
        return str(v)

    @model_validator(mode="after")
    def _cross_checks(self) -> "Scenario":
        prefix = self.id.split(".", 1)[0]
        if prefix != self.jurisdiction.lower():
            raise ValueError(
                f"scenario id prefix {prefix!r} does not match jurisdiction {self.jurisdiction!r}"
            )
        names = [f.name for f in self.intake]
        dup = {n for n in names if names.count(n) > 1}
        if dup:
            raise ValueError(f"duplicate intake fields: {sorted(dup)}")
        if not self.actions:
            raise ValueError("scenario needs at least one action")
        ids = [a.id for a in self.actions]
        dup = {n for n in ids if ids.count(n) > 1}
        if dup:
            raise ValueError(f"duplicate action ids: {sorted(dup)}")
        if self.actions[0].when is not None:
            raise ValueError(f"first action {ids[0]!r} must not have a 'when' condition")
        for a in self.actions[1:]:
            if a.when is None:
                raise ValueError(f"action {a.id!r} needs a 'when' condition (only the first may omit it)")
        seen: set[str] = set()
        for a in self.actions:
            cond = a.condition
            if cond:
                unknown = cond.actions - seen
                if unknown:
                    raise ValueError(
                        f"action {a.id!r}: condition refers to {sorted(unknown)} "
                        f"which is not an earlier action"
                    )
                bad = cond.values - set(RESPONSE_CLASSES)
                if bad:
                    raise ValueError(
                        f"action {a.id!r}: unknown response value(s) {sorted(bad)}; "
                        f"allowed: {', '.join(RESPONSE_CLASSES)}"
                    )
            seen.add(a.id)
            if a.addressee and a.addressee.party and a.addressee.party not in self.parties:
                raise ValueError(f"action {a.id!r}: addressee party {a.addressee.party!r} not in parties")
        field_names = set(names)
        for key, p in self.parties.items():
            for attr in ("name_field", "id_field", "email_field", "address_field"):
                ref = getattr(p, attr)
                if ref and ref not in field_names:
                    raise ValueError(f"parties.{key}.{attr} refers to unknown intake field {ref!r}")
        if self.claim and self.claim.amount_field and self.claim.amount_field not in field_names:
            raise ValueError(f"claim.amount_field refers to unknown intake field {self.claim.amount_field!r}")
        for lang in self.languages:
            if lang not in self.title:
                raise ValueError(f"title missing language {lang!r}")
        return self

    # ---- helpers -------------------------------------------------------
    def field(self, name: str) -> IntakeField:
        for f in self.intake:
            if f.name == name:
                return f
        raise KeyError(name)

    def action(self, action_id: str) -> ActionSpec:
        for a in self.actions:
            if a.id == action_id:
                return a
        raise KeyError(action_id)

    @property
    def is_draft(self) -> bool:
        """Not signed off by a lawyer → documents carry a DRAFT disclaimer."""
        return self.reviewed_at is None

    def todos(self) -> list[str]:
        """Everything still marked TODO (norm references to be confirmed by a lawyer)."""
        out = []
        for a in self.actions:
            for ref in a.norm_refs:
                if "TODO" in ref:
                    out.append(f"{self.id}:{a.id}: norm_ref {ref}")
            if a.deadline and "TODO" in a.deadline.norm_ref:
                days = a.deadline.calendar_days or a.deadline.business_days
                out.append(f"{self.id}:{a.id}: deadline {days} days — norm_ref {a.deadline.norm_ref}")
        return out
