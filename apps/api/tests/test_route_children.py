"""ZANN 03.10: the divorce route branches on common children under 18 (checked on old.adilet.zan.kz, К1100000518):
with them only the court, the juvenile one (CMF art. 19 p. 2 sub. 1; CPC art. 27 p. 3); without them, with consent and
no claims — the registry office (CMF art. 17 p. 1), else the district court by the respondent's residence (art. 19
p. 2 sub. 2–4; CPC art. 29). Unknown — the step that names both."""

from __future__ import annotations

from pathlib import Path

import pytest

from konsilier.core.packs import PackRegistry
from konsilier.core.safety import minor_children

from .test_e2e import web_user

COV = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ").coverage


@pytest.mark.parametrize("text,expect", [
    ("Хочу развестись, у нас двое детей, 5 и 9 лет", "yes"),
    ("Муж не даёт развод, сыну 3 года", "yes"),
    ("Хочу развестись, детей у нас нет", "no"),
    ("Развод, общих несовершеннолетних детей нет, муж против", "no"),
    ("Развод, дети уже взрослые", "no"),
    ("Ажырасқым келеді, балаларымыз жоқ", "no"),
    ("Ажырасқым келеді, екі балам бар", "yes"),
    ("Хочу развестись с мужем", "unknown"),
    ("", "unknown"),
])
def test_children_by_the_persons_words(text, expect):
    assert minor_children(text) == expect


def test_the_divorce_route_by_children():
    route = COV.routes["family.divorce"]
    yes, no, unknown = (route.steps_for(c) for c in ("yes", "no", "unknown"))
    assert [s.forum for s in yes] == ["kz.court.juvenile"] and "ст. 19 п. 2 пп. 1" in yes[0].norm
    assert [s.forum for s in no] == ["kz.court.district"] and "ст. 17 п. 1" in no[0].norm
    assert "ЗАГС" in no[0].why["ru"] and "АХАЖ" in no[0].why["kk"]
    # PM 03.10 (family sweep F1): the children's court only with children; unknown — the district court, the person is
    # asked about the children and the court follows
    assert [s.forum for s in unknown] == ["kz.court.district"] and "по делам несовершеннолетних" in unknown[0].label["ru"]


def test_routes_without_children_steps_are_unchanged():
    for key, route in COV.routes.items():
        if all(s.children is None for s in route.steps):
            assert route.steps_for("yes") == route.steps_for("no") == route.steps_for("unknown") == route.steps


@pytest.mark.parametrize("text,forum", [
    ("Хочу развестись с женой, у нас дочь 4 года", "kz.court.juvenile"),
    ("Хочу развестись с женой, детей нет, она против развода", "kz.court.district"),
])
def test_a_divorce_case_goes_to_the_court_its_children_decide(ctx, text, forum):
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": text, "country": "KZ"})["case"]
    if (case.get("coverage") or {}).get("forum") is None:
        pytest.skip("the test model did not classify it as a divorce")
    assert case["coverage"]["forum"]["id"] == forum
    steps = api.get(f"/v1/cases/{case['id']}").json()["recipients"]
    assert [s["key"] for s in steps] == [forum]


def test_own_residence_only_outside_the_big_cities():
    """CPC art. 30 p. 7 (checked 03.10): a divorce claim by the claimant's residence when the children live with them —
    except district courts of the capital, cities of republican significance and regional centres. Never promised
    without the exception."""
    for step in COV.routes["family.divorce"].steps:
        for lang, word in (("ru", "областн"), ("kk", "облыс орталығ")):
            text = step.why[lang]
            if ("своему" in text) if lang == "ru" else ("өз тұрғылықты" in text):
                assert word in text, (step.children, lang)


def test_birth_certificates_only_in_the_childrens_court(ctx):
    """PM 03.10 (family sweep F1): «свидетельство о рождении ребёнка» was asked in a divorce without children."""
    from konsilier.core.generic import GenericRef

    packs = ctx.container.engine.packs
    kinds = {}
    for forum in ("kz.court.juvenile", "kz.court.district"):
        sc = packs.scenario(GenericRef("KZ", "family.divorce", "spouse", forum).scenario_id)
        kinds[forum] = {k for f in sc.intake if f.type == "evidence" for k in f.evidence_kinds}
    assert {"marriage_certificate", "birth_certificate"} <= kinds["kz.court.juvenile"]
    assert "marriage_certificate" in kinds["kz.court.district"] and "birth_certificate" not in kinds["kz.court.district"]


def test_children_told_later_move_the_case_to_the_childrens_court(ctx):
    import uuid

    from konsilier.core.models import Case

    from .test_chat_flood_dialog import _flood
    from .test_chat_paid_document import _say

    api2, _ = _flood(ctx, "Есть ли у вас общие дети до 18 лет?", "Понял.")
    case = api2.post("/v1/cases", expect=201, json={"text": "Хочу развестись с мужем, он против", "country": "KZ"})["case"]
    if (case.get("coverage") or {}).get("forum") is None:
        import pytest
        pytest.skip("the test model did not classify it as a divorce")
    assert case["coverage"]["forum"]["id"] == "kz.court.district"
    _say(ctx, api2, case["id"], "У нас дочь, ей 6 лет")
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(case["id"]))
        assert c.forum_id == "kz.court.juvenile", c.forum_id


def test_the_divorce_claim_has_its_demand_norm_and_no_price(ctx):
    """PM 03.10 (family sweep): the claim read «прошу суд: [чего вы хотите добиться]», «цена иска: не указана», no norm."""
    from konsilier.core.generic import GenericRef

    sc = ctx.container.engine.packs.scenario(GenericRef("KZ", "family.divorce", "spouse", "kz.court.district").scenario_id)
    step = sc.actions[0]
    assert step.demands["ru"].startswith("1. Расторгнуть брак") and "{formal_demands}" not in step.demands["ru"]
    assert step.demands["kk"].startswith("1. ") and "некені" in step.demands["kk"]
    assert step.norm_refs == ("КоБС РК, ст. 19 п. 1, 2",)
    assert COV.routes["family.divorce"].claim_unpriced


def test_the_template_says_unpriced():
    import zipfile

    x = zipfile.ZipFile(Path(__file__).parents[3] / "packs/kz/templates/generic/lawsuit.docx").read("word/document.xml").decode()
    assert "{% elif unpriced %}не подлежит оценке" in x
