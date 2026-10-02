"""QA BUG-24 (02.10): «долг по расписке» went to a consumer refund the first time and to the private debt on a repeat.
The words decide it now: the same answer every time, without the model's guess."""

from __future__ import annotations

import pytest

from konsilier.core import ai

from .test_e2e import web_user

DEBT = "Дал знакомому в долг 300000 тенге по расписке, срок прошёл, он не возвращает долг"


def test_debt_by_receipt_is_decided_by_the_words_five_times_out_of_five(ctx, monkeypatch):
    # even a model that would guess a consumer refund cannot move it
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: ("kz.consumer.refund", 0.9, "guess"))
    monkeypatch.setattr(ai, "classify_taxonomy", lambda *a, **k: {"dispute_id": "consumer.refund", "role": "consumer",
                                                                   "confidence": 0.9})
    for _ in range(5):
        case = web_user(ctx).post("/v1/cases", expect=201, json={"text": DEBT, "country": "KZ"})["case"]
        assert case["coverage"]["dispute"]["id"] == "civil.debt", case["coverage"]
        assert case["coverage"]["forum"]["id"] == "kz.counterparty.claim"


@pytest.mark.parametrize("text", [
    "Банк выдал кредит, долг по кредиту растёт, коллекторы звонят",
    "Купил в магазине товар, не возвращают деньги",
    "Контрагент ТОО не возвращает долг по договору поставки",
])
def test_bank_shop_or_business_is_not_a_private_debt(ctx, text):
    from konsilier.core import safety
    from konsilier.core.packs import PackRegistry
    from pathlib import Path
    cov = PackRegistry.load(Path(__file__).resolve().parents[3] / "packs").pack("KZ").coverage
    assert safety.direct_dispute(cov, text) is None


def test_kazakh_receipt():
    from konsilier.core import safety
    from konsilier.core.packs import PackRegistry
    from pathlib import Path
    cov = PackRegistry.load(Path(__file__).resolve().parents[3] / "packs").pack("KZ").coverage
    rule = safety.direct_dispute(cov, "Танысыма қолхатпен қарыз бердім, қарызды қайтармайды")
    assert rule is not None and rule.dispute == "civil.debt"


def test_defamation_has_a_route_not_a_dead_end(ctx):
    """QA BUG-23: «клевета, защита чести» had no scenario and stopped; now the universal path takes it."""
    text = "Коллега распространил обо мне ложные сведения в соцсетях, клевета, хочу опровержение"
    case = web_user(ctx).post("/v1/cases", expect=201, json={"text": text, "country": "KZ"})["case"]
    assert case["coverage"]["dispute"]["id"] == "civil.honor", case["coverage"]
    assert case["coverage"]["forum"]["id"] == "kz.counterparty.claim"
    assert "143" in case["recipients"][0]["norm"]
