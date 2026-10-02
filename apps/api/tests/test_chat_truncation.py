"""P0 01.10: a chat answer cut mid-word («…если оплата была бе»), and BUG-15 (the saved answer shorter than the
streamed one, «…в течение»). Every way a model round can stop before its end — the token limit, a safety / recitation
/ other stop, a stream without a finish reason, a dropped connection, a tool call after the tools are over — is
continued from where it stopped; a reply still cut ends at its last whole sentence; the stored reply never ends
before what the person was shown. Offline: fake streams and mocked HTTP."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import httpx
import pytest

from konsilier.chat import CUT_NOTE, MAX_CONTINUE, TOOLS_OVER, ChatAgent, whole_sentences
from konsilier.gemini import GeminiClient
from konsilier.lawagent.sources import Adilet
from konsilier.openai_compat import OpenAICompatClient

from .test_lawagent import TK, fake_fetch, text, tool_use


class _Stream:
    def __init__(self, chunks, final, drop: Exception | None = None):
        self._chunks, self._final, self._drop = chunks, final, drop

    @property
    def text_stream(self):
        yield from self._chunks
        if self._drop is not None:
            raise self._drop

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._final


class Client:
    """Scripted rounds: (chunks, stop_reason, finish, extra blocks) or (chunks, Exception) for a dropped stream."""

    def __init__(self, rounds):
        self.rounds, self.calls = list(rounds), []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(json.loads(json.dumps(kw["messages"], default=lambda o: vars(o))))
        r = self.rounds.pop(0)
        if isinstance(r[1], Exception):
            return _Stream(r[0], None, r[1])
        chunks, stop, finish, blocks = r
        content = ([text("".join(chunks))] if chunks else []) + list(blocks)
        return _Stream(chunks, NS(stop_reason=stop, finish=finish, content=content,
                                  usage=NS(input_tokens=5, output_tokens=5)))


def run(rounds, max_turns=6):
    client = Client(rounds)
    agent = ChatAgent(client, "m", Adilet(fetch=fake_fetch), max_turns=max_turns)
    events = list(agent.stream([{"role": "user", "text": "Вернуть деньги за бракованный товар"}],
                               context={"pack": NS(add_days=lambda *a: None), "forums": [], "case": {}},
                               language="ru", country="KZ", use_portal=True))
    streamed = "".join(e["text"] for e in events if e["type"] == "text")
    return events[-1]["result"], streamed, client


ASK = [{"role": "user", "content": "?"}]
ARGS = {"act": TK, "article": "113"}
SHORT = "Вы вправе вернуть деньги за брак. **Напишите продавцу претензию.**\n[[MORE]]\n1. Если оплата была "


@pytest.mark.parametrize("stop,finish", [("max_tokens", "MAX_TOKENS"), ("max_tokens", "length"), ("cut", "SAFETY"),
                                         ("cut", "RECITATION"), ("cut", "OTHER"), ("cut", "NONE")])
def test_a_cut_round_is_continued_where_it_stopped(stop, finish):
    res, streamed, client = run([
        ([SHORT, "бе"], stop, finish, []),
        (["безналичной, верните деньги через банк."], "end_turn", "STOP", []),
    ])
    assert res.text.endswith("Если оплата была безналичной, верните деньги через банк.")
    assert res.text == streamed.strip()  # the repeated word is written once, in the stream and the stored reply
    assert res.truncated.endswith(f":{finish}")
    assert not res.trimmed and res.timing["truncated"] == [res.truncated]
    # the continuation request: the model's own words so far, then «continue exactly where it stopped»
    last = client.calls[1]
    assert last[-2] == {"role": "assistant", "content": [{"type": "text", "text": SHORT + "бе"}]}
    assert last[-1]["content"].startswith(CUT_NOTE) and "«бе»" in last[-1]["content"]


def test_a_dropped_stream_is_continued():
    res, streamed, client = run([
        ([SHORT, "бе"], httpx.RemoteProtocolError("peer closed connection without sending complete message body")),
        (["безналичной, верните деньги через банк."], "end_turn", "STOP", []),
    ])
    assert res.text.endswith("была безналичной, верните деньги через банк.") and res.text == streamed.strip()
    assert "error" in res.truncated and res.timing["rounds"][0]["error"].startswith("RemoteProtocolError")


def test_a_continuation_that_does_not_repeat_the_word_is_kept_as_written():
    res, _, _ = run([([SHORT, "без"], "max_tokens", "length", []),
                     (["наличной — через банк."], "end_turn", "stop", [])])
    assert res.text.endswith("Если оплата была безналичной — через банк.")


def test_still_cut_after_the_continuations_ends_at_the_last_whole_sentence():
    rounds = [([SHORT, "бе"], "max_tokens", "length", [])] + [
        (["безналичной, то"], "max_tokens", "length", []) for _ in range(MAX_CONTINUE)]
    res, streamed, _ = run(rounds)
    assert res.trimmed and len(res.truncated.split(",")) == MAX_CONTINUE + 1
    assert res.text.endswith("**Напишите продавцу претензию.**")  # never «…была бе», never a dangling marker
    assert streamed.startswith(res.text)


def test_a_drop_before_any_word_is_still_reported_as_before():
    with pytest.raises(httpx.ReadError):
        run([([], httpx.ReadError("reset"))])


def test_a_tool_call_after_the_tools_are_over_is_answered_and_the_reply_written():
    call = tool_use("t9", "get_article", {"act": TK, "article": "113"})
    res, streamed, client = run([
        (["Вы вправе вернуть деньги. "], "tool_use", "STOP", [tool_use("t1", "get_article", ARGS)]),
        ([], "tool_use", "STOP", [call]),  # the extra round calls a tool again instead of writing
        (["Напишите продавцу претензию."], "end_turn", "STOP", []),
    ], max_turns=1)
    assert res.text.endswith("Напишите продавцу претензию.") and not res.trimmed
    results = client.calls[2][-1]["content"]
    assert results[0] == {"type": "tool_result", "tool_use_id": "t9", "content": TOOLS_OVER}


def test_saved_equals_streamed_across_tool_rounds_guard_and_labels():
    """BUG-15: what is stored is what the person was finally shown — the look-up note between rounds is the only
    thing taken out (words follow it), labels are stripped, and the end is never shorter."""
    res, streamed, _ = run([
        (["КОРОТКИЙ ОТВЕТ: Уволить без предупреждения нельзя.\n[[MORE]]\n1. Работодатель должен уведомить вас "
          "заранее. ", "Сейчас уточню срок."], "tool_use", "STOP", [tool_use("t1", "get_article",
                                                                             {"act": TK, "article": "113"})]),
        # starts over with the short answer (the repeat guard drops it), then the rest
        (["Уволить без предупреждения нельзя.\n[[MORE]]\n", "2. Срок — не позднее трёх рабочих дней."], "end_turn",
         "STOP", []),
    ])
    assert "Сейчас уточню срок." in streamed and "Сейчас уточню срок." not in res.text
    assert res.text.startswith("Уволить без предупреждения нельзя.")  # the label is gone
    assert res.text.endswith(streamed.rstrip()[-40:])  # the end is exactly what was streamed last
    assert res.text.count("[[MORE]]") == 1


def test_a_look_up_note_at_the_very_end_is_kept_rather_than_leaving_a_stub():
    """BUG-15 «…в течение»: the note was dropped although nothing followed it — the stored reply ended mid-sentence."""
    res, streamed, _ = run([
        (["Работодатель должен уведомить вас в течение. ", "Сейчас уточню срок."], "tool_use", "STOP",
         [tool_use("t1", "get_article", {"act": TK, "article": "113"})]),
        ([" "], "end_turn", "STOP", []),
    ])
    assert res.text == streamed.strip() and res.text.endswith("Сейчас уточню срок.")


def test_whole_sentences():
    assert whole_sentences("Раз. Два **три.** Четы") == "Раз. Два **три.**"
    assert whole_sentences("Коротко.\n[[MORE]]\n1. Если оплата была бе") == "Коротко."
    assert whole_sentences("1. Паспорт\n2. Че") == "1. Паспорт"
    assert whole_sentences("нет конца") == "нет конца"


# ------------------------------------------------------------------ providers: finish reasons and thinking
def _gemini(lines):
    body = "".join(f"data: {json.dumps(x)}\n\n" for x in lines)
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, text=body)

    return GeminiClient("k", http=httpx.Client(transport=httpx.MockTransport(handler)), thinking_level="minimal"), seen


@pytest.mark.parametrize("finish,stop", [("STOP", "end_turn"), ("MAX_TOKENS", "max_tokens"), ("SAFETY", "cut"),
                                         ("RECITATION", "cut"), ("OTHER", "cut"), (None, "cut")])
def test_gemini_finish_reasons(finish, stop):
    cand = {"content": {"parts": [{"text": "Если оплата была бе"}]}}
    if finish:
        cand["finishReason"] = finish
    g, seen = _gemini([{"candidates": [cand]}])
    with g.messages.stream(model="gemini-3.5-flash-lite", max_tokens=4096, system="s", tools=[],
                           messages=[{"role": "user", "content": "?"}]) as s:
        assert "".join(s.text_stream) == "Если оплата была бе"
        final = s.get_final_message()
    assert (final.stop_reason, final.finish) == (stop, finish or "NONE")
    assert seen[0]["generationConfig"] == {"maxOutputTokens": 4096, "thinkingConfig": {"thinkingLevel": "minimal"}}


def _compat(body, seen, reasoning="none", refuse=False):
    def handler(req):
        b = json.loads(req.content)
        seen.append(b)
        if refuse and "reasoning_effort" in b:
            return httpx.Response(400, text='{"message":"reasoning_effort is not supported"}')
        return httpx.Response(200, text=body)

    return OpenAICompatClient("cerebras", "k", http=httpx.Client(transport=httpx.MockTransport(handler)),
                              reasoning_effort=reasoning)


@pytest.mark.parametrize("finish,done,stop", [("stop", True, "end_turn"), ("length", True, "max_tokens"),
                                              ("content_filter", True, "cut"), (None, False, "cut"),
                                              (None, True, "end_turn")])
def test_compat_finish_reasons(finish, done, stop):
    body = (f'data: {json.dumps({"choices": [{"delta": {"content": "Если оплата была бе"}, "finish_reason": finish}]})}'
            "\n\n" + ("data: [DONE]\n\n" if done else ""))
    seen = []
    c = _compat(body, seen)
    with c.messages.stream(model="x", max_tokens=4096, system="s", tools=[], messages=ASK) as s:
        assert "".join(s.text_stream) == "Если оплата была бе"
        assert s.get_final_message().stop_reason == stop
    assert seen[0]["reasoning_effort"] == "none" and seen[0]["max_tokens"] == 4096


def test_compat_provider_refusing_reasoning_effort_is_asked_without_it():
    seen = []
    body = 'data: {"choices":[{"delta":{"content":"Да."},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    c = _compat(body, seen, refuse=True)
    with c.messages.stream(model="x", max_tokens=10, system="s", tools=[], messages=ASK) as s:
        assert "".join(s.text_stream) == "Да."
    assert "reasoning_effort" in seen[0] and "reasoning_effort" not in seen[1]
    assert s.attempts[0]["status"] == "400 reasoning"


def test_compat_continuation_sends_the_cut_text_as_the_assistant_turn():
    from konsilier.openai_compat import _messages

    out = _messages("sys", [{"role": "user", "content": "?"},
                            {"role": "assistant", "content": [{"type": "text", "text": "Если оплата была бе"}]},
                            {"role": "user", "content": CUT_NOTE}])
    assert out[2] == {"role": "assistant", "content": "Если оплата была бе"} and out[3]["content"] == CUT_NOTE


def test_production_settings_leave_room_and_switch_thinking_off():
    from konsilier.config import Settings
    from konsilier.container import free_chat_clients

    s = Settings(chat_free_providers="gemini,cerebras", gemini_api_key="g", cerebras_api_key="c")
    assert s.chat_max_tokens >= 4096 and s.gemini_chat_thinking_level == "minimal"
    clients = free_chat_clients(s)
    assert [c.name for c in clients] == ["gemini", "cerebras"] and clients[1].reasoning_effort == "none"


# ------------------------------------------------------------------ the endpoint records it
def test_truncated_reply_is_recorded_in_the_meta(ctx):
    from konsilier.core.models import ChatMessage

    from .test_e2e import web_user

    ctx.container.chat_agent = ChatAgent(Client([
        ([SHORT, "бе"], "max_tokens", "length", []),
        (["безналичной, верните деньги через банк."], "end_turn", "stop", []),
    ]), "m", Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Вернуть деньги за бракованный товар", "country": "KZ"})
    cid = cid["case"]["id"]
    r = ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Вернуть деньги за бракованный товар"})
    events = [json.loads(x[6:]) for x in r.text.splitlines() if x.startswith("data: ")]
    streamed = "".join(e["text"] for e in events if e["type"] == "text")
    saved = api.get(f"/v1/cases/{cid}/chat").json()[-1]["text"]
    assert saved == events[-1]["message"]["text"] and saved.endswith("была безналичной, верните деньги через банк.")
    assert streamed.strip().endswith(saved[-40:])
    with ctx.container.session_factory() as s:
        meta = s.query(ChatMessage).filter(ChatMessage.role == "assistant").all()[-1].meta
    assert meta["truncated"].endswith(":length") and meta["trimmed"] is False
