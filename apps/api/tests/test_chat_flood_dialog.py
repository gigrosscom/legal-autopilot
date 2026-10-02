"""PM 02.10 P0 after #215 (prod @a241392, flooding): the solution and the buttons came at the 2nd message with the sum
and the act unknown, the documents were not asked, the steps were the route's raw labels and the 3rd reply repeated
the 2nd word for word. The dialog of 4 messages: question → documents → the solution with the person's facts → card."""

from __future__ import annotations

import uuid

from konsilier.core.models import Case

from .test_chat_paid_document import _agent, _say
from .test_e2e import web_user

FIRST = "Сосед сверху затопил мою квартиру. Что делать?"
SOLUTION = ("Что делать:\n1. **Направьте соседу претензию** на 450 000 ₸ с копией акта КСК.\n2. Если не заплатит — "
            "**иск в районный суд** по месту жительства соседа.\n[[MORE]]\n**Почему претензия.** Она фиксирует сумму и "
            "дату.\nСоставлю претензию соседу — готовый PDF и Word.\n[[DOCUMENT]]")
RAW = ("Что делать:\n1. **Подготовьте документы для суда.**\n2. **Подайте иск.**\n[[MORE]]\nСоставлю претензию.\n"
       "[[DOCUMENT]]")


def _flood(ctx, *replies):
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent(*replies), None
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": FIRST, "country": "KZ"})["case"]["id"]
    return api, cid


def _missing(ctx, cid):
    with ctx.container.session_factory() as s:
        return ctx.container.engine.facts_missing(s.get(Case, uuid.UUID(cid)))


def test_flood_dialog_question_documents_solution_card(ctx):
    api, cid = _flood(ctx, "Когда это случилось?", SOLUTION, SOLUTION)
    r1 = _say(ctx, api, cid, FIRST)
    assert r1["text"].startswith("Когда это случилось?") and "Пришлите" in r1["text"]  # 1: question + documents
    assert not r1["offer_document"]
    r2 = _say(ctx, api, cid, "Сосед сверху, 25.09.2026, у него лопнула труба.")
    assert _missing(ctx, cid), "the sum is not known yet"
    assert "[[MORE]]" not in r2["text"] and "Что делать" not in r2["text"]  # 2: no solution yet
    assert r2["text"].rstrip().endswith("?") and not r2["offer_document"]
    r3 = _say(ctx, api, cid, "Ущерб 450 000 тенге, акт КСК есть.")
    assert not _missing(ctx, cid)  # the sum of this very message is read before the reply
    assert r3["text"].startswith("Что делать:\n1. **Направьте соседу претензию** на 450 000 ₸")  # 3: the person's facts
    assert r3["text"] != r2["text"]
    r4 = _say(ctx, api, cid, "Да, составьте претензию")
    assert r4["offer_document"]  # 4: the card


def test_model_steps_against_the_route_fall_back_to_the_route(ctx):
    api, cid = _flood(ctx, RAW)
    with ctx.container.session_factory() as s:  # the facts are in: the solution may come
        c = s.get(Case, uuid.UUID(cid))
        for name in ctx.container.engine.facts_missing(c):
            c.facts = {**(c.facts or {}), name: "450000" if "amount" in name else "25.09.2026" if "date" in name
                       else "затопление из квартиры сверху"}
        s.commit()
    assert not _missing(ctx, cid)
    text = _say(ctx, api, cid, "Ущерб 450 000 тенге, акт есть, 25.09.2026.")["text"]
    assert text.startswith("Что делать:\n1. **Тот, кто причинил ущерб, — претензия**.")
    assert "Подготовьте документы для суда" not in text
