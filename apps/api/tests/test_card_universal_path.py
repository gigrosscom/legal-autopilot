"""P0 03.10 (prod a73a9ee, browser): a divorce / property division in the chat — «Детей нет, документов нет. Составьте
иск.» got «Что делать:» with no card, and «да давайте» got the documents reminder or the offer line again. The case
had its dispute but no recipient: only the case page picked it (get_case), the chat never did, so there was no
scenario and nothing to offer. The chat picks the recipient now, and «да» after a card is the card again."""

from __future__ import annotations

import uuid

import pytest

from konsilier.core import ai, qualifier
from konsilier.core.models import Case

from .test_chat_paid_document import _agent, _say
from .test_e2e import web_user

SOL = ("Что делать:\n1. **Подайте иск о разделе** в районный суд.\n[[MORE]]\n"
       "Составлю исковое заявление с вашими данными — готовый PDF и Word.")
FIRST = "Развожусь с женой. Хочу разделить квартиру, купленную в браке. Она против."


@pytest.mark.parametrize("dispute", ["family.property_division", "family.divorce"])
def test_a_dispute_without_a_recipient_gets_its_card(ctx, monkeypatch, dispute):
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: (None, 0.0, "no scenario fits"))
    ctx.container.settings.background_jobs = "off"  # as on prod: the background classification has not finished
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent("Пришлите документы. Есть ли дети?", SOL,
                                                                         SOL, SOL), None
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": FIRST, "country": "KZ", "defer": True})["case"]["id"]
    _say(ctx, api, cid, FIRST)
    with ctx.container.session_factory() as s:  # the dispute is known, the recipient is not (prod state)
        c = s.get(Case, uuid.UUID(cid))
        c.taxonomy = {"dispute_id": dispute, "role": "spouse", "domain": "family"}
        c.coverage_level = qualifier.LEVEL_UNIVERSAL
        s.commit()
    r = _say(ctx, api, cid, "Детей нет, документов нет. Составьте иск.")
    assert r["offer_document"], r["text"]
    card = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert card["ready"] is True and card["title"], card
    again = _say(ctx, api, cid, "да давайте")
    assert again["offer_document"] and "Пришлите фото" not in again["text"], again["text"]


def test_a_direct_dispute_classifies_when_the_taxonomy_model_is_down(ctx, monkeypatch):
    """P0 03.10 (prod 32901b3, browser): the chat classified nothing — a debt by a receipt, a labour claim, a divorce —
    so «Составить документ» never showed. The cause: the classification model errors on prod (quota), and the universal
    router called it without catching, so even a dispute the words already decide («расписка», «долг») crashed the
    whole classification and the case stayed «pending». The router now routes on the words when the model is down, so a
    direct-rule dispute still classifies offline and the card can appear. Both models raise here, as on prod."""
    def boom(*a, **k):
        raise RuntimeError("taxonomy/qualify model down (quota)")
    monkeypatch.setattr(ai, "qualify", boom)
    monkeypatch.setattr(ai, "classify_taxonomy", boom)
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    ctx.container.settings.background_jobs = "off"
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent("Опишите подробнее.", SOL, SOL, SOL), None
    api = web_user(ctx)
    debt = "Одолжил знакомому 500 000 тенге под расписку, срок прошёл, деньги не возвращает."
    cid = api.post("/v1/cases", expect=201, json={"text": debt, "country": "KZ", "defer": True})["case"]["id"]
    _say(ctx, api, cid, debt)
    _say(ctx, api, cid, "Расписка есть. Составьте иск.")  # the words decide the dispute (civil.debt), no model needed
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        assert c.scenario_id or (c.taxonomy or {}).get("dispute_id"), (c.scenario_id, c.taxonomy, c.coverage_level)


def test_a_universal_case_without_a_dispute_is_classified_again(ctx, monkeypatch):
    """PM 03.10: the case went to the universal path with no dispute (the model was unsure); requalify_from_chat
    skipped every non-«verified» case, so it never got a scenario and never a card."""
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: (None, 0.0, "no scenario fits"))
    ctx.container.settings.background_jobs = "off"
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent("Пришлите документы.", SOL, SOL, SOL), None
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": FIRST, "country": "KZ", "defer": True})["case"]["id"]
    _say(ctx, api, cid, FIRST)
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        c.taxonomy, c.coverage_level = {}, qualifier.LEVEL_UNIVERSAL
        s.commit()
    r = _say(ctx, api, cid, "Детей нет, документов нет. Составьте иск.")
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).scenario_id
    assert r["offer_document"], r["text"]
    assert api.get(f"/v1/cases/{cid}/chat/document").json()["ready"] is True
