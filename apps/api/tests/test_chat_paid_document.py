"""P0 02.10: the chat gave a whole claim away for free («вот проект претензии…» with «(ваши ФИО)»). The chat never
writes a document out: «да, покажите» after an offer, «составьте претензию» → the paid offer (card «Услуга /
Стоимость / Оплатить»), no model call; a reply that writes a document anyway is cut to the short answer + the offer."""
from __future__ import annotations

from konsilier.api.chat import looks_like_document
from konsilier.chat import ChatAgent
from konsilier.core.models import ChatMessage
from konsilier.lawagent.sources import Adilet

from .test_chat import StreamingClient, _sse
from .test_e2e import web_user
from .test_lawagent import fake_fetch
from .test_payment import ANSWERS, STORY

CLAIM = ("Можно потребовать возврат денег.\n[[MORE]]\nВот проект претензии:\n\nКому: (наименование продавца)\n"
         "От: (ваши ФИО)\n\nПРЕТЕНЗИЯ\nПрошу вернуть 180 000 тенге.\nДата: ____  Подпись: ____")


def _agent(*texts):
    return ChatAgent(StreamingClient([([t], "end_turn", []) for t in texts]), "claude-haiku-4-5", Adilet(fetch=fake_fetch))


def _case(ctx):
    from .test_e2e import run_intake
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    run_intake(api, cid, ANSWERS)
    return api, cid


def _say(ctx, api, cid, text):
    return _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": text}))[-1]["message"]


def test_yes_after_the_offer_is_the_paid_offer_without_the_model(ctx):
    agent = _agent("Можно вернуть деньги.\n[[MORE]]\n1. Напишите продавцу.\nСоставлю претензию с вашими данными.\n[[DOCUMENT]]")
    ctx.container.chat_agent = agent
    api, cid = _case(ctx)
    _say(ctx, api, cid, "Продавец не возвращает деньги, что делать?")  # no offer in the first reply (owner 30.09)
    agent.client.turns.append((["Можно вернуть деньги.\n[[MORE]]\nСоставлю претензию с вашими данными.\n[[DOCUMENT]]"], "end_turn", []))
    assert _say(ctx, api, cid, "Чек есть, телефон за 180 000")["offer_document"]
    calls = len(agent.client.calls)
    reply = _say(ctx, api, cid, "Да, покажите")
    assert len(agent.client.calls) == calls  # no model call
    assert reply["offer_document"] and "PDF и Word" in reply["text"] and "2 990 ₸" in reply["text"]
    assert "Кому" not in reply["text"] and "(ваши" not in reply["text"]
    doc = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert doc["price"] == 2990 and doc["paid"] is False and doc["title"]


def test_asking_for_the_document_text_gets_the_offer(ctx):
    ctx.container.chat_agent = _agent(CLAIM)
    api, cid = _case(ctx)
    reply = _say(ctx, api, cid, "Составьте мне претензию")
    assert reply["offer_document"] and reply["text"].startswith("Документ: ")


def test_a_written_out_document_is_cut(ctx):
    ctx.container.chat_agent = _agent(CLAIM)
    api, cid = _case(ctx)
    reply = _say(ctx, api, cid, "А что мне делать дальше?")
    assert reply["offer_document"] and "Можно потребовать возврат денег." in reply["text"]
    assert "Кому" not in reply["text"] and "ПРЕТЕНЗИЯ" not in reply["text"] and "(ваши ФИО)" not in reply["text"]
    with ctx.container.session_factory() as s:
        saved = [m.text for m in s.query(ChatMessage).filter_by(role="assistant")]
    assert not any("(ваши ФИО)" in t for t in saved)


def test_document_signs():
    assert looks_like_document(CLAIM)
    assert not looks_like_document("Прошу заметить: срок — 10 дней. Напишите продавцу претензию.")
    assert not looks_like_document("Можно вернуть деньги. **Напишите претензию продавцу.**")


def test_the_prompt_forbids_writing_the_document():
    from konsilier.chat import PAID_DOCUMENT_RULE
    assert "Never write the text of a claim" in PAID_DOCUMENT_RULE and "{offer_marker}" in PAID_DOCUMENT_RULE


def test_the_offer_is_in_the_persons_language_with_the_price(ctx):
    from konsilier.api.chat import offer_text
    pack = ctx.container.packs.pack("KZ")
    kk = offer_text({"title": "Сатушыға наразылық", "price": 1990.0, "currency": "₸"}, "kk", pack)
    assert kk.startswith("Құжат: Сатушыға наразылық") and "1 990 ₸" in kk and "Документ" not in kk
    ru = offer_text({"title": None, "price": 1990.0, "currency": "₸", "price_from": True}, "ru", pack)
    assert "от 1 990 ₸" in ru


def test_kazakh_yes_after_the_offer(ctx):
    ctx.container.chat_agent = _agent("Ақшаны қайтаруға болады.\n[[MORE]]\nНаразылық дайындаймын.\n[[DOCUMENT]]",
                                      "Ақшаны қайтаруға болады.\n[[MORE]]\nНаразылық дайындаймын.\n[[DOCUMENT]]")
    api, cid = _case(ctx)
    for text in ("Сатушы ақшаны қайтармайды", "Чек бар"):
        ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": text, "language": "kk"})
    r = ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Иә, көрсетіңіз", "language": "kk"})
    reply = _sse(r)[-1]["message"]
    assert reply["offer_document"] and reply["text"].startswith("Құжат:") and "₸" in reply["text"]


def test_the_first_reply_keeps_the_offer_once_the_scenario_is_known(ctx):
    ctx.container.chat_agent = _agent("Можно вернуть деньги.\n[[MORE]]\nСоставлю претензию продавцу.\n[[DOCUMENT]]")
    api, cid = _case(ctx)  # the case already has its scenario
    assert _say(ctx, api, cid, "Магазин не возвращает деньги за телевизор")["offer_document"]
    doc = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert doc["title"] and doc["price"] == 2990 and doc["price_from"] is False


def test_the_ways_to_solve_it_carry_the_full_case_price(ctx):
    """Owner 02.10: under the answer — «Составить документ» (its price), «Дело под ключ» (its price), «Нанять юриста»."""
    from .test_e2e import web_user

    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Купил телевизор, через неделю сломался, деньги не возвращают",
                                                  "country": "KZ"})["case"]["id"]
    offer = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert offer["price"] and offer["case_price"] == float(ctx.container.engine.config.case_price)
    assert offer["case_paid"] is False
