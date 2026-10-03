"""QA BUG-12 (KPI case «жалоба на госорган»): it was a dead end before kz.gov.inaction_complaint (01.10). Kept as a
regression after the chat-intake changes of BUG-26: a complaint about an akimat that does not answer goes from the
chat to the document — the card, the form before payment, the payment and the document — with or without the model
that chooses the scenario."""

from __future__ import annotations

import uuid

import pytest

from konsilier.core import ai
from konsilier.core.models import Case

from .test_bug26_chat_to_document import _value
from .test_chat_paid_document import _agent, _say
from .test_e2e import web_user

FIRST = "Акимат района не отвечает на моё заявление уже два месяца, подавал через eOtinish 1 августа"
SOL = ("Что делать:\n1. **Подайте жалобу** в вышестоящий орган.\n2. Если не ответят — **иск в суд**.\n[[MORE]]\n"
       "Составлю жалобу с вашими данными — готовый PDF и Word.\n[[DOCUMENT]]")


@pytest.mark.parametrize("model_down", [False, True], ids=["model", "model_down"])
def test_a_complaint_about_an_akimat_ends_in_a_document(ctx, monkeypatch, model_down):
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: {})
    if model_down:
        monkeypatch.setattr(ai, "qualify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429")))
    ctx.container.settings.background_jobs = "inline"
    ctx.container.engine.config.approval_required_first_n = 0
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent("Какой номер у обращения?", SOL, SOL, SOL), None
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": FIRST, "country": "KZ", "defer": True})["case"]["id"]
    for text in (FIRST, "Номер обращения 123456, ответа нет", "Да, составьте жалобу"):
        _say(ctx, api, cid, text)
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).scenario_id == "kz.gov.inaction_complaint"
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
