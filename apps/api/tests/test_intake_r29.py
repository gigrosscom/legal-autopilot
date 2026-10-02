"""Owner 02.10 (R-29, decision 226): not a solution and not a document while who, whom, what, when, how much is not
known — the bot asks the next missing fact instead; and when the bot asks for documents, the chat offers
«Сфотографировать» / «Приложить файл» under that answer."""

from __future__ import annotations

import uuid

from konsilier.api.chat import asks_for_files
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
    with ctx.container.session_factory() as s:  # the seller is not known yet
        c = s.get(Case, uuid.UUID(cid))
        c.facts = {k: v for k, v in c.facts.items() if k != "seller_name"}
        s.commit()
    assert ctx.container.engine.facts_missing(c) == ["seller_name"]
    _say(ctx, api, cid, "Продавец не возвращает деньги, что делать?")
    reply = _say(ctx, api, cid, "Чек есть, телефон за 180 000")
    assert not reply["offer_document"]
    assert "продав" in reply["text"].lower().split("[[more]]")[-1] or "Продав" in reply["text"]  # the seller is asked
    doc = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert doc["ready"] is False
    # «составьте документ» does not jump over the missing fact either
    reply = _say(ctx, api, cid, "Составьте претензию")
    assert not reply["offer_document"]


def test_the_bot_asking_for_documents_shows_the_upload_buttons(ctx):
    ctx.container.chat_agent = _agent("Пришлите фото чека и договора — я сам возьму из них данные.[[FILES]]")
    api, cid = _case(ctx)
    reply = _say(ctx, api, cid, "Купил телевизор, сломался")
    assert reply["ask_files"] is True and "[[FILES]]" not in reply["text"]
    assert asks_for_files("Приложите договор аренды.")[1] and not asks_for_files("Вы вправе вернуть деньги.")[1]


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
