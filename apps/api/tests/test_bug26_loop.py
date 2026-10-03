"""BUG-26 part 3 (prod dc5de58, PM's screenshot, flooding): the model kept asking «труба в квартире соседа или
стояк?»; «Больше ничего нет, нет. Составьте претензию» did not end it — no card, no button, no document. The
person's own request ends the interview at once: the document card with its buttons, then the form, payment and
the document."""

from __future__ import annotations

import pytest

from konsilier.core import ai

from .test_bug26_chat_to_document import _value
from .test_chat_paid_document import _agent, _say
from .test_e2e import web_user

PIPE = "Пришлите фото акта КСК. И один вопрос: труба лопнула в квартире соседа или это стояк между этажами?"
AGAIN = "Уточните, пожалуйста: труба в квартире соседа или стояк (общий)?"


@pytest.mark.parametrize("model_down", [False, True], ids=["model", "model_down"])
@pytest.mark.parametrize("ask", ["Больше ничего нет, нет. Составьте претензию", "Составьте претензию",
                                 "Достаточно, дайте решение"])
def test_a_request_ends_the_pipe_question_loop(ctx, monkeypatch, ask, model_down):
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    if model_down:
        monkeypatch.setattr(ai, "qualify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429")))
    ctx.container.settings.background_jobs = "inline"
    ctx.container.engine.config.approval_required_first_n = 0
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent(PIPE, AGAIN, AGAIN, AGAIN), None
    api = web_user(ctx)
    first = "Затопил сосед, труба лопнула, ущерб 450000, акт КСК есть, сосед отказывается"
    cid = api.post("/v1/cases", expect=201, json={"text": first, "country": "KZ", "defer": True})["case"]["id"]
    assert not _say(ctx, api, cid, first)["offer_document"]
    r = _say(ctx, api, cid, ask)
    assert r["offer_document"] and "стояк" not in r["text"], r["text"]
    card = api.get(f"/v1/cases/{cid}/chat/document").json()
    assert card["ready"] is True and card["title"], card
    for _ in range(3):
        pay = api.c.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
        if pay.status_code != 422:
            break
        fields = pay.json()["detail"]["fields"]
        api.c.post(f"/v1/cases/{cid}/facts", headers=api.h, json={"values": {f["field"]: _value(f) for f in fields}})
    assert pay.status_code == 200, pay.json()
    nxt = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert nxt.status_code == 200, nxt.json()
    a = api.get(f"/v1/cases/{cid}").json()["actions"][0]
    assert a["downloadable"] and a["has_docx"]
