"""Universal path (coverage level 2): build an ordinary ``Scenario`` from pack registry data.

No new engine: the generated scenario runs on the same CaseEngine and state machine. Everything legal
(addressee, deadline, norms, filing channels) comes from the pack's forum registry and document types;
where the pack has no data, norms stay "TODO" (the template prints a placeholder) and deadlines are absent.
The scenario is never reviewed (``reviewed_at=None``), so documents carry the DRAFT mark, and the engine
always requires a lawyer's approval for it.

Generic scenario ids encode their inputs so they can be rebuilt deterministically:
``<cc>.generic.<dispute with '.'→'__'>.<role>.<forum with '.'→'__'>``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .coverage.schema import DisputeType, Forum
from .scenario.schema import (
    ActionSpec,
    AddresseeSpec,
    ClaimSpec,
    IntakeField,
    PartySpec,
    PricingSpec,
    Scenario,
)

if TYPE_CHECKING:
    from .packs import JurisdictionPack

MARKER = "generic"


@dataclass(frozen=True)
class GenericRef:
    country: str
    dispute_id: str
    role: str
    forum_id: str

    @property
    def scenario_id(self) -> str:
        enc = lambda s: s.replace(".", "__")  # noqa: E731
        return f"{self.country.lower()}.{MARKER}.{enc(self.dispute_id)}.{self.role}.{enc(self.forum_id)}"

    @classmethod
    def parse(cls, scenario_id: str) -> "GenericRef | None":
        parts = scenario_id.split(".")
        if len(parts) != 5 or parts[1] != MARKER:
            return None
        dec = lambda s: s.replace("__", ".")  # noqa: E731
        return cls(parts[0].upper(), dec(parts[2]), parts[3], dec(parts[4]))


def is_generic(scenario_id: str | None) -> bool:
    return bool(scenario_id) and GenericRef.parse(scenario_id) is not None


def _loc(pack: "JurisdictionPack", key: str, **kw: str) -> dict[str, str]:
    return {lang: pack.t(lang, key, **kw) for lang in pack.manifest.languages}


def build_generic_scenario(pack: "JurisdictionPack", ref: GenericRef) -> Scenario:
    cov = pack.coverage
    if cov is None:
        raise KeyError(f"pack {pack.country} has no coverage registry")
    dispute: DisputeType = cov.dispute(ref.dispute_id)
    first: Forum = cov.forums[ref.forum_id]
    chain = [first, *cov.escalation_chain(first.id, dispute, ref.role)]

    steps: list[tuple[Forum, object]] = []
    for forum in chain:
        doc = cov.document_for(forum)
        if doc is None:
            break  # the pack has no document type for this forum: stop, the lawyer takes over
        steps.append((forum, doc))
    if not steps:
        raise KeyError(f"no document type for forum {first.id}")

    intake: list[IntakeField] = []
    seen: set[str] = set()
    for _, doc in steps:
        for fld in doc.required_fields:
            if fld.name not in seen:
                intake.append(fld)
                seen.add(fld.name)
    intake.append(IntakeField(name="evidence", type="evidence", evidence_kinds=("other",), optional=True))
    names = {f.name for f in intake}

    parties = {
        "applicant": PartySpec(kind="person", name_field="applicant_name",
                               id_field="applicant_iin" if "applicant_iin" in names else None,
                               address_field="applicant_address" if "applicant_address" in names else None),
        "respondent": PartySpec(kind="person" if set(dispute.counterparty_kinds) <= {"person"} else "business",
                                name_field="respondent_name"),
    }

    actions: list[ActionSpec] = []
    for i, (forum, doc) in enumerate(steps, 1):
        instructions = {
            lang: tuple(
                pack.t(lang, f"generic.instructions.{ch.kind}", url=ch.url or "", email=ch.email or "",
                       addressee=pack.localized(forum.name, lang))
                for ch in forum.submission
            ) + (pack.t(lang, "generic.instructions.mark_submitted"),)
            for lang in pack.manifest.languages
        }
        deadline = forum.response_deadline
        actions.append(ActionSpec(
            id=f"step_{i}",
            title={lang: pack.t(lang, "generic.action_title", document=pack.localized(doc.title, lang),
                                forum=pack.localized(forum.name, lang))
                   for lang in pack.manifest.languages},
            template=doc.template,
            addressee=AddresseeSpec(forum=forum.id),
            deadline=deadline,
            norm_refs=(deadline.norm_ref,) if deadline else ("TODO",),
            when=None if i == 1 else f"step_{i - 1}.response in [none, refusal, partial]",
            instructions=instructions,
            demands={lang: "{formal_demands}" for lang in pack.manifest.languages},
        ))
    actions.append(ActionSpec(
        id="handoff_lawyer", kind="handoff", title=_loc(pack, "generic.handoff_title"),
        when=f"step_{len(steps)}.response in [none, refusal, partial]",
    ))

    title = {lang: dispute.title.get(lang) or next(iter(dispute.title.values()))
             for lang in pack.manifest.languages}
    return Scenario(
        id=ref.scenario_id, version="1.0.0", ontology=dispute.id, jurisdiction=pack.country,
        languages=pack.manifest.languages, owner="generic", reviewed_at=None, published=False,
        title=title, summary={}, claim=ClaimSpec(type="generic", amount_field="amount") if "amount" in names else None,
        intake=[f.model_dump() for f in intake], parties=parties, actions=tuple(actions), pricing=PricingSpec(model="free"),
    )
