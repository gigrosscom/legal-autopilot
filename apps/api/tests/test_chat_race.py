"""The free chat's providers race (CHAT_FIRST_TOKEN_TIMEOUT) without doubling or losing the answer.

In production (30.09, cerebras,gemini,groq with a 1.5 s timeout) one reply streamed two full answers one after the
other (the short answer, [[MORE]], «Сейчас уточняю официальные источники…», then the whole answer again) and half of
the replies ended without a word. Causes: the round after a tool call was raced again, so another model wrote the
whole answer anew after the text already shown (and the same model often starts over too); a reply without text
and without a tool call (or with blank text only) won the race and was saved as an empty answer. Here the providers
are scripted fakes: delays, tool calls, failures, empty and blank replies.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from types import SimpleNamespace as NS

import httpx
import pytest

from konsilier.chat import CONTINUE_NOTE, FINAL_NOTE, MORE_MARKER, ChatAgent, RepeatGuard, trailing_filler
from konsilier.gemini import Block, EmptyReply, Message, Usage
from konsilier.lawagent.sources import Adilet
from konsilier.openai_compat import ChainClient, OpenAICompatClient

from .test_chat import _sse
from .test_lawagent import TK, fake_fetch

SHORT = "Работодатель должен рассчитаться с вами в день увольнения. **Напишите ему письменное требование.**"
FILLER = "Сейчас уточняю официальные источники…"
DETAILS = "1. Подайте требование работодателю под подпись.\n2. Если не заплатят — обратитесь в инспекцию труда."
ARTICLE = ("get_article", {"act": TK, "article": "113"})


@dataclass
class R:
    """One scripted model round: words after ``delay`` s (``gap`` s between them), then tool calls; or a failure."""
    chunks: list[str] = field(default_factory=list)
    tools: list[tuple[str, dict]] = field(default_factory=list)
    delay: float = 0.0
    gap: float = 0.0
    fail: bool = False


class Fake:
    """A provider of the chain playing its rounds in order (the last one repeats)."""

    def __init__(self, name, *rounds: R):
        self.name, self.rounds, self.calls, self.closed = name, list(rounds), [], 0
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        r = self.rounds.pop(0) if len(self.rounds) > 1 else self.rounds[0]
        return _FakeStream(self, r)


class _FakeStream:
    def __init__(self, owner: Fake, r: R):
        self.owner, self.r, self._closed = owner, r, False
        self.attempts = [{"status": 200, "ms": int(r.delay * 1000)}]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        self._closed = True
        self.owner.closed += 1

    def _sleep(self, s):
        end = time.perf_counter() + s
        while time.perf_counter() < end and not self._closed:
            time.sleep(0.005)

    @property
    def text_stream(self):
        self._sleep(self.r.delay)
        if self._closed:
            return
        if self.r.fail:
            raise RuntimeError(f"{self.owner.name} 429: busy")
        for c in self.r.chunks:
            if self._closed:
                return
            yield c
            self._sleep(self.r.gap)

    def get_final_message(self):
        blocks = ([Block("text", text="".join(self.r.chunks))] if self.r.chunks else []) + [
            Block("tool_use", id=f"c{i}", name=n, input=inp) for i, (n, inp) in enumerate(self.r.tools)]
        return Message(blocks, "tool_use" if self.r.tools else "end_turn", Usage(1, 1))


def ask(client):
    agent = ChatAgent(client, "m", Adilet(fetch=fake_fetch), web_search=False)
    events = list(agent.stream([{"role": "user", "text": "Уволили, не рассчитались"}],
                               context={"pack": NS(add_days=lambda *a: None), "forums": [], "case": {}},
                               language="ru", country="X", use_portal=True))
    return "".join(e["text"] for e in events if e["type"] == "text"), events[-1]["result"]


def once(text, part):
    return text.count(part) == 1


# ------------------------------------------------------------------ duplicated answers
def test_round_after_a_tool_call_is_not_raced_so_another_model_cannot_answer_again():
    """The production doubling: cerebras answered first and called a tool; its continuation was slower than the
    timeout, gemini was asked in parallel and wrote the whole answer again after the text already shown."""
    cerebras = Fake("cerebras", R([SHORT, f"\n{MORE_MARKER}\n", FILLER], [ARTICLE]),
                    R([DETAILS], delay=0.15))
    gemini = Fake("gemini", R([SHORT, f"\n{MORE_MARKER}\n", DETAILS]))
    streamed, res = ask(ChainClient([cerebras, gemini], first_token_timeout=0.05))
    assert gemini.calls == []  # round 1 came in time; round 2 is cerebras' own, however slow
    assert once(streamed, SHORT) and once(streamed, MORE_MARKER) and DETAILS in streamed
    assert once(res.text, SHORT) and once(res.text, MORE_MARKER) and FILLER not in res.text
    assert res.text == f"{SHORT}\n{MORE_MARKER}\n\n{DETAILS}"
    assert [r["provider"] for r in res.timing["rounds"]] == ["cerebras", "cerebras"]


def test_continuation_is_asked_to_go_on_and_a_restart_is_cut():
    """The same model starting over after the tool call: its repeated short answer and second marker are dropped
    from the stream, and it was told not to repeat."""
    model = Fake("cerebras", R([SHORT, f"\n{MORE_MARKER}\n", FILLER], [ARTICLE]),
                 R([SHORT[:30], SHORT[30:], f"\n{MORE_MARKER}\n", DETAILS]))
    streamed, res = ask(ChainClient([model]))
    assert once(streamed, SHORT) and once(streamed, MORE_MARKER)
    assert res.text == f"{SHORT}\n{MORE_MARKER}\n\n{DETAILS}"
    results = model.calls[1]["messages"][2]["content"]  # user, assistant (text + tool call), tool results
    assert results[0]["type"] == "tool_result" and {"type": "text", "text": CONTINUE_NOTE} in results


def test_restart_without_the_first_marker_keeps_one_marker():
    model = Fake("gemini", R([SHORT, " ", FILLER], [ARTICLE]),
                 R([SHORT, f"\n{MORE_MARKER}\n", DETAILS]))
    streamed, res = ask(model)
    assert once(streamed, SHORT) and once(res.text, SHORT) and once(res.text, MORE_MARKER)
    assert res.text.startswith(SHORT) and res.text.endswith(DETAILS) and FILLER not in res.text


def test_restart_without_any_marker_drops_the_repeated_paragraph():
    model = Fake("gemini", R([SHORT], [ARTICLE]), R([SHORT, "\n\n", DETAILS]))
    streamed, res = ask(model)
    assert once(streamed, SHORT) and res.text == f"{SHORT}\n\n{DETAILS}"


def test_a_true_continuation_passes_unchanged():
    model = Fake("gemini", R([SHORT, f"\n{MORE_MARKER}\n"], [ARTICLE]), R(["Подробнее: ", DETAILS], gap=0.001))
    streamed, res = ask(model)
    assert res.text == f"{SHORT}\n{MORE_MARKER}\nПодробнее: {DETAILS}"
    assert streamed.endswith(f"Подробнее: {DETAILS}")


def test_tool_first_then_the_whole_answer_is_not_held_or_cut():
    """No text before the tool call: the next round writes the whole answer, streamed as it comes."""
    model = Fake("cerebras", R([], [ARTICLE]), R([SHORT, f"\n{MORE_MARKER}\n", DETAILS]))
    streamed, res = ask(model)
    assert streamed == f"{SHORT}\n{MORE_MARKER}\n{DETAILS}" and res.text == streamed
    assert {"type": "text", "text": CONTINUE_NOTE} not in model.calls[1]["messages"][2]["content"]


# ------------------------------------------------------------------ look-up notes before a tool call
def test_look_up_note_is_not_left_in_the_stored_reply():
    model = Fake("gemini", R(["Сейчас посмотрю закон."], [ARTICLE]), R([SHORT]))
    streamed, res = ask(model)
    assert res.text == SHORT
    assert streamed.startswith("Сейчас посмотрю закон.\n\n")  # shown while the tool runs, never glued to the answer


@pytest.mark.parametrize("text,note", [
    (f"{SHORT} Сейчас уточню срок по закону.", "Сейчас уточню срок по закону."),
    (f"{SHORT}\n{MORE_MARKER}\n{FILLER}", FILLER),
    ("Let me check the official sources.", "Let me check the official sources."),
    ("Ресми kaynaklara bakayım…", "Ресми kaynaklara bakayım…"),
    (f"{SHORT}", ""),
    ("Проверьте договор.", ""),  # advice to the person, not a look-up note
    ("Сейчас вы вправе требовать расчёт.", ""),
])
def test_trailing_filler(text, note):
    assert trailing_filler(text) == note


# ------------------------------------------------------------------ empty answers
def test_empty_reply_never_wins_the_race():
    empty = Fake("cerebras", R([]))  # finished at once: no word, no tool call
    gemini = Fake("gemini", R([SHORT], delay=0.1))
    streamed, res = ask(ChainClient([empty, gemini], first_token_timeout=0.5))
    assert streamed == SHORT and res.text == SHORT and res.timing["provider"] == "gemini"


def test_blank_first_pieces_do_not_win_the_race():
    blank = Fake("cerebras", R(["", " ", "\n"]))
    gemini = Fake("gemini", R([SHORT], delay=0.1))
    streamed, res = ask(ChainClient([blank, gemini], first_token_timeout=0.05))
    assert res.text == SHORT and res.timing["provider"] == "gemini"


def test_empty_first_piece_then_words_is_an_answer():
    model = Fake("cerebras", R(["", SHORT]))
    streamed, res = ask(ChainClient([model, Fake("gemini", R(["нет"]))], first_token_timeout=0.05))
    assert streamed == SHORT and res.timing["provider"] == "cerebras"


def test_empty_reply_goes_to_the_next_provider_without_the_race():
    empty, gemini = Fake("cerebras", R([])), Fake("gemini", R([SHORT]))
    streamed, res = ask(ChainClient([empty, gemini]))
    assert res.text == SHORT and len(empty.calls) == 1


def test_all_providers_empty_is_an_error_not_an_empty_reply():
    with pytest.raises(EmptyReply):
        ask(ChainClient([Fake("cerebras", R([])), Fake("gemini", R(["  "]))], first_token_timeout=0.05))
    with pytest.raises(EmptyReply):
        ask(Fake("gemini", R([])))


def test_model_that_only_calls_tools_is_asked_to_write_the_answer():
    model = Fake("cerebras", *([R([], [ARTICLE])] * 6), R([SHORT]))
    agent = ChatAgent(ChainClient([model]), "m", Adilet(fetch=fake_fetch), web_search=False)
    events = list(agent.stream([{"role": "user", "text": "?"}], context={"pack": NS(add_days=None), "forums": [],
                                                                        "case": {}},
                               language="ru", country="X", use_portal=True))
    assert events[-1]["result"].text == SHORT and len(model.calls) == 7
    assert {"type": "text", "text": FINAL_NOTE} in model.calls[-1]["messages"][-1]["content"]
    # still no words after that: an error for the caller, never an empty answer
    with pytest.raises(EmptyReply):
        ask(ChainClient([Fake("cerebras", R([], [ARTICLE]))]))


# ------------------------------------------------------------------ the loser is cancelled
def test_loser_is_cancelled_and_its_words_never_arrive():
    slow = Fake("cerebras", R(["медленно ", "и ещё"], delay=0.3))
    fast = Fake("gemini", R(["быстро"]))
    with ChainClient([slow, fast], first_token_timeout=0.05).stream(model="m", messages=[]) as s:
        text = "".join(s.text_stream)
    assert text == "быстро" and s.provider == "gemini" and slow.closed == 1
    time.sleep(0.35)  # the slow one would have spoken by now
    assert text == "быстро"


def test_winner_failing_mid_answer_is_raised_not_replaced():
    class Breaks(Fake):
        def stream(self, **kw):
            st = super().stream(**kw)
            orig = type(st).text_stream.fget

            class S(type(st)):
                @property
                def text_stream(self):
                    yield from orig(self)
                    raise RuntimeError("connection dropped")
            st.__class__ = S
            return st
    other = Fake("gemini", R(["другой ответ"], delay=0.2))
    with pytest.raises(RuntimeError, match="dropped"):
        with ChainClient([Breaks("cerebras", R([SHORT])), other], first_token_timeout=0.05).stream() as s:
            assert "".join(s.text_stream) == SHORT  # only the winner's words, then its error


# ------------------------------------------------------------------ the three production set-ups
SETUPS = {
    "cerebras first, race": (["cerebras", "gemini", "groq"], 0.05),
    "gemini first, race": (["gemini", "cerebras", "groq"], 0.05),
    "cerebras first, no race": (["cerebras", "gemini", "groq"], 0),
}


def providers():
    return {
        # fast; writes a look-up note before its tool call and starts over after it
        "cerebras": Fake("cerebras", R([SHORT, f"\n{MORE_MARKER}\n", FILLER], [ARTICLE], delay=0.02),
                         R([SHORT, f"\n{MORE_MARKER}\n", DETAILS], delay=0.1)),
        # slower, sometimes silent too long; continues properly
        "gemini": Fake("gemini", R([SHORT, f"\n{MORE_MARKER}\n"], [ARTICLE], delay=0.08, gap=0.01),
                       R([DETAILS], delay=0.1)),
        "groq": Fake("groq", R(fail=True)),
    }


@pytest.mark.parametrize("setup", SETUPS)
def test_one_answer_whatever_the_order_and_timeout(setup):
    order, timeout = SETUPS[setup]
    p = providers()
    streamed, res = ask(ChainClient([p[n] for n in order], first_token_timeout=timeout))
    assert once(streamed, SHORT) and once(streamed, MORE_MARKER) and DETAILS in streamed
    assert res.text == f"{SHORT}\n{MORE_MARKER}\n\n{DETAILS}"
    rounds = [r["provider"] for r in res.timing["rounds"]]
    assert len(rounds) == 2 and len(set(rounds)) == 1  # the provider that began the reply finishes it
    if timeout == 0:
        assert rounds[0] == order[0]


# ------------------------------------------------------------------ the endpoint
def _case(ctx):
    from .test_e2e import web_user

    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ",
                                                  "defer": True})["case"]["id"]
    return api, cid


def test_endpoint_sends_one_answer(ctx):
    api, cid = _case(ctx)
    p = providers()
    ctx.container.chat_agent = ChatAgent(ChainClient([p["cerebras"], p["gemini"]], 0.05), "m",
                                         Adilet(fetch=fake_fetch), web_search=False)
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда рассчитаются?"}))
    streamed = "".join(e["text"] for e in ev if e["type"] == "text")
    assert once(streamed, SHORT) and ev[-1]["type"] == "done"
    assert ev[-1]["message"]["text"] == f"{SHORT}\n{MORE_MARKER}\n\n{DETAILS}"


@pytest.mark.parametrize("rounds", [[R([])], [R(["   "])], [R(fail=True)], [R([], [ARTICLE])]])
def test_endpoint_never_ends_with_an_empty_reply(ctx, rounds):
    api, cid = _case(ctx)
    ctx.container.chat_fallback_agent = None
    ctx.container.chat_agent = ChatAgent(ChainClient([Fake("cerebras", *rounds), Fake("gemini", *rounds)], 0.05),
                                         "m", Adilet(fetch=fake_fetch), web_search=False)
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда рассчитаются?"}))
    assert ev[-1] == {"type": "error", "code": "busy", "message": "Сейчас большая нагрузка, повторите через минуту."}
    assert not any(e["type"] == "done" for e in ev)
    msgs = api.get(f"/v1/cases/{cid}/chat").json()
    assert [m["role"] for m in msgs] == ["user"]  # nothing empty stored; the message goes back to the limit


# ------------------------------------------------------------------ OpenAI-compatible stream parsing
def _compat(lines):
    body = "".join(f"data: {json.dumps(x)}\n\n" for x in lines) + "data: [DONE]\n\n"
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=body)))
    return OpenAICompatClient("cerebras", "k", http=http)


def test_tool_call_pieces_without_index_make_one_call():
    client = _compat([
        {"choices": [{"delta": {"role": "assistant", "content": None}}]},
        {"choices": [{"delta": {"tool_calls": [{"id": "x1", "function": {"name": "get_article", "arguments": ""}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"function": {"arguments": '{"act": "K1", '}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"function": {"arguments": '"article": "113"}'}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ])
    with client.stream(model="m", max_tokens=10, system="s", tools=[], messages=[]) as s:
        assert "".join(s.text_stream) == ""
        final = s.get_final_message()
    assert final.stop_reason == "tool_use" and len(final.content) == 1
    assert final.content[0].name == "get_article" and final.content[0].input == {"act": "K1", "article": "113"}


def test_empty_compat_reply_is_passed_on_in_the_chain():
    empty = _compat([{"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]}])
    streamed, res = ask(ChainClient([empty, Fake("gemini", R([SHORT]))], first_token_timeout=0.5))
    assert res.text == SHORT and res.timing["provider"] == "gemini"


def test_repeat_guard_holds_only_until_it_can_tell():
    g = RepeatGuard(f"{SHORT}\n{MORE_MARKER}\n\n")
    assert g.feed("1. Подайте") == ""  # held: could be the start of a repeat
    assert g.feed(" требование." + " слово" * 120) != ""  # long enough without a marker: passes
    assert g.feed(" дальше") == " дальше"
