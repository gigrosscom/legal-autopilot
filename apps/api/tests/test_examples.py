"""Chat suggestions come from the scenarios and the taxonomy, so every new scenario brings its own."""

from __future__ import annotations


def test_examples_follow_the_topic(ctx):
    fines = ctx.client.get("/v1/examples", params={"topics": "administrative.fine_appeal", "lang": "ru"}).json()
    assert fines["examples"] and all("штраф" in e.lower() for e in fines["examples"])
    family = ctx.client.get("/v1/examples", params={"topics": "family", "lang": "ru"}).json()["examples"]
    assert len(family) == 4 and len(set(family)) == 4
    assert any("алимент" in e.lower() for e in family)  # the published scenario
    # disputes with no scenario yet speak through the taxonomy's examples
    assert any("развест" in e.lower() or "ребён" in e.lower() or "квартир" in e.lower() for e in family)


def test_a_new_scenario_brings_its_examples(ctx):
    sc = next(s for s in ctx.container.packs.published("KZ") if s.taxonomy == "family.alimony")
    ex = set(sc.classification.examples["ru"])
    seen = set()
    for _ in range(20):
        seen |= set(ctx.client.get("/v1/examples", params={"topics": "family", "lang": "ru", "limit": 12})
                    .json()["examples"])
    assert ex <= seen


def test_examples_in_a_language_without_them_are_empty_not_russian(ctx):
    out = ctx.client.get("/v1/examples", params={"topics": "family", "lang": "tr"}).json()
    assert out["examples"] == []  # the site falls back to its own texts
