"""The most requested topics in Kazakhstan: benefits, business grants, study grants and scholarships, tenders.

The taxonomy gains four branches (social, education, business, procurement); the site's life situations point at them,
so the chat suggests their examples; the beta scenarios pick up typical stories while EXPERIMENTAL_SCENARIOS is on;
and stories that were routed before keep their route."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from konsilier.core import qualifier
from konsilier.core.coverage import global_taxonomy
from konsilier.core.llm.mock import HeuristicMockProvider
from konsilier.core.packs import load_pack

from .test_e2e import web_user
from .test_pilot_drafts import PACKS

KZ = load_pack(PACKS / "kz", PACKS)
NEW_BRANCHES = ("social", "education", "business", "procurement")
NEW_SCENARIOS = ("kz.social.benefit_application", "kz.social.benefit_refusal_appeal", "kz.business.state_grant")
SITUATIONS_TS = Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "situations.ts"
WEB_DICTS = Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "dict"


def _situations() -> dict[str, list[str]]:
    """key → topics, read from the site's list of life situations."""
    text = SITUATIONS_TS.read_text("utf-8")
    return {m.group(1): re.findall(r'"([^"]+)"', m.group(2))
            for m in re.finditer(r'key: "(\w+)".*?topics: \[([^\]]*)\]', text)}


def _classify(cov, text: str) -> str | None:
    return HeuristicMockProvider()._classify_taxonomy(
        {"text": text, "disputes": qualifier.taxonomy_options(cov, "ru")})["dispute_id"]


# ---------------------------------------------------------------- taxonomy
def test_new_branches_are_in_the_taxonomy_with_examples():
    branches = {b.id: b for b in global_taxonomy().branches}
    for bid in NEW_BRANCHES:
        b = branches[bid]
        assert {"ru", "kk", "en", "ar", "tr"} <= set(b.title) and {"ru", "kk", "en", "ar", "tr"} <= set(b.situation)
        for d in b.disputes:
            assert {"ru", "kk", "en"} <= set(d.title), d.id
            assert d.keywords.get("ru") and d.keywords.get("kk"), d.id
            assert len(d.examples.get("ru", ())) >= 2 and d.examples.get("kk") and d.examples.get("en"), d.id


def test_new_disputes_do_not_capture_old_stories():
    """Keyword fallback (and the mock model) on every example that existed before: no story moves to a new branch."""
    cov = KZ.coverage
    old_texts = [ex for d in cov.disputes.values() if d.branch not in NEW_BRANCHES for ex in d.examples.get("ru", ())]
    old_texts += [ex for sc in KZ.scenarios.values() if sc.published for ex in sc.classification.examples.get("ru", ())]
    assert old_texts
    for text in old_texts:
        got = _classify(cov, text)
        assert got is None or cov.dispute(got).branch not in NEW_BRANCHES, (text, got)


def test_new_disputes_classify_their_own_examples():
    cov = KZ.coverage
    for bid in NEW_BRANCHES:
        for d in (d for d in cov.disputes.values() if d.branch == bid):
            for text in d.examples["ru"]:
                got = _classify(cov, text)
                assert got and cov.dispute(got).branch == bid, (d.id, text, got)


def test_benefit_refusal_keeps_the_route_of_a_state_body_refusal():
    """Before the social branch a refused benefit was a refusal by a state body: same bodies now."""
    cov = KZ.coverage
    old = {f.id for f in cov.candidate_forums(cov.dispute("administrative.state_body_inaction"), "complainant")}
    new = {f.id for f in cov.candidate_forums(cov.dispute("social.benefit_refusal"), "complainant")}
    assert new and new == old


# ---------------------------------------------------------------- site → examples
def test_every_situation_topic_exists_in_the_taxonomy():
    situations = _situations()
    assert {"benefits", "grants", "study", "tenders"} <= set(situations)
    ids = list(KZ.coverage.disputes)
    for key, topics in situations.items():
        assert topics, key
        for t in topics:
            assert any(d == t or d.startswith(t + ".") for d in ids), (key, t)


