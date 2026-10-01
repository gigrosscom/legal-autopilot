"""A chat answer that broke off (the API restarting, a lost connection) is retried by the page with the same
idempotency key (``client_id``): the message is never stored twice nor counted twice against the daily limit, and an
answer that was already saved comes back instead of a new one. Also: the scheduler tick lock."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from konsilier.core.models import Case, ChatMessage

from .test_chat import Busy, _claude, _sse
from .test_e2e import web_user

KEY = "m-3f2a9c1e-retry"


def _case(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    return api, cid


def _send(ctx, api, cid, text="Когда должны рассчитаться?", key=KEY):
    return ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": text, "client_id": key})


def _rows(ctx):
    with ctx.container.session_factory() as s:
        return [(m.role, m.text, dict(m.meta or {})) for m in
                s.query(ChatMessage).order_by(ChatMessage.created_at, ChatMessage.id).all()]


class Counting:
    """Wraps an agent and counts the replies it was asked for."""

    def __init__(self, agent):
        self.agent, self.calls = agent, 0
        self.portal_domain, self.client = agent.portal_domain, agent.client

    def stream(self, *a, **k):
        self.calls += 1
        yield from self.agent.stream(*a, **k)


def test_retry_after_the_answer_was_saved_returns_it_without_a_new_reply(ctx):
    api, cid = _case(ctx)
    agent = Counting(_claude())
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = agent, None
    first = _sse(_send(ctx, api, cid))[-1]
    assert first["type"] == "done" and first["remaining"] == 39
    again = _sse(_send(ctx, api, cid))
    # only the saved answer comes back: no text chunks, no second call to the model
    assert [e["type"] for e in again] == ["done"] and agent.calls == 1
    assert again[0]["message"]["id"] == first["message"]["id"] and again[0]["remaining"] == 39
    assert [r[0] for r in _rows(ctx)] == ["user", "assistant"]
    assert [m["role"] for m in api.get(f"/v1/cases/{cid}/chat").json()] == ["user", "assistant"]
    # a new message (another key) is a new message and counts
    assert _sse(_send(ctx, api, cid, "А компенсация?", key="m-other-key-1"))[-1]["remaining"] == 38


def test_cut_stream_is_answered_on_retry_as_the_same_message_and_counted_once(ctx):
    api, cid = _case(ctx)
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _claude(), None
    # the first attempt reached the server (the message is saved) and its stream was cut before the answer was saved
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        asked = ChatMessage(case_id=case.id, user_id=case.owner_id, role="user", text="Когда должны рассчитаться?",
                            meta={"attachments": [], "client_id": KEY}, created_at=datetime.now(timezone.utc))
        s.add(asked)
        s.commit()
        asked_id = str(asked.id)
    ctx.container.settings.chat_daily_limit = 1  # the one free message is this one: its retry is not refused
    done = _sse(_send(ctx, api, cid))[-1]
    assert done["type"] == "done" and done["remaining"] == 0
    rows = _rows(ctx)
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert rows[1][2]["reply_to"] == asked_id
    # the limit is used up by that one message now
    assert _send(ctx, api, cid, "ещё", key="m-another-1").status_code == 429


def test_busy_then_retry_keeps_one_message(ctx):
    api, cid = _case(ctx)
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = Busy(), None
    ctx.container.settings.chat_daily_limit = 1
    for _ in range(2):  # «Повторить» while the models are busy: the same message, not counted
        assert _sse(_send(ctx, api, cid))[-1]["code"] == "busy"
    rows = _rows(ctx)
    assert [r[0] for r in rows] == ["user"] and rows[0][2].get("failed")
    ctx.container.chat_agent = _claude()
    done = _sse(_send(ctx, api, cid))[-1]
    assert done["type"] == "done" and done["remaining"] == 0
    rows = _rows(ctx)
    assert [r[0] for r in rows] == ["user", "assistant"] and "failed" not in rows[0][2]


def test_without_a_key_every_send_is_a_new_message(ctx):
    api, cid = _case(ctx)
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _claude(), None
    for _ in range(2):
        r = ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"})
        assert _sse(r)[-1]["type"] == "done"
    assert [r[0] for r in _rows(ctx)] == ["user", "assistant", "user", "assistant"]


def test_key_of_another_case_is_not_reused(ctx):
    api, cid = _case(ctx)
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _claude(), None
    _send(ctx, api, cid)
    cid2 = api.post("/v1/cases", expect=201, json={"text": "Сосед затопил квартиру", "country": "KZ"})["case"]["id"]
    done = _sse(_send(ctx, api, cid2))[-1]
    assert done["type"] == "done" and done["remaining"] == 38
    assert len([r for r in _rows(ctx) if r[0] == "user"]) == 2


def test_bad_key_is_rejected(ctx):
    api, cid = _case(ctx)
    assert _send(ctx, api, cid, key="x y").status_code == 422


def test_tick_is_skipped_while_another_process_holds_the_lock(ctx, monkeypatch):
    from konsilier.core import deadlines

    calls = []
    ctx.container.scheduler.extra_jobs.append(lambda s, now: calls.append(now) or 0)
    monkeypatch.setattr(deadlines, "tick_lock", lambda session: False)
    assert ctx.container.scheduler.tick() == 0 and calls == []
    monkeypatch.setattr(deadlines, "tick_lock", lambda session: True)
    ctx.container.scheduler.tick()
    assert len(calls) == 1


def test_tick_lock_is_a_no_op_on_sqlite(ctx):
    from konsilier.core.deadlines import tick_lock

    with ctx.container.session_factory() as s:
        assert tick_lock(s) is True
