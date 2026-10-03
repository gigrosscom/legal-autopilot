"""PM 02.10 (QA BUG-24 recheck): B5 «Знакомый взял у меня деньги в долг…» went to consumer.refund in 1 of 3 runs; B8
«Наш КСК собирает деньги…» went to consumer.poor_service every time. The words decide before the model: a loan to a
private person is a debt (Civil Code SP, loan), a КСК is the condominium's manager (Housing Relations Law art. 51-4,
51-6) — the housing scenario, not «a service's defects»."""

from __future__ import annotations

import pytest

from konsilier.core import ai

from .test_e2e import web_user

B5 = "Знакомый взял у меня деньги в долг и не возвращает уже долго. Как вернуть?"
B8 = "Наш КСК собирает деньги, а в доме ничего не ремонтируют. Куда обращаться?"


@pytest.fixture
def wrong_model(monkeypatch):
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: ("kz.consumer.refund", 0.9, "wrong guess"))
    monkeypatch.setattr(ai, "classify_taxonomy", lambda *a, **k: {"dispute_id": "consumer.poor_service",
                                                                   "role": "consumer", "confidence": 0.9})


def _case(ctx, text):
    return web_user(ctx).post("/v1/cases", expect=201, json={"text": text, "country": "KZ"})["case"]


@pytest.mark.parametrize("run", range(3))
def test_b5_debt_three_of_three(ctx, wrong_model, run):
    case = _case(ctx, B5)
    assert (case["coverage"].get("dispute") or {}).get("id") == "civil.debt"


@pytest.mark.parametrize("run", range(3))
def test_b8_ksk_three_of_three(ctx, wrong_model, run):
    case = _case(ctx, B8)
    assert case["scenario"]["id"] == "kz.housing.management_company"


def test_flood_from_above_is_still_damages(ctx, wrong_model):
    case = _case(ctx, "Сосед сверху затопил квартиру, КСК составил акт. Что делать?")
    assert (case["coverage"].get("dispute") or {}).get("id") == "civil.damages"
