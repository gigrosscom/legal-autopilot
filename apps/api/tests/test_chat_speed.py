"""The first chat answer must start at once (owner 30.09: first words within ~2 s): the case is created without
waiting for the classification, articles come from the local Zann corpus copy, a slow free provider gets the next
one asked in parallel, Gemini 3 is asked to think least, and the time to the first words is measured."""

from __future__ import annotations

import gzip
import json
import time
from types import SimpleNamespace as NS

import httpx
import pytest

from konsilier.chat import ChatAgent
from konsilier.gemini import Block, GeminiClient, Message, Usage
from konsilier.lawagent.sources import ActNotFound, Adilet, page_text
from konsilier.openai_compat import ChainClient

from .test_chat import StreamingClient, _sse
from .test_lawagent import FIX, Q113, TK, fake_fetch


# ------------------------------------------------------------------ case creation does not wait for the model
class CountingLLM:
    """The case engine's model, counting its calls (the classification is two of them, ≈4 s in production)."""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def __getattr__(self, name):
        attr = getattr(self.inner, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            self.calls += 1
            return attr(*a, **k)
        return call


def test_chat_case_is_created_without_the_classification_then_classified(ctx, monkeypatch):
    from konsilier.api import routes

    from .test_e2e import web_user

    counting = CountingLLM(ctx.container.engine.llm_provider)
    monkeypatch.setattr(ctx.container.engine, "llm_provider", counting)
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ",
                                                  "defer": True})
    case = out["case"]
    assert counting.calls == 0 and out["reply"]["message"] == ""  # no model call before the chat can answer
    assert case["scenario"] is None
    # the chat answers a case that is not classified yet
    ctx.container.chat_agent = ChatAgent(StreamingClient([(["Расчёт — в день увольнения."], "end_turn", [])]),
                                         "m", Adilet(fetch=fake_fetch))
    events = _sse(ctx.client.post(f"/v1/cases/{case['id']}/chat", headers=api.h, json={"text": "Когда?"}))
    assert events[-1]["type"] == "done"
    # the background job (BACKGROUND_JOBS=off in tests) never ran: opening the case later runs the classification
    monkeypatch.setattr(routes, "QUALIFY_RETRY_AFTER_S", -1)
    opened = api.get(f"/v1/cases/{case['id']}").json()
    assert counting.calls >= 1 and opened["scenario"]
    calls = counting.calls
    api.get(f"/v1/cases/{case['id']}")  # once only
    assert counting.calls == calls


def test_background_classification_runs_after_the_case_is_saved(ctx):
    from .test_e2e import web_user

    ctx.container.settings.background_jobs = "inline"
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ",
                                                  "defer": True})["case"]["id"]
    assert api.get(f"/v1/cases/{cid}").json()["scenario"]


def test_without_the_flag_the_case_is_classified_at_once(ctx):
    from .test_e2e import web_user

    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})
    assert out["case"]["scenario"] and out["reply"]["message"]


def test_web_chat_opens_the_case_without_waiting():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[3] / "apps/web/components/Chat.tsx").read_text("utf-8")
    assert "defer: true" in src


# ------------------------------------------------------------------ articles from the local Zann corpus
def stored(title_text: tuple[str, str] | None):
    calls = []

    def local(code, lang):
        calls.append((code, lang))
        return title_text
    return local, calls


def test_article_comes_from_the_local_corpus_before_the_portal():
    title, text = page_text((FIX / f"{TK}.txt").read_text("utf-8"))
    local, calls = stored((title, text))

    def no_network(url):
        raise AssertionError("the portal must not be opened when the corpus has the act")

    a = Adilet(fetch=no_network, local=local)
    art = a.article(TK, "113")
    assert Q113 in art.text and art.url == f"https://old.adilet.zan.kz/rus/docs/{TK}" and a.last_source() == "local"
    assert calls == [(TK, "rus")]
    a.article(TK, "113")
    assert a.last_source() == "cache" and len(calls) == 1


def test_act_missing_locally_is_read_live():
    local, calls = stored(None)
    a = Adilet(fetch=fake_fetch, local=local)
    assert Q113 in a.article(TK, "113").text and a.last_source() == "live" and calls

    def broken(code, lang):
        raise OSError("storage down")
    a = Adilet(fetch=fake_fetch, local=broken)
    assert Q113 in a.article(TK, "113").text and a.last_source() == "live"
    with pytest.raises(ActNotFound):
        Adilet(fetch=fake_fetch, local=stored(("t", "no articles here"))[0]).article("K9999999999", "1")


def test_corpus_texts_read_the_collected_file(ctx):
    from konsilier.core.models import ZannFile
    from konsilier.zann.corpus import CorpusTexts, file_key

    title, text = page_text((FIX / f"{TK}.txt").read_text("utf-8"))
    ctx.container.storage.put(file_key(TK, "ru"), gzip.compress(text.encode()), "application/gzip")
    with ctx.container.session_factory() as s:
        s.add(ZannFile(code=TK, lang="ru", key=file_key(TK, "ru"), url="u", title=title, sha256="x"))
        s.commit()
    texts = CorpusTexts(ctx.container.session_factory, ctx.container.storage)
    assert texts(TK, "rus") == (title, text) and texts(TK, "kaz") is None
    # the container wires it into the chat's portal access
    assert ctx.container.settings.law_texts_local is True


