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
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

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


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _raw(pack: "JurisdictionPack", lang: str, *path: str) -> Any:
    """A raw i18n node (list or dict) for ``lang``, falling back to the pack's default language."""
    for candidate in (lang, pack.manifest.default_language):
        node: Any = pack.i18n.get(candidate, {})
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        if node is not None:
            return node
    return None


def filing_steps(pack: "JurisdictionPack", lang: str, forum: Forum, doc: Any) -> tuple[str, ...]:
    """Step-by-step filing instructions for one document: prepare → what to attach → the main channel in detail
    (per portal when the pack describes it) → other channels → mark as submitted. All text comes from pack data."""
    t = lambda key, **kw: pack.t(lang, f"generic.instructions.{key}", **kw)  # noqa: E731
    party = forum.type == "private_org"  # a claim to the other party itself, not to a body
    addressee = "{addressee}" if party else pack.localized(forum.name, lang)
    doc_title = pack.localized(doc.title, lang)
    steps: list[str] = [t("prepare", document=doc_title)]
    items = (doc.attachments.get(lang) or doc.attachments.get(pack.manifest.default_language) or ()) \
        if getattr(doc, "attachments", None) else ()
    if items:
        steps.append(t("attach", items="; ".join(items)))
    for i, ch in enumerate(forum.submission):
        kw = {"url": ch.url or "", "email": ch.email or "", "addressee": addressee, "document": doc_title}
        detailed = None
        if ch.kind == "portal" and ch.url:
            host = (urlparse(ch.url).hostname or "").removeprefix("www.")
            detailed = _raw(pack, lang, "generic", "portals", host)
        if i == 0 and isinstance(detailed, list):
            steps += [str(x).format_map(_Safe(kw)) for x in detailed]
            continue
        key = f"{ch.kind}_party" if party and ch.kind in ("email", "in_person") else ch.kind
        line = t(key, **kw)
        steps.append(line if i == 0 else t("alternative", step=line))
    steps.append(t("mark_submitted"))
    return tuple(steps)


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
    # a copy of the ID is attached to the document; personal data can also be typed in instead
    intake.append(IntakeField(name="identity_document", type="evidence", evidence_kinds=("id_document",),
                              optional=True))
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
        instructions = {lang: filing_steps(pack, lang, forum, doc) for lang in pack.manifest.languages}
        deadline = forum.response_deadline
        actions.append(ActionSpec(
            id=f"step_{i}",
            # a claim to the other party is titled by the document alone: the addressee is the respondent
            title={lang: pack.localized(doc.title, lang) if forum.type == "private_org" else
                   pack.t(lang, "generic.action_title", document=pack.localized(doc.title, lang),
                          forum=pack.localized(forum.name, lang))
                   for lang in pack.manifest.languages},
            template=doc.template,
            # a pre-trial claim goes to the other party itself; everything else to the body from the registry
            addressee=AddresseeSpec(party="respondent") if forum.type == "private_org" else AddresseeSpec(forum=forum.id),
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
