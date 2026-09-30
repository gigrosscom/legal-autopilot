"""Chat suggestions come from the scenarios and the taxonomy, so every new scenario brings its own."""

from __future__ import annotations

import re


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


# ---------------------------------------------------------------- ethics: suggestions are shown to strangers
SENSITIVE = re.compile(
    r"\b(умер|смерт|погиб|скончал|насил|избил|убий|суицид|кормил|инвалид|развод|развест|бывш|наслед|алаяқ|"
    r"қайтыс|өлі|өлген|зорлық|мүгедек|ажырас|мұра|died|death|dead\b|killed|abuse|violen|suicide|divorce|inherit)",
    re.IGNORECASE)
ALWAYS = re.compile(r"\b(умер|смерт|погиб|скончал|насил|избил|убий|суицид|қайтыс|өлген|зорлық|died|death|killed)",
                    re.IGNORECASE)


def _many(ctx, **params) -> set[str]:
    seen: set[str] = set()
    for _ in range(25):
        seen |= set(ctx.client.get("/v1/examples", params={"limit": 12, **params}).json()["examples"])
    return seen


def test_default_suggestions_are_neutral_and_everyday(ctx):
    """No topic chosen: nothing about death, violence, illness, divorce or inheritance, and no family/criminal area."""
    for experimental in (False, True):
        ctx.container.packs.experimental = experimental
        for lang in ("ru", "kk", "en"):
            seen = _many(ctx, lang=lang)
            assert seen, (lang, experimental)
            bad = [e for e in seen if SENSITIVE.search(e)]
            assert not bad, (lang, bad)
            assert all(len(e) <= 60 and e[:1].isupper() for e in seen), (lang, seen)
    cov = next(p.coverage for p in ctx.container.packs.packs.values() if p.coverage is not None)
    touchy = {e for d in cov.disputes.values() if d.branch in ("inheritance", "criminal", "family")
              and d.id != "family.alimony" for e in d.examples.get("ru", ())}
    assert touchy and not (_many(ctx, lang="ru") & touchy)


def test_chosen_topic_keeps_neutral_suggestions(ctx):
    inh = _many(ctx, topics="inheritance", lang="ru")
    assert inh and all("наслед" in e.lower() for e in inh)
    assert not any(ALWAYS.search(e) for e in inh), inh
    for topics in ("family", "criminal", "social", "finance", "labor"):
        for lang in ("ru", "kk", "en"):
            got = _many(ctx, topics=topics, lang=lang)
            assert not any(ALWAYS.search(e) for e in got), (topics, lang, got)


def test_death_and_violence_are_filtered_even_when_a_pack_has_them():
    from konsilier.core import suggestions

    assert not suggestions.allowed("Отец умер без завещания, как оформить наследство", prompted=True)
    assert not suggestions.allowed("Сосед избил меня во дворе", prompted=True)
    assert not suggestions.allowed("Әкем өсиетсіз қайтыс болды", prompted=True)
    assert not suggestions.allowed("My father died without a will", prompted=True)
    assert suggestions.allowed("Как оформить развод через суд", prompted=True)
    assert not suggestions.allowed("Как оформить развод через суд", prompted=False)
    assert suggestions.allowed("Как изменить условия кредита", prompted=False)
    assert suggestions.allowed("Бөлімшеге өтініш беру", prompted=False)  # "өлі" inside a word is not death
    assert suggestions.sensitive_area("inheritance.acceptance") and suggestions.sensitive_area("criminal")
    assert not suggestions.sensitive_area("family.alimony") and not suggestions.sensitive_area("consumer.refund")


def test_pack_and_taxonomy_examples_carry_no_tragedy(ctx):
    """Authors write examples neutrally; the filter is only the safety net."""
    texts = [e for p in ctx.container.packs.packs.values() for sc in p.scenarios.values()
             for exs in sc.classification.examples.values() for e in exs]
    texts += [e for p in ctx.container.packs.packs.values() if p.coverage is not None
              for d in p.coverage.disputes.values() for exs in d.examples.values() for e in exs]
    assert texts
    bad = [e for e in texts if ALWAYS.search(e) or re.search(r"кормил|инвалид|мүгедек|бывш|бұрынғы", e, re.I)]
    assert not bad, bad
