"""Owner 02.10 (decisions 225, 226; QA BUG-25): the documents asked are waited for. With the facts in but no file, the
solution waits for one reminder; «нет» / «позже» or a file — the solution."""

from __future__ import annotations

from .test_chat_flood_dialog import SOLUTION, _flood, _say

REMIND = "Пока не вижу документов"


def test_one_reminder_then_the_solution(ctx):
    api, cid = _flood(ctx, "Когда это случилось?", "Какую сумму вы требуете?", SOLUTION, SOLUTION)
    assert "Пришлите" in _say(ctx, api, cid, "Меня затопил сосед сверху, испорчен потолок и обои в комнате")["text"]
    _say(ctx, api, cid, "Сосед этажом выше, 25.09.2026, лопнула труба.")
    r3 = _say(ctx, api, cid, "Ущерб 450 000 тенге, сосед платить отказывается.")  # facts in, no file, no «нет»
    assert r3["text"].startswith(REMIND) and "Что делать" not in r3["text"] and not r3["offer_document"]
    r4 = _say(ctx, api, cid, "Документов нет")
    assert r4["text"].startswith("Что делать:") and REMIND not in r4["text"]  # reminded once only


def test_no_reminder_when_the_person_says_later(ctx):
    api, cid = _flood(ctx, "Когда это случилось?", SOLUTION)
    _say(ctx, api, cid, "Меня затопил сосед сверху")
    r2 = _say(ctx, api, cid, "25.09.2026, ущерб 450 000 тенге, акт пришлю потом.")
    assert r2["text"].startswith("Что делать:")


def test_reminder_names_what_the_person_said(ctx):
    """PM 03.10: «акт КСК есть» — not «Пока не вижу документов», but «Вижу, у вас есть акт — приложите фото…»."""
    api, cid = _flood(ctx, "Когда это случилось?", "Какую сумму вы требуете?", SOLUTION, SOLUTION)
    _say(ctx, api, cid, "Меня затопил сосед сверху, испорчен потолок и обои в комнате")
    _say(ctx, api, cid, "Сосед этажом выше, 25.09.2026, лопнула труба.")
    r3 = _say(ctx, api, cid, "Ущерб 450 000 тенге, акт КСК есть.")
    assert r3["text"].startswith("Вижу, у вас есть акт — приложите фото") and REMIND not in r3["text"]
    assert "Что делать" not in r3["text"] and not r3["offer_document"]
    r4 = _say(ctx, api, cid, "нет")
    assert r4["text"].startswith("Что делать:")  # one reminder, «нет» goes on
