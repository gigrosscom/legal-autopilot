"""Owner 02.10 (decisions.md): understand the gist → ask for the documents → questions only if still short → solution.
The chat model gets the scenario's documents, what came, the facts known and the facts still missing (names,
addresses and IDs are left to the form)."""

from __future__ import annotations

import uuid

from konsilier.api.chat import intake_note
from konsilier.chat import FACTS_FIRST_RULE
from konsilier.core.models import Case

from .test_e2e import web_user


def test_rule_asks_for_documents_once():
    r = " ".join(FACTS_FIRST_RULE.split())
    assert "Documents first" in r and "documents_to_ask" in r and "Ask once" in r
    assert "never asked again" in r


def test_note_for_a_refund_case(ctx):
    text = "Купил телефон Samsung за 250000 тенге в магазине «Технодом» 10.09.2026, сломался, деньги не возвращают."
    cid = web_user(ctx).post("/v1/cases", expect=201, json={"text": text, "country": "KZ"})["case"]["id"]
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        assert case.scenario_id == "kz.consumer.refund"
        note = intake_note(ctx.container, case, "ru")
    assert "Чек или квитанция об оплате" in note["documents_to_ask"]
    assert not note["documents_received"]
    # the parties' details go to the form before payment — except the other side's name («кому», R-29: one list with
    # the offer's gate, engine.facts_missing)
    assert not any(n.endswith(("_name", "_address", "_iin", "_phone")) for n in note["facts_missing"] if n != "seller_name")
    assert not any(n.startswith("applicant_") for n in note["facts_missing"])
    assert set(note["facts_missing"]).isdisjoint(note["facts_known"])


def test_no_note_without_scenario(ctx):
    with ctx.container.session_factory() as s:
        assert intake_note(ctx.container, Case(scenario_id=None), "ru") == {}


def _say(ctx, reply):
    from .test_chat import _claude

    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _claude(reply), None


def _chat(ctx, api, cid, text):
    from .test_chat import _sse

    return _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": text}))


def test_server_asks_for_documents_once(ctx):
    api = web_user(ctx)
    story = "Купил телефон Samsung за 250000 тенге в магазине «Технодом», сломался, деньги не возвращают."
    cid = api.post("/v1/cases", expect=201, json={"text": story, "country": "KZ"})["case"]["id"]
    _say(ctx, "Когда вы купили телефон?")
    ev = _chat(ctx, api, cid, story)
    text = ev[-1]["message"]["text"]
    assert text.startswith("Когда вы купили телефон?") and "Пришлите фото или скан документов" in text
    assert "чек или квитанция об оплате" in text
    assert any(e.get("type") == "text" and "Пришлите" in e.get("text", "") for e in ev)  # streamed too
    ev = _chat(ctx, api, cid, "10.09.2026")
    assert "Пришлите" not in ev[-1]["message"]["text"]  # once per chat


def test_no_line_when_the_model_asked_or_answered(ctx):
    api = web_user(ctx)
    story = "Купил телефон Samsung за 250000 тенге в магазине «Технодом», сломался, деньги не возвращают."
    cid = api.post("/v1/cases", expect=201, json={"text": story, "country": "KZ"})["case"]["id"]
    _say(ctx, "Что делать:\n1. **Направьте претензию продавцу.**\n[[MORE]]\nПодробнее.")
    assert "Пришлите" not in _chat(ctx, api, cid, story)[-1]["message"]["text"]  # a solution, not a question
    cid = api.post("/v1/cases", expect=201, json={"text": story, "country": "KZ"})["case"]["id"]
    _say(ctx, "Пришлите фото чека. Когда вы купили телефон?")
    assert _chat(ctx, api, cid, story)[-1]["message"]["text"].count("Пришлите") == 1


def test_no_line_for_a_greeting(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Здравствуйте", "country": "KZ"})["case"]["id"]
    _say(ctx, "Здравствуйте! Что у вас случилось?")
    assert "Пришлите" not in _chat(ctx, api, cid, "Здравствуйте")[-1]["message"]["text"]
