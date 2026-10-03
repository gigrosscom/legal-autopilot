"""ZANN 03.10: a refused residence permit — a complaint to the higher body first, the court after it (АППК ст. 91
ч. 1, 3, 5; ст. 92 ч. 1, 1-1; checked on old.adilet.zan.kz). Removal stays with a lawyer (liberty at stake)."""

from __future__ import annotations

from pathlib import Path

from konsilier.core.packs import PackRegistry

PACK = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ")
COV = PACK.coverage


def test_residence_refusal_route():
    steps = COV.routes["migration.residence"].steps
    assert [s.forum for s in steps] == ["kz.gov.superior", "kz.court.district"]
    assert steps[0].norm.startswith("АППК РК, ст. 91 ч. 1, 3, ст. 92") and "3 месяцев" in steps[0].why["ru"]
    assert steps[1].norm == "АППК РК, ст. 91 ч. 5" and steps[1].when["ru"]


def test_the_higher_body_accepts_a_migrant():
    dispute = COV.dispute("migration.residence")
    forums = [f.id for f in COV.candidate_forums(dispute, "migrant")]
    assert "kz.gov.superior" in forums
    assert COV.auto_forum(COV.candidate_forums(dispute, "migrant"), "migration.residence").id == "kz.gov.superior"


def test_removal_stays_with_a_lawyer():
    assert "migration.removal" in COV.routing.lawyer_only
    assert "migration.removal" not in COV.routes


def test_a_refused_permit_case_gets_the_complaint(ctx):
    from .test_e2e import web_user

    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={
        "text": "Мне отказали в виде на жительство без объяснения причин, хочу обжаловать", "country": "KZ"})["case"]
    assert case["coverage"]["forum"]["id"] == "kz.gov.superior", case["coverage"]
    steps = api.get(f"/v1/cases/{case['id']}").json()["recipients"]
    assert [s["key"] for s in steps] == ["kz.gov.superior", "kz.court.district"]


def test_removal_words_are_not_the_residence_rule():
    from konsilier.core.safety import direct_dispute

    assert direct_dispute(COV, "Отказали в ВНЖ, хочу обжаловать").dispute == "migration.residence"
    assert direct_dispute(COV, "Тұруға ықтиярхат бермеді").dispute == "migration.residence"
    rule = direct_dispute(COV, "Суд вынес решение о выдворении, был вид на жительство")
    assert rule is None or rule.dispute != "migration.residence"