def test_chat_records_where_the_time_went():
    title, text = page_text((FIX / f"{TK}.txt").read_text("utf-8"))
    local, _ = stored((title, text))
    from .test_chat import reply_turns

    agent = ChatAgent(StreamingClient(reply_turns("По статье 113 расчёт — не позднее трёх рабочих дней.")), "m",
                      Adilet(fetch=fake_fetch, local=local))
    events = list(agent.stream([{"role": "user", "text": "Уволили"}], context={"pack": NS(add_days=None), "case": {},
                                                                              "forums": []},
                               language="ru", country="X", use_portal=True))
    t = events[-1]["result"].timing
    assert isinstance(t["ttft_ms"], int) and t["system_chars"] > 1000 and t["prompt_chars"] > t["system_chars"]
    assert [r["stop"] for r in t["rounds"]] == ["tool_use", "end_turn"]
    assert t["tools"] == [{"name": "get_article", "ms": t["tools"][0]["ms"], "source": "local"}]


# ------------------------------------------------------------------ the chain: a slow provider gets company
class Slow:
    """A provider whose first word comes after ``delay`` seconds (or that fails)."""

    def __init__(self, name, delay, text="Ответ.", fail=False, tool=False):
        self.name, self.delay, self.text, self.fail, self.tool = name, delay, text, fail, tool
        self.messages, self.calls, self.warmed = self, 0, 0

    def warm(self):
        self.warmed += 1

    def stream(self, **kw):
        self.calls += 1
        me = self

        class S:
            attempts = [{"status": 200, "ms": int(me.delay * 1000)}]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            @property
            def text_stream(self):
                time.sleep(me.delay)
                if me.fail:
                    raise RuntimeError(f"{me.name} 429: busy")
                if not me.tool:
                    yield me.text

            def get_final_message(self):
                blocks = ([Block("tool_use", id="c1", name="deadline", input={})] if me.tool
                          else [Block("text", text=me.text)])
                return Message(blocks, "tool_use" if me.tool else "end_turn", Usage(1, 1))
        return S()


def read(stream):
    with stream as s:
        text = "".join(s.text_stream)
        return text, s.get_final_message(), s


def test_slow_first_provider_gets_the_next_asked_in_parallel():
    slow, fast = Slow("gemini", 0.6, "медленно"), Slow("cerebras", 0.0, "быстро")
    t0 = time.perf_counter()
    text, final, s = read(ChainClient([slow, fast], first_token_timeout=0.05).stream(model="m", messages=[]))
    assert text == "быстро" and s.provider == "cerebras" and time.perf_counter() - t0 < 0.5
    assert [(a["provider"], a["result"]) for a in s.attempts] == [("cerebras", "answered"), ("gemini", "dropped")]
    # a first provider that answers in time is used alone
    quick = Slow("gemini", 0.0, "сразу")
    other = Slow("cerebras", 0.0)
    text, _, s = read(ChainClient([quick, other], first_token_timeout=0.5).stream(model="m", messages=[]))
    assert text == "сразу" and other.calls == 0


def test_failed_provider_is_replaced_at_once_and_tool_rounds_count_as_an_answer():
    broken, tools = Slow("gemini", 0.0, fail=True), Slow("cerebras", 0.0, tool=True)
    text, final, s = read(ChainClient([broken, tools], first_token_timeout=5).stream(model="m", messages=[]))
    assert text == "" and final.stop_reason == "tool_use" and s.provider == "cerebras"
    assert s.attempts[0]["provider"] == "gemini" and s.attempts[0]["result"].startswith("error")
    with pytest.raises(RuntimeError):
        read(ChainClient([Slow("a", 0, fail=True), Slow("b", 0, fail=True)], first_token_timeout=5).stream())


def test_the_provider_that_began_the_turn_keeps_it():
    a, b = Slow("gemini", 0.0, "г"), Slow("cerebras", 0.0, "ц")
    text, _, s = read(ChainClient([a, b]).stream(prefer="cerebras", model="m", messages=[]))
    assert text == "ц" and a.calls == 0
    agent = ChatAgent(ChainClient([a, b]), "m", Adilet(fetch=fake_fetch), web_search=False)
    events = list(agent.stream([{"role": "user", "text": "?"}], context={"pack": NS(add_days=None), "case": {},
                                                                        "forums": []},
                               language="ru", country="X", use_portal=False))
    assert events[-1]["result"].timing["provider"] == "gemini"


def test_warm_up_when_the_chat_page_opens(ctx):
    client = Slow("gemini", 0)
    ctx.container.chat_agent = ChatAgent(ChainClient([client]), "m", Adilet(fetch=fake_fetch))
    ctx.client.get("/v1/chat/info")
    for _ in range(50):
        if client.warmed:
            break
        time.sleep(0.02)
    assert client.warmed == 1


