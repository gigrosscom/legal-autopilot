"""First words of the chat within ~2 s (owner 30.09) and no empty reply charged to the daily limit (QA BUG-02).

Measured 30.09 with the real keys (apps/api/scripts/chat_timing.py, CHAT_LIVE=1): gemini-3.1-flash-lite answered after
2–8 s (median ≈5 s, some 503), gemini-3.5-flash-lite and gemini-flash-lite-latest after ≈0.5 s; the chain then raced
Cerebras at 1.5 s, which often returned an empty reply. Now the Gemini fallback models are asked in parallel after
GEMINI_HEDGE_AFTER; the first model to answer is read, the other request is closed. Test accounts (production smoke
checks) get the breakdown of each reply in the ``done`` event, so the speed can be measured from outside.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from konsilier.chat import MORE_MARKER, ChatAgent
from konsilier.gemini import GeminiClient, GeminiUnavailable
from konsilier.lawagent.sources import Adilet
from konsilier.openai_compat import ChainClient

from .test_chat import _sse
from .test_chat_race import SHORT, Fake, R, _case
from .test_e2e import Api
from .test_lawagent import fake_fetch


# ------------------------------------------------------------------ Gemini: a slow model is replaced in parallel
class SlowTransport(httpx.BaseTransport):
    """Gemini models with a delay before their answer (Gemini answers when its first words are ready) or a status."""

    def __init__(self, delays: dict[str, float], status: dict[str, int] | None = None):
        self.delays, self.status = delays, status or {}
        self.asked: list[str] = []
        self.closed: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        model = str(request.url).split("/models/", 1)[1].split(":", 1)[0]
        self.asked.append(model)
        time.sleep(self.delays.get(model, 0))
        if model in self.status:
            return httpx.Response(self.status[model], text='{"error": "busy"}')
        body = f'data: {{"candidates":[{{"content":{{"parts":[{{"text":"{model}"}}]}},"finishReason":"STOP"}}]}}\n\n'
        closed = self.closed

        class Body(httpx.SyncByteStream):
            def __iter__(self):
                yield body.encode()

            def close(self):
                closed.append(model)

        return httpx.Response(200, stream=Body())


def gemini(transport, hedge=0.1, fallbacks=("gemini-3.5-flash-lite", "gemini-flash-lite-latest")):
    return GeminiClient("k", http=httpx.Client(transport=transport), fallback_models=fallbacks, hedge_after=hedge)


def read(client, model="gemini-3.1-flash-lite"):
    t0 = time.perf_counter()
    with client.messages.stream(model=model, max_tokens=10, system="s", tools=[],
                                messages=[{"role": "user", "content": "?"}]) as s:
        text = "".join(s.text_stream)
    return text, time.perf_counter() - t0, s


def test_slow_first_model_is_replaced_by_the_fallback_asked_in_parallel():
    t = SlowTransport({"gemini-3.1-flash-lite": 1.0, "gemini-3.5-flash-lite": 0.05})
    text, took, s = read(gemini(t))
    assert text == "gemini-3.5-flash-lite" and took < 0.6
    assert t.asked[:2] == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    time.sleep(1.1)  # the slow model answers late: its answer is closed unread
    assert "gemini-3.1-flash-lite" in t.closed
    assert {a["model"] for a in s.attempts} >= {"gemini-3.1-flash-lite", "gemini-3.5-flash-lite"}


def test_quick_first_model_is_the_only_one_asked():
    t = SlowTransport({"gemini-3.1-flash-lite": 0.01})
    text, _, _ = read(gemini(t, hedge=0.3))
    assert text == "gemini-3.1-flash-lite" and t.asked == ["gemini-3.1-flash-lite"]


def test_first_model_failing_before_the_hedge_asks_the_fallback_at_once(monkeypatch):
    import konsilier.gemini as gm

    monkeypatch.setattr(gm, "RETRY_DELAY", 0)
    t = SlowTransport({}, status={"gemini-3.1-flash-lite": 400})
    text, took, _ = read(gemini(t, hedge=1.0))
    assert text == "gemini-3.5-flash-lite" and took < 0.5


def test_every_model_busy_is_reported_as_overload(monkeypatch):
    import konsilier.gemini as gm

    monkeypatch.setattr(gm, "RETRY_DELAY", 0)
    t = SlowTransport({}, status={"gemini-3.1-flash-lite": 503, "gemini-3.5-flash-lite": 429,
                                  "gemini-flash-lite-latest": 429})
    with pytest.raises(GeminiUnavailable):
        read(gemini(t, hedge=0.05))


def test_without_hedge_the_models_are_tried_one_after_another():
    t = SlowTransport({"gemini-3.1-flash-lite": 0.3})
    text, took, _ = read(gemini(t, hedge=0))
    assert text == "gemini-3.1-flash-lite" and took >= 0.3 and t.asked == ["gemini-3.1-flash-lite"]


def test_the_loser_starts_no_new_try_once_a_model_answered(monkeypatch):
    import konsilier.gemini as gm

    monkeypatch.setattr(gm, "RETRY_DELAY", 0.3)  # the first model waits before its retry
    t = SlowTransport({"gemini-3.5-flash-lite": 0.05}, status={"gemini-3.1-flash-lite": 503})
    text, _, _ = read(gemini(t, hedge=0.01))
    time.sleep(0.5)
    assert text == "gemini-3.5-flash-lite" and t.asked.count("gemini-3.1-flash-lite") == 1


def test_settings_pass_the_hedge_to_the_chat_client():
    from konsilier.config import Settings
    from konsilier.container import free_chat_clients

    s = Settings(chat_free_providers="gemini", gemini_api_key="k", gemini_hedge_after=0.7)
    assert free_chat_clients(s)[0].hedge_after == 0.7
    assert 0 < Settings().gemini_hedge_after < Settings().chat_first_token_timeout


# ------------------------------------------------------------------ test accounts see where the time went
def smoke_user(ctx) -> Api:
    ctx.container.settings.smoke_token = "smoke-secret"
    return Api(ctx, ctx.client.post("/v1/smoke/user", headers={"X-Smoke-Token": "smoke-secret"}).json()["token"])


def _chain(*rounds):
    return ChatAgent(ChainClient([Fake("gemini", *rounds), Fake("cerebras", R([SHORT]))], 0.5), "m",
                     Adilet(fetch=fake_fetch), web_search=False)


def test_done_event_of_a_test_account_carries_the_breakdown(ctx):
    api = smoke_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ",
                                                  "defer": True})["case"]["id"]
    ctx.container.chat_agent = _chain(R([SHORT]))
    done = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда?"}))[-1]
    d = done["diagnostics"]
    assert d["served_by"] == "gemini" and isinstance(d["first_ms"], int) and d["total_ms"] >= d["first_ms"]
    assert {"ttft_ms", "queue_ms", "setup_ms", "rounds", "prompt_chars"} <= set(d["timing"])
    assert d["timing"]["rounds"][0]["provider"] == "gemini"


def test_real_people_never_get_the_breakdown(ctx):
    api, cid = _case(ctx)
    ctx.container.chat_agent = _chain(R([SHORT]))
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда?"}))
    assert ev[-1]["type"] == "done" and "diagnostics" not in ev[-1]
    assert "timing" not in json.dumps(ev) and "served_by" not in json.dumps(ev)


def test_test_account_sees_why_no_model_answered(ctx):
    api = smoke_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ",
                                                  "defer": True})["case"]["id"]
    ctx.container.chat_fallback_agent = None
    ctx.container.chat_agent = ChatAgent(ChainClient([Fake("gemini", R([])), Fake("cerebras", R([]))], 0.05), "m",
                                         Adilet(fetch=fake_fetch), web_search=False)
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда?"}))
    assert ev[-1]["code"] == "busy" and ev[-1]["reason"] == "free_EmptyReply"


# ------------------------------------------------------------------ BUG-02: an empty reply is never charged
@pytest.mark.parametrize("rounds", [[R([])], [R(["  \n"])], [R([MORE_MARKER])], [R(["\n", MORE_MARKER, "\n"])],
                                    [R(["[[DOCUMENT]]"])]])
def test_empty_or_marker_only_reply_goes_to_the_next_provider(ctx, rounds):
    api, cid = _case(ctx)
    ctx.container.chat_agent = ChatAgent(ChainClient([Fake("gemini", *rounds), Fake("cerebras", R([SHORT]))], 0), "m",
                                         Adilet(fetch=fake_fetch), web_search=False)
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда?"}))
    assert ev[-1]["type"] == "done" and ev[-1]["message"]["text"] == SHORT
    assert "".join(e["text"] for e in ev if e["type"] == "text") == SHORT  # nothing of the empty reply was shown


def test_empty_replies_never_use_up_the_daily_limit(ctx):
    api, cid = _case(ctx)
    ctx.container.settings.chat_daily_limit = 2
    ctx.container.chat_fallback_agent = None
    empty = ChatAgent(ChainClient([Fake("gemini", R([MORE_MARKER])), Fake("cerebras", R(["  "]))], 0.05), "m",
                      Adilet(fetch=fake_fetch), web_search=False)
    ctx.container.chat_agent = empty
    for _ in range(4):  # empty and marker-only replies: an error, and the message goes back to the limit
        ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда?"}))
        assert ev[-1]["type"] == "error" and not any(e["type"] == "done" for e in ev)
    ctx.container.chat_agent = _chain(R([SHORT]))
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда?"}))
    assert ev[-1]["type"] == "done" and ev[-1]["remaining"] == 1 and ev[-1]["limit"] == 2
    msgs = api.get(f"/v1/cases/{cid}/chat").json()
    assert [m for m in msgs if m["role"] == "assistant" and not m["text"].strip()] == []
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Ещё?"}))
    assert ev[-1]["remaining"] == 0
    assert ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "И?"}).status_code == 429


def test_hedged_gemini_in_the_chain_answers_before_the_next_provider_is_raced():
    """The production set-up: Gemini first with a slow first model; its fallback model answers before the chain's
    own race timeout, so Cerebras is never asked."""
    t = SlowTransport({"gemini-3.1-flash-lite": 2.0, "gemini-3.5-flash-lite": 0.05})
    cerebras = Fake("cerebras", R([SHORT]))
    chain = ChainClient([gemini(t, hedge=0.1), cerebras], first_token_timeout=0.5)
    agent = ChatAgent(chain, "gemini-3.1-flash-lite", Adilet(fetch=fake_fetch), web_search=False)
    events = list(agent.stream([{"role": "user", "text": "?"}], context={"forums": [], "case": {}}, language="ru",
                               country="X", use_portal=False))
    res = events[-1]["result"]
    assert res.text == "gemini-3.5-flash-lite" and res.timing["provider"] == "gemini" and cerebras.calls == []
    assert res.timing["ttft_ms"] < 500


@pytest.mark.parametrize("text,words", [("", False), (" \n", False), (MORE_MARKER, False), ("[[MO", False),
                                        ("\n[[MORE]]\n[[DOCUMENT]]", False), ("[[MORE]", False), ("Да", True),
                                        ("[[MORE]]\n1. Шаг", True), ("**Напишите**", True)])
def test_has_words(text, words):
    from konsilier.gemini import has_words

    assert has_words(text) is words
