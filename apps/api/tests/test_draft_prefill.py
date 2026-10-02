"""Owner 01.10 (iPhone): «Данные собраны», yet the draft's fields were all empty though the goods, the date and the sum
had been told in the chat. The blanks are looked for in everything the person said before the draft is shown — once
per story — and what is said in the chat after «Данные собраны» fills them too."""

from __future__ import annotations

from konsilier.core import ai
from konsilier.core.models import Case, ChatMessage

from .test_e2e import web_user
from .test_fast_intake import STORY

TOLD = "Купил в ТОО «Техномир» 12.08.2026, заплатил 150000 тенге"


def _fake_extract(calls):
    def extract(llm, sc, pack, lang, text, pending, fields):
        calls.append(list(fields))
        found = {"purchase_date": "12.08.2026", "amount": "150000"}
        return {k: v for k, v in found.items() if k in fields and v in text}
    return extract


def to_draft(ctx):
    """«не помню» to every question: the draft keeps blanks."""
    ctx.container.engine.config.intake_max_questions = 4
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    case = api.get(f"/v1/cases/{cid}").json()
    for _ in range(40):
        if case["status"] != "intake" or case["question"] is None:
            break
        q = case["question"]
        case = api.answer(cid, "пропустить" if q["type"] == "evidence" else "не помню")["case"]
    return api, case


def _say(ctx, cid, text):
    with ctx.container.session_factory() as s:
        case = s.get(Case, __import__("uuid").UUID(cid))
        s.add(ChatMessage(case_id=case.id, user_id=None, role="user", text=text))
        s.commit()


def test_the_draft_takes_what_was_told(ctx, monkeypatch):
    api, case = to_draft(ctx)
    cid = case["id"]
    blanks = {b["field"] for b in api.get(f"/v1/cases/{cid}/draft").json()["blanks"]}
    assert blanks & {"purchase_date", "amount"}, blanks
    calls: list = []
    monkeypatch.setattr(ai, "extract_fields", _fake_extract(calls))
    _say(ctx, cid, TOLD)
    after = {b["field"] for b in api.get(f"/v1/cases/{cid}/draft").json()["blanks"]}
    assert not after & {"purchase_date", "amount"} and after < blanks
    assert len(calls) == 1
    api.get(f"/v1/cases/{cid}/draft")  # the same story: no second model call
    assert len(calls) == 1


def test_the_chat_fills_blanks_after_data_collected(ctx, monkeypatch):
    _, case = to_draft(ctx)
    cid = case["id"]
    assert case["status"] == "qualified"
    monkeypatch.setattr(ai, "extract_fields", _fake_extract([]))
    import uuid
    with ctx.container.session_factory() as s:
        filled = ctx.container.engine.facts_from_chat(s, uuid.UUID(cid), TOLD)
        s.commit()
    assert {"purchase_date", "amount"} & set(filled)
