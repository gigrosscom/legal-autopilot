"""«Куда подать» (PM 02.10, owner's screenshots): the pre-trial step first, then the court, optional ways last; «the court
where your case already is» only when the person says so; concrete terms and norms instead of «уточнит юрист»."""

from __future__ import annotations

from pathlib import Path

from konsilier.core import qualifier, safety
from konsilier.core.packs import PackRegistry

REPO = Path(__file__).resolve().parents[3]


def _cov():
    return PackRegistry.load(REPO / "packs").pack("KZ").coverage


def test_private_debt_order_and_no_pending_court():
    cov = _cov()
    debt = cov.dispute("civil.debt")
    ids = [f.id for f in cov.candidate_forums(debt, "claimant")]
    assert ids == ["kz.counterparty.claim", "kz.court.district", "kz.mediation"]
    with_pending = [f.id for f in cov.candidate_forums(debt, "claimant", pending=True)]
    assert with_pending[-1] == "kz.court.pending"


def test_pending_comes_from_the_story():
    cov = _cov()
    assert safety.matter_pending(cov, "Суд уже назначил судебное заседание, номер дела 7599-26")
    assert not safety.matter_pending(cov, "Дал знакомому в долг по расписке, он не возвращает")
    route = qualifier.route_universal(cov, {"dispute_id": "civil.debt", "role": "claimant", "confidence": 0.9},
                                      pending=True)
    assert "pending" in route.flags and route.forums[-1].id == "kz.court.pending"


def test_debt_hints_cite_the_norms_and_every_hint_key_is_known():
    cov = _cov()
    known = set(cov.disputes) | {d.branch for d in cov.disputes.values()}
    for f in cov.forums.values():
        assert set(f.hints) <= known and set(f.mandatory_for) <= known, f.id
        for text in f.hints.values():
            assert {"ru", "kk"} <= set(text) and "уточнит юрист" not in text["ru"]
    claim = cov.forums["kz.counterparty.claim"].hints["civil.debt"]["ru"]
    assert "30 дней" in claim and "ст. 722" in claim
    court = cov.forums["kz.court.district"].hints["civil.debt"]["ru"]
    assert "ст. 29" in court and "3 года" in court and "ст. 178" in court and "ст. 135" in court


def test_forum_option_shows_pretrial_label_and_hint(ctx):
    engine = ctx.container.engine
    pack = PackRegistry.load(REPO / "packs").pack("KZ")
    cov = pack.coverage
    debt = cov.dispute("civil.debt")
    claim = engine.forum_option(pack, cov.forums["kz.counterparty.claim"], "ru", debt)
    assert claim["pretrial"] == "voluntary" and claim["deadline_known"] and "30 дней" in claim["hint"]
    court = engine.forum_option(pack, cov.forums["kz.court.district"], "ru", debt)
    assert court["pretrial"] is None and court["deadline_known"] and "уточнит юрист" not in court["name"]


def test_routes_cover_every_dispute_scenario_and_name_known_addressees():
    """Owner 02.10: the system chooses the addressee. Every scenario with a dispute chain has a route; every route
    key, forum and authority exists; the first step of a dispute route is one of its candidate forums."""
    pack = PackRegistry.load(REPO / "packs").pack("KZ")
    cov = pack.coverage
    for key, route in cov.routes.items():
        assert key in cov.disputes or key in pack.scenarios, key
        for step in route.steps:
            assert step.norm and {"ru", "kk"} <= set(step.label) and {"ru", "kk"} <= set(step.why), key
            if step.authority:
                assert step.authority in pack.manifest.authorities, key
        if key in cov.disputes:
            d = cov.dispute(key)
            assert cov.first_forum(key, cov.candidate_forums(d, d.applicant_roles[0])) is not None, key
    for sid, sc in pack.scenarios.items():
        if any(a.kind == "handoff" for a in sc.actions):
            assert sid in cov.routes, sid


def test_private_debt_case_gets_its_addressee_without_a_list(ctx):
    from .test_e2e import web_user

    ctx.container.engine.config.auto_recipient = True
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={
        "text": "Дал знакомому в долг 300000 тенге по расписке, он не возвращает", "country": "KZ"})["case"]
    assert case["coverage"]["level"] == "universal" and case["scenario"]["ontology"] == "civil.debt"
    assert case["coverage"]["forum"]["id"] == "kz.counterparty.claim"  # chosen by the system
    assert case["coverage"]["options"] == []
    route = case["recipients"]
    assert [s["kind"] for s in route] == ["forum", "forum"] and route[0]["key"] == "kz.counterparty.claim"
    assert "ст. 722" in route[0]["norm"] and route[1]["when"]