def test_keepalive_and_rate_limited_warm_up():
    seen = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(str(r.url)) or httpx.Response(200)))
    g = GeminiClient("k", http=http)
    g.warm()
    g.warm()
    assert len(seen) == 1 and "/models" in seen[0]
    assert GeminiClient("k").http._transport._pool._keepalive_expiry >= 60


# ------------------------------------------------------------------ Gemini 3 thinks least in the chat
def _ok():
    return httpx.Response(200, text='data: {"candidates":[{"content":{"parts":[{"text":"Да."}]},"finishReason":"STOP"}]}\n\n')


def test_gemini_3_gets_the_minimal_thinking_level_and_old_models_do_not(monkeypatch):
    import konsilier.gemini as gm

    monkeypatch.setattr(gm, "RETRY_DELAY", 0)
    bodies = []

    def handler(req):
        bodies.append((str(req.url), json.loads(req.content)))
        if "gemini-3" in str(req.url) or "latest" in str(req.url):
            return httpx.Response(503, text="busy")
        return _ok()

    # the "-latest" aliases point at Gemini 3 models: they get the level too (P0 01.10)
    g = GeminiClient("k", http=httpx.Client(transport=httpx.MockTransport(handler)),
                     fallback_models=("gemini-flash-lite-latest", "gemini-2.5-flash-lite"), thinking_level="minimal")
    with g.messages.stream(model="gemini-3.1-flash-lite", max_tokens=10, system="s", tools=[],
                           messages=[{"role": "user", "content": "?"}]) as s:
        assert "".join(s.text_stream) == "Да."
    first_url, first = bodies[0]
    assert first["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert [b["generationConfig"]["thinkingConfig"] for u, b in bodies if "latest" in u][0] == {
        "thinkingLevel": "minimal"}
    assert "thinkingConfig" not in bodies[-1][1]["generationConfig"]
    assert [a["status"] for a in s.attempts][-1] == 200 and s.attempts[0]["model"] == "gemini-3.1-flash-lite"


def test_gemini_refusing_the_thinking_level_is_asked_again_without_it():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "thinkingConfig" in body["generationConfig"]:
            return httpx.Response(400, text='{"error": {"message": "Thinking level minimal is not supported"}}')
        return _ok()

    g = GeminiClient("k", http=httpx.Client(transport=httpx.MockTransport(handler)), thinking_level="minimal")
    with g.messages.stream(model="gemini-3.5-flash-lite", max_tokens=10, system="s", tools=[],
                           messages=[{"role": "user", "content": "?"}]) as s:
        assert "".join(s.text_stream) == "Да."
    assert len(bodies) == 2


def test_tool_call_of_another_provider_gets_the_signature_placeholder():
    from konsilier.gemini import _contents

    out = _contents([{"role": "assistant", "content": [Block("tool_use", id="c1", name="deadline", input={})]}])
    assert out[0]["parts"][0]["thoughtSignature"] == "skip_thought_signature_validator"


# ------------------------------------------------------------------ the metric for /ops
def test_time_to_first_words_is_kept_and_reported(ctx):
    from konsilier.core.models import ChatMessage

    from .test_e2e import ADMIN, web_user

    ctx.container.chat_agent = ChatAgent(StreamingClient([(["Ответ."], "end_turn", [])] * 3), "m",
                                         Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ",
                                                  "defer": True})["case"]["id"]
    for q in ("Когда?", "А если нет?"):
        _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": q}))
    with ctx.container.session_factory() as s:
        metas = [m.meta for m in s.query(ChatMessage).filter(ChatMessage.role == "assistant")]
    t = metas[0]["timing"]
    assert {"ttft_ms", "queue_ms", "setup_ms", "total_ms", "rounds", "system_chars"} <= set(t)
    assert metas[0]["served_by"] == "anthropic"  # a client without a name: the metric's provider label
    m = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()["chat_latency"]
    assert m["n"] == 2 and m["p50_ms"] is not None and m["p95_ms"] >= m["p50_ms"]
    assert sum(v["n"] for v in m["by_provider"].values()) == 2
    assert "timing" not in api.get(f"/v1/cases/{cid}/chat").json()[1]  # never shown to the person


def test_percentiles():
    from konsilier.api.chat import _percentile

    assert _percentile([], 0.5) is None
    assert _percentile([100, 300, 200], 0.5) == 200 and _percentile(list(range(1, 101)), 0.95) == 95


def test_first_token_timing_is_logged(caplog):
    agent = ChatAgent(StreamingClient([(["Ответ."], "end_turn", [])]), "m", Adilet(fetch=fake_fetch))
    with caplog.at_level("INFO", logger="konsilier.chat"):
        list(agent.stream([{"role": "user", "text": "?"}], context={"pack": NS(add_days=None), "case": {},
                                                                   "forums": [], "case_id": "c1"},
                          language="ru", country="X", use_portal=False))
    assert "chat timing: case=c1 phase=first_token" in caplog.text and "phase=round" in caplog.text

