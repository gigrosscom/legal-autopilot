"""Owner 02.10 (R-29, decision 226): not a solution and not a document while who, whom, what, when, how much is not
known — the bot asks the next missing fact instead; and when the bot asks for documents, the chat offers
«Сфотографировать» / «Приложить файл» under that answer."""

from __future__ import annotations

import uuid

from konsilier.api.chat import ASKED_DOCUMENTS
from konsilier.core.models import Case

from .test_chat_paid_document import _agent, _case, _say

OFFER = "Можно вернуть деньги.\n[[MORE]]\n1. Напишите продавцу.\nСоставлю претензию.\n[[DOCUMENT]]"


def test_complete_case_gets_the_offer(ctx):
    ctx.container.chat_agent = _agent(OFFER, OFFER)
    api, cid = _case(ctx)
    _say(ctx, api, cid, "Продавец не возвращает деньги, что делать?")
    assert _say(ctx, api, cid, "Чек есть, телефон за 180 000")["offer_document"]
    assert api.get(f"/v1/cases/{cid}/chat/document").json()["ready"] is True


def test_no_offer_while_a_fact_is_missing_the_fact_is_asked(ctx):
    ctx.container.chat_agent = _agent(OFFER, OFFER, OFFER)
    api, cid = _case(ctx)
    # what was bought is not known yet (a fact, not a requisite); the story's date is read by rule (PM 02.10), so the
    # fact taken away here is one the person's words do not hold
    ctx.container.engine.facts_from_chat = lambda *a, **k: []  # the model reads nothing from the chat here
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        c.facts = {k: v for k, v in c.facts.items() if k != "goods_description"}
        s.commit()
        assert ctx.container.engine.facts_missing(c) == ["goods_description"]
    reply = _say(ctx, api, cid, "Продавец не возвращает деньги, что делать?")
    assert not reply["offer_document"] and "кнопк" not in reply["text"].lower()
    assert "Что именно купили" in reply["text"]  # the missing fact is asked
    assert api.get(f"/v1/cases/{cid}/chat/document").json()["ready"] is False
    # PM 02.10 P0 (#216 looped): asked and answered — never asked again, the chat goes on with what there is
    again = _say(ctx, api, cid, "Чек есть, за 180 000")
    assert "Что именно купили" not in again["text"]


def test_the_bot_asking_for_documents_shows_the_upload_buttons(ctx):
    ctx.container.chat_agent = _agent("Пришлите фото чека и договора — я сам возьму из них данные.[[FILES]]")
    api, cid = _case(ctx)
    reply = _say(ctx, api, cid, "Купил телевизор, сломался")
    assert reply["ask_files"] is True and "[[FILES]]" not in reply["text"]
    assert ASKED_DOCUMENTS.search("Приложите договор аренды.") and not ASKED_DOCUMENTS.search("Вы вправе вернуть деньги.")


def test_the_chat_and_the_card_name_the_same_document(ctx):
    """PM 02.10 (flooding): the chat «Составлю исковое заявление», the card «Досудебная претензия» — the card is
    withheld, the case is flagged for a second look; once they agree, the card is back."""
    lawsuit = "Можно взыскать ущерб.\n[[MORE]]\nСоставлю исковое заявление к соседу.\n[[DOCUMENT]]"
    ctx.container.chat_agent = _agent(OFFER, lawsuit, OFFER)
    api, cid = _case(ctx)  # the case's document is a claim to the seller
    _say(ctx, api, cid, "Продавец не возвращает деньги, что делать?")
    reply = _say(ctx, api, cid, "Что дальше?")
    assert not reply["offer_document"]
    assert api.get(f"/v1/cases/{cid}/chat/document").json()["ready"] is False
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).needs_review is True
    assert _say(ctx, api, cid, "Хорошо")["offer_document"]  # «Составлю претензию» again: the card is back
    assert api.get(f"/v1/cases/{cid}/chat/document").json()["ready"] is True
