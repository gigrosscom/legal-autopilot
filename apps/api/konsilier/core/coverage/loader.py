"""Load and cross-validate a pack's coverage data (taxonomy, forums, document types, routing)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from .schema import (
    DEFENCE_ROLES,
    Branch,
    DisputeType,
    DocumentType,
    Forum,
    GlobalTaxonomy,
    PackTaxonomy,
    Routing,
)

GLOBAL_TAXONOMY_PATH = Path(__file__).with_name("global_taxonomy.yaml")


class CoverageValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@lru_cache(maxsize=1)
def global_taxonomy() -> GlobalTaxonomy:
    return GlobalTaxonomy.model_validate(yaml.safe_load(GLOBAL_TAXONOMY_PATH.read_text("utf-8")))


@dataclass
class Coverage:
    """Everything a pack knows about the universal path. Pure data + lookups, no country logic."""

    country: str
    branches: dict[str, Branch]
    disputes: dict[str, DisputeType]
    forums: dict[str, Forum]
    documents: dict[str, DocumentType]
    routing: Routing
    has_registry: bool = field(default=False)

    # ---- lookups -------------------------------------------------------
    def dispute(self, dispute_id: str) -> DisputeType:
        return self.disputes[dispute_id]

    def candidate_forums(self, dispute: DisputeType, role: str) -> list[Forum]:
        """First-instance forums that accept this dispute and role."""
        return [f for f in self.forums.values() if f.instance != "appeal" and f.accepts_case(dispute, role)]

    def auto_forum(self, forums: list[Forum]) -> Forum | None:
        """The step's recipient chosen by the system (owner 02.10): the first candidate in the pack's forum_order;
        none when the order names none of them (then the person is asked one question, not shown a list)."""
        order = self.routing.forum_order
        if not order:
            return forums[0] if len(forums) == 1 else None
        ranked = sorted((f for f in forums if f.id in order), key=lambda f: order.index(f.id))
        return ranked[0] if ranked else (forums[0] if len(forums) == 1 else None)

    def escalation_chain(self, forum_id: str, dispute: DisputeType, role: str) -> list[Forum]:
        """Forums reached by following appeals_to from forum_id (first accepting target each step)."""
        chain: list[Forum] = []
        seen = {forum_id}
        current = self.forums[forum_id]
        while True:
            nxt = next((self.forums[t] for t in current.appeals_to
                        if t not in seen and self.forums[t].accepts_case(dispute, role)), None)
            if nxt is None:
                return chain
            chain.append(nxt)
            seen.add(nxt.id)
            current = nxt

    def document_for(self, forum: Forum) -> DocumentType | None:
        for doc_id in forum.document_types:
            if doc_id in self.documents:
                return self.documents[doc_id]
        return None

    def is_lawyer_only(self, dispute: DisputeType, role: str) -> bool:
        return role in DEFENCE_ROLES or dispute.id in self.routing.lawyer_only or dispute.branch in self.routing.lawyer_only

    # ---- review status -------------------------------------------------
    def review_rows(self) -> list[tuple[str, str, str, str]]:
        """(kind, id, status, verified_by) for REVIEW.md."""
        rows: list[tuple[str, str, str, str]] = []
        for f in self.forums.values():
            rows.append(("forum", f.id, "проверено" if f.verified else "TODO", f.verified_by or "—"))
        for d in self.documents.values():
            rows.append(("document", d.id, "проверено" if d.verified_at else "TODO", d.verified_by or "—"))
        r = self.routing
        for key, checked in (("upl_notice", r.upl_notice), ("false_report_norm", r.false_report_norm)):
            if checked:
                rows.append(("routing", key, "проверено" if checked.verified_at else "TODO", "—"))
        for n in r.emergency.numbers:
            rows.append(("emergency", n.number, "проверено" if n.verified_at else "TODO", "—"))
        if r.high_amount_threshold is None:
            rows.append(("routing", "high_amount_threshold", "TODO", "—"))
        return rows


def _read(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text("utf-8"))
    except yaml.YAMLError as e:
        raise CoverageValidationError([f"{path}: YAML error: {e}"]) from e


def _validate(model: type[BaseModel], data: Any, source: str, errors: list[str]) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            errors.append(f"{source}: {loc}: {err['msg'].removeprefix('Value error, ')}")
        return None


def load_coverage(root: Path, packs_root: Path, country: str, languages: tuple[str, ...]) -> Coverage:
    errors: list[str] = []
    glob_tax = global_taxonomy()
    branches = {b.id: b for b in glob_tax.branches}
    disputes = {d.id: d for b in glob_tax.branches for d in b.disputes}

    tax_path = root / "taxonomy.yaml"
    if tax_path.is_file():
        tax = _validate(PackTaxonomy, _read(tax_path) or {}, str(tax_path), errors)
        if tax:
            prefix = country.lower() + "."
            for d in tax.add:
                if not d.id.startswith(prefix):
                    errors.append(f"{tax_path}: local dispute {d.id} must start with '{prefix}'")
                elif d.branch not in branches:
                    errors.append(f"{tax_path}: local dispute {d.id} refers to unknown branch {d.branch}")
                elif d.id in disputes:
                    errors.append(f"{tax_path}: duplicate dispute {d.id}")
                else:
                    disputes[d.id] = d
            for did in tax.disable:
                if did not in disputes:
                    errors.append(f"{tax_path}: cannot disable unknown dispute {did}")
                else:
                    del disputes[did]

    documents: dict[str, DocumentType] = {}
    for path in sorted((root / "documents").glob("*.yaml")):
        doc = _validate(DocumentType, _read(path), str(path), errors)
        if doc is None:
            continue
        if doc.id in documents:
            errors.append(f"{path}: duplicate document type {doc.id}")
        if not (packs_root / doc.template).is_file():
            errors.append(f"{path}: template not found: {doc.template}")
        documents[doc.id] = doc

    forums: dict[str, Forum] = {}
    forum_dir = root / "forums"
    for path in sorted(forum_dir.glob("*.yaml")):
        data = _read(path) or {}
        items = data.get("forums", []) if isinstance(data, dict) else []
        for i, item in enumerate(items):
            forum = _validate(Forum, item, f"{path}[{i}]", errors)
            if forum is None:
                continue
            if forum.id in forums:
                errors.append(f"{path}: duplicate forum {forum.id}")
            forums[forum.id] = forum

    for f in forums.values():
        for t in f.appeals_to:
            if t not in forums:
                errors.append(f"forum {f.id}: appeals_to unknown forum {t}")
        for rule in f.accepts:
            for b in rule.branches:
                if b not in branches:
                    errors.append(f"forum {f.id}: unknown branch {b}")
            for d in rule.dispute_types:
                if d not in disputes:
                    errors.append(f"forum {f.id}: unknown dispute type {d}")
        missing_langs = [lang for lang in languages if lang not in f.name]
        if missing_langs:
            errors.append(f"forum {f.id}: name missing languages {missing_langs}")
    errors += _cycles(forums)

    routing_path = root / "routing.yaml"
    routing = Routing()
    if routing_path.is_file():
        routing = _validate(Routing, _read(routing_path) or {}, str(routing_path), errors) or Routing()
        for ref in routing.lawyer_only:
            if ref not in branches and ref not in disputes:
                errors.append(f"{routing_path}: lawyer_only refers to unknown {ref}")

    if errors:
        raise CoverageValidationError(errors)
    return Coverage(country=country, branches=branches, disputes=disputes, forums=forums,
                    documents=documents, routing=routing, has_registry=bool(forums))


def _cycles(forums: dict[str, Forum]) -> list[str]:
    """Escalation graph must be acyclic."""
    state: dict[str, int] = {}
    errors: list[str] = []

    def visit(fid: str, path: list[str]) -> None:
        if state.get(fid) == 2 or fid not in forums:
            return
        if state.get(fid) == 1:
            errors.append("escalation cycle: " + " → ".join(path + [fid]))
            return
        state[fid] = 1
        for t in forums[fid].appeals_to:
            visit(t, path + [fid])
        state[fid] = 2

    for fid in forums:
        visit(fid, [])
    return errors
