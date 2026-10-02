"""PM 02.10 P0 after #216 (prod @914d384, flooding): «Ущерб примерно 450 000 тенге» was not read into the case, so the
chat asked «Какую сумму вы требуете…?» again and again, and «Да, составьте претензию» got the same question. The sum
and the date are read by rule (no model), and a question asked and answered is never asked again."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from konsilier.core import ai
from konsilier.core.fields import date_in_text, money_in_text, parse_money
from konsilier.core.models import Case

from .test_chat_flood_dialog import SOLUTION, _flood, _say

ASK_SUM = "Какую сумму вы требуете — во сколько оцениваете ущерб, в тенге?"


@pytest.fixture
def no_model_extraction(monkeypatch):
    """As on prod: the model reads nothing from the chat."""
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})


def test_flood_dialog_reaches_the_solution_and_the_card(ctx, no_model_extraction):
    api, cid = _flood(ctx, "Был ли акт от КСК?", SOLUTION, SOLUTION)
    _say(ctx, api, cid, "Меня затопил сосед сверху")
    r2 = _say(ctx, api, cid, "Сосед этажом выше, 25.09, лопнула труба")
    assert ASK_SUM in r2["text"] and "Что делать" not in r2["text"]
    r3 = _say(ctx, api, cid, "Ущерб примерно 450 000 тенге, акт от КСК есть, сосед платить отказывается")
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        assert c.facts.get("claim_amount") == "450000.00" and c.facts.get("event_date", "").endswith("-09-25")
        assert not ctx.container.engine.facts_missing(c)
    assert r3["text"].startswith("Что делать:") and ASK_SUM not in r3["text"]
    r4 = _say(ctx, api, cid, "Да, составьте претензию")
    assert r4["offer_document"] and ASK_SUM not in r4["text"]


def test_a_question_answered_is_not_asked_again(ctx, no_model_extraction):
    api, cid = _flood(ctx, "Был ли акт?", SOLUTION, SOLUTION)
    _say(ctx, api, cid, "Меня затопил сосед сверху")
    assert ASK_SUM in _say(ctx, api, cid, "Сосед этажом выше, 25.09, лопнула труба")["text"]
    r3 = _say(ctx, api, cid, "Не знаю точно, ремонт ещё не считали")  # answered, no sum
    assert ASK_SUM not in r3["text"] and r3["text"].startswith("Что делать:")  # the solution with what there is
    r4 = _say(ctx, api, cid, "Да, составьте претензию")
    assert ASK_SUM not in r4["text"]


def test_sums_and_dates_in_plain_words():
    today = date(2026, 10, 2)
    assert money_in_text("Ущерб примерно 450 000 тенге, акт есть") == Decimal("450000.00")
    assert money_in_text("450 тыс") == Decimal("450000.00") and parse_money("450 тыс") == Decimal("450000.00")
    assert money_in_text("долг 1,5 млн тенге") == Decimal("1500000.00")
    assert money_in_text("позвоните 87011234567, это было в 2026 году") is None
    assert date_in_text("Сосед этажом выше, 25.09, лопнула труба", today) == date(2026, 9, 25)
    assert date_in_text("15 декабря", today) == date(2025, 12, 15)  # not in the future
