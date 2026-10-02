"""PM 02.10: «Дела» showed «Новое дело · Определяем путь» for good. A chat case whose first message said too little
(«Здравствуйте, нужна помощь») was classified as «no keywords» once and never looked at again, though the person told
the story in the chat afterwards. Each new chat message now tries again with everything told so far."""

from __future__ import annotations

import uuid

from konsilier.core.models import Case, ChatMessage

from .test_e2e import web_user


def _vague_case(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Здравствуйте, нужна помощь", "country": "KZ",
                                                  "defer": True})["case"]["id"]
    pk = uuid.UUID(cid)
    with ctx.container.session_factory() as s:
        ctx.container.engine.qualify_later(s, pk)
        s.commit()
    assert ctx.client.get(f"/v1/cases/{cid}", headers=api.h).json()["coverage"]["level"] == "pending"
    return api, cid, pk


def _say(ctx, pk, text):
    with ctx.container.session_factory() as s:
        s.add(ChatMessage(case_id=pk, user_id=None, role="user", text=text))
        s.commit()
        done = ctx.container.engine.requalify_from_chat(s, pk)
        s.commit()
        return done


def test_the_story_told_in_the_chat_classifies_the_case(ctx):
    api, cid, pk = _vague_case(ctx)
    assert _say(ctx, pk, "Купил телевизор, через неделю сломался, магазин не возвращает деньги")
    view = ctx.client.get(f"/v1/cases/{cid}", headers=api.h).json()
    assert view["coverage"]["level"] != "pending" and view["scenario"] is not None
    with ctx.container.session_factory() as s:
        assert s.get(Case, pk).initial_text == "Здравствуйте, нужна помощь"  # the first message stays as written


def test_still_unclear_is_tried_once_per_new_message(ctx):
    api, cid, pk = _vague_case(ctx)
    assert not _say(ctx, pk, "Спасибо")
    with ctx.container.session_factory() as s:
        assert not ctx.container.engine.requalify_from_chat(s, pk)  # nothing new: no model call
        assert s.get(Case, pk).taxonomy["chat_messages"] == 1
    assert _say(ctx, pk, "Меня уволили и не выплатили зарплату за два месяца")


def test_a_classified_case_is_left_alone(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Купил телевизор, через неделю сломался, магазин не возвращает деньги",
                                                  "country": "KZ"})["case"]["id"]
    pk = uuid.UUID(cid)
    before = ctx.client.get(f"/v1/cases/{cid}", headers=api.h).json()["scenario"]
    assert not _say(ctx, pk, "Меня уволили и не выплатили зарплату")
    assert ctx.client.get(f"/v1/cases/{cid}", headers=api.h).json()["scenario"] == before
