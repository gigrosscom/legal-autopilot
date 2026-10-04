"""BUG-26 (P0, prod 588be8b, 03.10): no case reached a document. A case led by the chat stayed in «Сбор информации»:
1) the chat answers only what the solution needs (R-29), the interview's own questions stayed open, so «Составить
документ» → 409 intake_incomplete (since intake_max_questions = 0, #208); 2) when the model that chooses the scenario
did not answer, the case had no scenario at all → no button, 409 no_document_path, payment 409. Now the open
questions become blanks of the form before payment, the keywords choose the scenario when the model is down, and the
dialog ends in a document: chat → «Составить документ» → the form → payment → PDF/Word."""

from __future__ import annotations

import uuid

import pytest

from konsilier.core import ai
from konsilier.core.models import Case

from .test_chat_paid_document import _agent, _say
from .test_e2e import web_user

SOL = ("Что делать:\n1. **Направьте претензию** на {sum} ₸.\n2. Если откажут — **иск в суд**.\n[[MORE]]\n"
       "Составлю документ с вашими данными — готовый PDF и Word.\n[[DOCUMENT]]")
CASES = {
    "refund": ["Купил телефон за 180 000 тенге, сломался через неделю, магазин не возвращает деньги",
               "В Технодоме 10 сентября", "документов нет, нет"],
    "debt": ["Дал в долг знакомому 500 000 тенге по расписке, не возвращает",
             "Давал 15 августа, срок возврата был 15 сентября", "Расписка есть, пришлю позже"],
    "flood": ["Сосед сверху затопил мою квартиру", "Сосед этажом выше, 25.09, лопнула труба",
              "Ущерб 450 000 тенге, акт КСК есть, пришлю позже"],
}
VALUE = {"date": "12.09.2026", "money": "180000", "phone": "+7 701 123 45 67"}


def _value(f: dict) -> str:
    n = f["field"]
    if f["type"] in VALUE:
        return VALUE[f["type"]]
    if n.endswith("address"):
        return "г. Алматы, ул. Абая, 10"
    if n.endswith("iin") or n.endswith("bin"):
        return "880101300123"
    if n.endswith("email"):
        return "client@mail.kz"
    if n == "applicant_name":
        return "Иванов Иван Иванович"
    return "ТОО «Техномир»" if n.endswith("name") else "Смартфон, сломался через неделю после покупки"


def _dialog(ctx, monkeypatch, kind: str, model_down: bool):
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})  # as on prod: the model reads nothing from the chat
    if model_down:
        def down(*a, **k):
            raise RuntimeError("429 quota exceeded")
        monkeypatch.setattr(ai, "qualify", down)
    ctx.container.settings.background_jobs = "inline"  # the chat's classification runs as on prod
    ctx.container.engine.config.approval_required_first_n = 0
    sol = SOL.format(sum="180 000")
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent("Когда это было?", "Сохранились документы?",
                                                                         sol, sol, sol, sol), None
    api = web_user(ctx)
    said = CASES[kind]
    cid = api.post("/v1/cases", expect=201, json={"text": said[0], "country": "KZ", "defer": True})["case"]["id"]
    for text in [*said, "Да, составьте документ"]:
        _say(ctx, api, cid, text)
    return api, cid


@pytest.mark.parametrize("model_down", [False, True], ids=["model", "model_down"])
@pytest.mark.parametrize("kind", list(CASES))
def test_the_chat_ends_in_a_document(ctx, monkeypatch, kind, model_down):
    api, cid = _dialog(ctx, monkeypatch, kind, model_down)
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).scenario_id, "the case has a document path"
    for _ in range(3):  # the form before payment: what the chat did not ask
        r = api.c.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
        if r.status_code != 422:
            break
        detail = r.json()["detail"]
        assert detail["code"] == "applicant_data_required", detail
        out = api.c.post(f"/v1/cases/{cid}/facts", headers=api.h,
                         json={"values": {f["field"]: _value(f) for f in detail["fields"]}})
        assert out.status_code == 200, out.json()
    assert r.status_code == 200, r.json()  # never 409 no_document_path / intake_incomplete
    nxt = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert nxt.status_code == 200, nxt.json()
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["status"] == "action_ready", case["status"]
    a = case["actions"][0]
    assert a["downloadable"] and a["has_docx"]


# prod d0868e0 (PM 03.10, browser): the model wrote the offer line without the [[DOCUMENT]] marker, a fact the solution
# waits for was never read from the chat — «Претензию подготовлю с вашими данными — готовый PDF и Word», no button
PROD_OFFER = ("Что делать:\n1. **Направьте продавцу претензию** о возврате денег.\n2. Если откажет — **иск в суд**.\n"
              "[[MORE]]\nПретензию подготовлю с вашими данными — готовый PDF и Word.")


