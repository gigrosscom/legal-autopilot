"""ZANN 03.10 (PM decision on the family sweep F2–F4): a spouse protecting their own property (bought before the
marriage, a gift, an inheritance, a marriage contract) gets no divorce claim: a claim to have it recognised as personal
and kept out of the division (CMF art. 35, 38–40), or — when the other spouse's claim is already filed — a reply to
it (CPC art. 166). Norms checked on old.adilet.zan.kz."""

from __future__ import annotations

import pytest

from .test_e2e import web_user


def _case(ctx, text):
    api = web_user(ctx)
    return api, api.post("/v1/cases", expect=201, json={"text": text, "country": "KZ"})["case"]


@pytest.mark.parametrize("text", [
    "Разводимся с женой, она требует половину квартиры, но квартиру я купил за два года до свадьбы",
    "При разводе бывший муж хочет поделить дачу, которую мне подарили родители, и квартиру, которую я унаследовала",
    "Разводимся, у нас брачный договор, по нему дом остаётся мне",
])
def test_not_yet_filed_a_claim_to_keep_it_out(ctx, text):
    api, case = _case(ctx, text)
    assert case["coverage"]["dispute"]["id"] == "family.personal_property", case["coverage"]
    assert case["coverage"]["forum"]["id"] == "kz.court.district"
    sc = ctx.container.engine.packs.scenario(case["scenario"]["id"])
    step = sc.actions[0]
    assert step.title["ru"].startswith("Исковое заявление о признании имущества личной собственностью")
    assert "Исключить это имущество" in step.demands["ru"] and step.norm_refs == ("КоБС РК, ст. 35 п. 1, ст. 38 п. 1, ст. 39, 40",)


def test_already_filed_a_reply_to_the_claim(ctx):
    api, case = _case(ctx, "Жена подала в суд на раздел, требует половину квартиры, которую я купил до брака")
    assert case["coverage"]["dispute"]["id"] == "family.personal_property"
    assert case["coverage"]["forum"]["id"] == "kz.court.pending", case["coverage"]
    sc = ctx.container.engine.packs.scenario(case["scenario"]["id"])
    step = sc.actions[0]
    assert step.title["ru"] == "Отзыв на исковое заявление о разделе имущества"
    assert step.template.endswith("response.docx")
    assert step.demands["ru"].startswith("1. Отказать в иске в части раздела") and "ГПК РК, ст. 166" in step.norm_refs


def test_the_reply_template_is_a_reply():
    import zipfile
    from pathlib import Path

    x = zipfile.ZipFile(Path(__file__).parents[3] / "packs/kz/templates/generic/response.docx").read("word/document.xml").decode()
    assert "ОТЗЫВ НА ИСКОВОЕ ЗАЯВЛЕНИЕ" in x and "ХОДАТАЙСТВО" not in x and "Прошу суд:" in x


def test_alimony_is_not_taken_for_personal_property(ctx):
    from pathlib import Path

    from konsilier.core.packs import PackRegistry
    from konsilier.core.safety import direct_dispute

    cov = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ").coverage
    rule = direct_dispute(cov, "Бывший не платит алименты, квартира куплена до брака")
    assert rule is None or rule.dispute != "family.personal_property"


def test_the_sum_is_asked_as_the_property_value_and_never_in_a_divorce(ctx):
    """ZANN 03.10: «во сколько оцениваете ущерб» was asked in a property division; a divorce has no price at all."""
    from konsilier.core.generic import GenericRef

    eng = ctx.container.engine
    packs, pack = eng.packs, eng.packs.pack("KZ")
    div = packs.scenario(GenericRef("KZ", "family.divorce", "spouse", "kz.court.district").scenario_id)
    assert not {f.name for f in div.intake} & {"amount", "claim_amount"}
    assert eng.question_for(div, pack, "ru", "event_date").text == "Когда зарегистрирован брак?"
    for dispute in ("family.property_division", "family.personal_property"):
        sc = packs.scenario(GenericRef("KZ", dispute, "spouse", "kz.court.district").scenario_id)
        q = eng.question_for(sc, pack, "ru", "claim_amount").text
        assert "оцениваете имущество" in q and "ущерб" not in q
        assert "имущество" in eng.question_for(sc, pack, "kk", "claim_amount").text or "мүлік" in eng.question_for(sc, pack, "kk", "claim_amount").text


def test_child_residence_and_alimony_claims_have_demands_and_norms(ctx):
    from konsilier.core.generic import GenericRef

    packs = ctx.container.engine.packs
    res = packs.scenario(GenericRef("KZ", "family.child_residence", "parent", "kz.court.juvenile").scenario_id)
    assert res.actions[0].demands["ru"].startswith("1. Определить место жительства") and res.actions[0].norm_refs == ("КоБС РК, ст. 73 п. 2",)
    ali = packs.scenario(GenericRef("KZ", "family.alimony", "parent", "kz.court.juvenile").scenario_id)
    d = ali.actions[0].demands["ru"]
    assert "1/4" in d and "1/3" in d and "1/2" in d and "со дня обращения в суд" in d
    assert ali.actions[0].norm_refs == ("КоБС РК, ст. 138 п. 2, ст. 139 п. 1, ст. 164 п. 2",)