def test_every_situation_is_translated_in_every_language():
    keys = set(_situations())
    for path in sorted(WEB_DICTS.glob("*.ts")):
        if path.name == "types.ts":
            continue
        text = path.read_text("utf-8")
        block = text[text.index("  situations: {"):text.index("\n  },", text.index("  situations: {"))]
        for key in keys:
            m = re.search(rf"\n    {key}: \{{(.*)\}},", block)
            assert m, (path.name, key)
            for field in ("label", "hint", "placeholder", "ex1", "ex2", "ex3", "ex4"):
                assert f"{field}: " in m.group(1), (path.name, key, field)


@pytest.mark.parametrize("key,word", [("benefits", "пособ|помощ|выплат"), ("grants", "грант|финансир"),
                                      ("study", "грант|стипенд|поступ|вуз|университет"),
                                      ("tenders", "тендер|госзакуп|заявк|конкурс|аукцион")])
def test_new_situations_bring_their_suggestions(ctx, key, word):
    topics = _situations()[key]
    for experimental in (True, False):  # production (beta off) speaks through the taxonomy's examples
        ctx.container.packs.experimental = experimental
        out = ctx.client.get("/v1/examples", params={"topics": ",".join(topics), "lang": "ru", "limit": 4}).json()
        assert len(out["examples"]) == 4, (key, experimental, out)
        assert all(re.search(word, e.lower()) for e in out["examples"]), (key, out["examples"])
        kk = ctx.client.get("/v1/examples", params={"topics": ",".join(topics), "lang": "kk"}).json()["examples"]
        assert kk, (key, experimental)


def test_old_situations_keep_their_suggestions(ctx):
    for key, topics in _situations().items():
        if key in ("benefits", "grants", "study", "tenders"):
            continue
        ex = ctx.client.get("/v1/examples", params={"topics": ",".join(topics), "lang": "ru", "limit": 12}).json()
        texts = [e.lower() for e in ex["examples"]]
        assert not any(re.search("пособи|грант|стипенд|тендер|госзакуп", t) for t in texts), (key, texts)


# ---------------------------------------------------------------- scenarios
def test_new_beta_scenarios_are_unpublished_drafts():
    for sid in NEW_SCENARIOS:
        sc = KZ.scenarios[sid]
        assert sc.beta and not sc.published and sc.reviewed_at is None, sid
        assert sc.taxonomy and KZ.coverage.dispute(sc.taxonomy).branch in NEW_BRANCHES


def test_story_opens_the_beta_scenario_when_experimental(ctx):
    ctx.container.packs.experimental = True
    api = web_user(ctx)
    stories = {
        "kz.social.benefit_application": "Как оформить пособие при рождении ребёнка, какие документы нужны",
        "kz.social.benefit_refusal_appeal": "Отказали в назначении пособия по инвалидности, хочу обжаловать отказ",
        "kz.business.state_grant": "Хочу получить грант на новую бизнес-идею, какие документы и бизнес-план нужны",
    }
    for sid, text in stories.items():
        case = api.post("/v1/cases", expect=201, json={"text": text, "country": "KZ"})["case"]
        assert case["scenario"]["id"] == sid, (text, case["scenario"])
        assert case["scenario"]["beta"] is True


def test_production_routing_of_a_benefit_refusal(ctx):
    """Beta off: no scenario; the universal path offers the same bodies as for any refusal by a state body."""
    ctx.container.packs.experimental = False
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={
        "text": "Отказали в назначении пособия по инвалидности, хочу обжаловать отказ", "country": "KZ"})
    case = created["case"]
    assert case["coverage"]["dispute"]["id"] == "social.benefit_refusal"
    assert case["coverage"]["level"] == "universal"
    # the system takes the prosecutor's office; the ombudsman is «Другой адресат» (owner 02.10)
    assert case["coverage"]["forum"]["id"] == "kz.prosecutor"
    assert {o["id"] for o in case["coverage"]["other_forums"]} == {"kz.ombudsman"}
