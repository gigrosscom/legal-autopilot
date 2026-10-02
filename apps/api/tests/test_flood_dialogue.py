"""PM 02.10 (prod @f2f88c7, 19:52, flooding): after «Ущерб 450 000, акт от КСК есть, сосед отказывается» the bot
gave the 1-2-3 solution but no buttons; «Да, составьте претензию» got «…после нажатия кнопки „Составить документ“
ниже. Кто нарушил ваши права? …должность — если госорган» and still no button. The other side's name (and other
requisites) must not hold the offer back — the form before payment asks them; a hidden card is never mentioned."""

from __future__ import annotations

import uuid

from konsilier.api.chat import without_button_talk
from konsilier.core.models import Case

from .test_chat_paid_document import _agent, _say
from .test_e2e import web_user

SOLUTION = ("Сосед отвечает за ущерб от затопления.\n[[MORE]]\n1. Направьте соседу досудебную претензию.\n"
            "2. Приложите акт КСК.\n3. Если откажет — иск в суд.\n[[DOCUMENT]]")


def _flood(ctx, *replies):
    ctx.container.chat_agent = _agent(*replies)
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня затопил сосед сверху, ущерб 450 000 тенге, "
                                                  "лопнула труба 25.09.2026, акт от КСК есть, сосед отказывается",
                                                  "country": "KZ"})["case"]["id"]
    return api, cid


def test_the_neighbour_is_enough_the_solution_gets_its_buttons(ctx):
    api, cid = _flood(ctx, "Когда это случилось?", SOLUTION, SOLUTION)
    with ctx.container.session_factory() as s:
        assert ctx.container.engine.facts_missing(s.get(Case, uuid.UUID(cid))) == []  # «сосед», 450 000, 25.09
    _say(ctx, api, cid, "Меня затопил сосед сверху")
    reply = _say(ctx, api, cid, "Ущерб 450 000, акт от КСК есть, сосед отказывается")
    assert reply["offer_document"] is True  # the 1-2-3 solution with its buttons
    assert "Кто нарушил" not in reply["text"] and "Чего вы хотите добиться" not in reply["text"]
    assert api.get(f"/v1/cases/{cid}/chat/document").json()["ready"] is True
    reply = _say(ctx, api, cid, "Да, составьте претензию")  # the offer at once, no question about the neighbour
    assert reply["offer_document"] is True and "Кто нарушил" not in reply["text"]


def test_a_hidden_card_is_never_mentioned(ctx):
    api, cid = _flood(ctx, "Претензия будет готова после нажатия кнопки «Составить документ» ниже. Когда это было?")
    with ctx.container.session_factory() as s:  # a case still lacking a fact: no card
        c = s.get(Case, uuid.UUID(cid))
        c.scenario_id = c.scenario_id or None
        s.commit()
    reply = _say(ctx, api, cid, "Да, составьте претензию")
    if not reply["offer_document"]:
        assert "кнопк" not in reply["text"].lower()
    assert without_button_talk("Хорошо. Претензия будет готова после нажатия кнопки «Составить документ» ниже. "
                               "Когда это было?") == "Хорошо. Когда это было?"
