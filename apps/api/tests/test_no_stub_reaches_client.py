"""PM 03.10: a document with a template stub («TODO», «[норма: уточнит юрист]») is never given to a client. Unchecked
norms are left out of the document (engine.group_norms), whatever slips through is stopped by the check before
issue (core/docgate.py, #198), and the case view never lists an unchecked norm."""

from __future__ import annotations

from pathlib import Path

import pytest

from konsilier.core import docgate
from konsilier.core.engine import group_norms
from konsilier.core.packs import PackRegistry

KZ = PackRegistry.load(Path(__file__).resolve().parents[3] / "packs").pack("KZ")


@pytest.mark.parametrize("sc", list(KZ.scenarios.values()), ids=lambda sc: sc.id)
def test_no_unchecked_norm_goes_into_a_document(sc):
    for action in sc.actions:
        assert not [r for r in group_norms(action.norm_refs) if "TODO" in r], (sc.id, action.id)


def test_a_bare_stub_stops_the_document():
    words = tuple(KZ.coverage.routing.document_markers.get("*", ()))
    for text in ("Основание: TODO.", "Правовое основание: [норма: уточнит юрист]."):
        found = docgate.markers(text, words)
        assert found and found[0].kind == "marker", text


def test_the_case_view_lists_no_unchecked_norm(ctx):
    from .test_admin_documents import paid_document

    api, cid, _, _ = paid_document(ctx, "stub.check@mail.kz")
    engine = ctx.container.engine
    a = api.get(f"/v1/cases/{cid}").json()["actions"][0]
    spec = engine.packs.scenario(api.get(f"/v1/cases/{cid}").json()["scenario"]["id"]).action(a["action_id"])
    object.__setattr__(spec, "norm_refs", (*spec.norm_refs, "TODO"))  # as a scenario with an unchecked norm
    try:
        refs = api.get(f"/v1/cases/{cid}").json()["actions"][0]["norm_refs"]
    finally:
        object.__setattr__(spec, "norm_refs", tuple(r for r in spec.norm_refs if r != "TODO"))
    assert refs and not [r for r in refs if "TODO" in r], refs