@pytest.mark.parametrize("kind", list(CASES))
@pytest.mark.parametrize("ask", ["Нет, дайте решение", "Составьте претензию"])
def test_the_offer_line_brings_the_button(ctx, monkeypatch, kind, ask):
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429")))
    ctx.container.settings.background_jobs = "inline"
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent(
        "Когда это было?", PROD_OFFER, PROD_OFFER, PROD_OFFER), None
    api = web_user(ctx)
    said = CASES[kind]
    cid = api.post("/v1/cases", expect=201, json={"text": said[0], "country": "KZ", "defer": True})["case"]["id"]
    _say(ctx, api, cid, said[0])
    r = _say(ctx, api, cid, ask)  # the person says all they will at the 2nd message, nothing read from the chat
    assert r["offer_document"], r["text"]
    card = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert card["ready"] is True and card["title"], card  # the site shows «Составить документ» only when ready
    pay = api.c.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert pay.status_code in (200, 422), pay.json()  # the bill or the form before it — never 409


def test_one_short_stem_does_not_choose_the_scenario():
    """PM 03.10 (family sweep): «брак» — a defect, a refund keyword — is in «в браке», a marriage; with the model down
    a divorce went to «Возврат денег за товар». One stem alone decides nothing; two keywords or a phrase do."""
    from pathlib import Path

    from konsilier.core.engine import by_keywords
    from konsilier.core.packs import PackRegistry

    published = PackRegistry.load(Path(__file__).resolve().parents[3] / "packs").published("KZ")
    assert by_keywords(published, "Хочу развестись, мы в браке 8 лет, квартира куплена в браке")[0] is None
    assert by_keywords(published, CASES["refund"][0])[0] == "kz.consumer.refund"


# prod dc5de58 (PM 03.10, browser): the free model never gives a solution or an offer — it loops on a clarifying
# question («труба в квартире соседа или стояк?»). The person says «Составьте претензию», the model asks again, and the
# card «Составить документ» never appears → no document. Owner 03.10: once the intake has begun and the person asks
# for the document, the card appears with what there is; the blanks are filled in the form before payment.
LOOP = ["Труба в квартире соседа или это общий стояк?", "А когда именно это произошло?", "Понятно, уточните детали."]


@pytest.mark.parametrize("kind", list(CASES))
@pytest.mark.parametrize("ask", ["Составьте претензию", "Хватит вопросов, дайте решение"])
def test_the_clarifying_loop_still_brings_the_button(ctx, monkeypatch, kind, ask):
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429")))
    ctx.container.settings.background_jobs = "inline"
    # the model only ever asks another clarifying question: no «Что делать:», no [[MORE]], no offer line, no card
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent(*LOOP, *LOOP), None
    api = web_user(ctx)
    said = CASES[kind]
    cid = api.post("/v1/cases", expect=201, json={"text": said[0], "country": "KZ", "defer": True})["case"]["id"]
    first = _say(ctx, api, cid, said[0])
    assert not first["offer_document"], first["text"]  # documents-first: no card in the first reply
    r = _say(ctx, api, cid, ask)  # the person insists after the intake began — the card appears despite the loop
    assert r["offer_document"], r["text"]
    card = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert card["ready"] is True and card["title"], card  # «Составить документ» renders only when ready
    pay = api.c.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert pay.status_code in (200, 422), pay.json()  # the bill or the form before it — never 409 no_document_path


# prod dc5de58 (PM 03.10, browser root cause): classification runs in a background thread (background_jobs=thread), so
# when the person insists before it finishes, scenario_id is still unset → has_path is False → no card, the loop went
# on forever. background_jobs="off" reproduces it: the deferred requalify never runs, so the scenario is set only by
# the synchronous requalify the insistence now triggers.
@pytest.mark.parametrize("kind", list(CASES))
def test_insisting_classifies_now_when_the_background_job_has_not_run(ctx, monkeypatch, kind):
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429")))
    ctx.container.settings.background_jobs = "off"  # the background classification never runs — the prod race
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent(*LOOP, *LOOP), None
    api = web_user(ctx)
    said = CASES[kind]
    cid = api.post("/v1/cases", expect=201, json={"text": said[0], "country": "KZ", "defer": True})["case"]["id"]
    _say(ctx, api, cid, said[0])
    with ctx.container.session_factory() as s:
        assert not s.get(Case, uuid.UUID(cid)).scenario_id  # nothing classified it yet (the job was skipped)
    r = _say(ctx, api, cid, "Составьте претензию")  # the insistence classifies the case here and now
    assert r["offer_document"], r["text"]
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).scenario_id, "classified synchronously on the insistence"
    card = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert card["ready"] is True and card["title"], card
