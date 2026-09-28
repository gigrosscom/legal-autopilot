"""Free consultation chat: streamed reply, portal tools, the check of cited articles, limits."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

from konsilier.chat import ChatAgent, mentioned_articles
from konsilier.lawagent.sources import Adilet

from .test_lawagent import Q113, TK, fake_fetch, text, tool_use


class _Stream:
    def __init__(self, chunks, final):
        self.text_stream, self._final = iter(chunks), final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._final


class StreamingClient:
    """Plays back scripted turns: (text chunks, stop_reason, extra content blocks)."""

    def __init__(self, turns):
        self.turns, self.calls = list(turns), []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        chunks, stop, blocks = self.turns.pop(0)
        content = ([text("".join(chunks))] if chunks else []) + list(blocks)
        return _Stream(chunks, NS(stop_reason=stop, content=content, usage=NS(input_tokens=50, output_tokens=10)))


def reply_turns(final_text):
    return [
        (["Сейчас посмотрю закон."], "tool_use", [tool_use("t1", "get_article", {"act": TK, "article": "113"})]),
        ([final_text[:20], final_text[20:]], "end_turn", []),
    ]


def run(final_text, use_portal=True):
    client = StreamingClient(reply_turns(final_text) if use_portal else [([final_text], "end_turn", [])])
    agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch))
    pack = NS(add_days=lambda *a: None)
    events = list(agent.stream([{"role": "user", "text": "Уволили, не рассчитались"}],
                               context={"pack": pack, "forums": [], "case": {}}, language="ru",
                               country="X", use_portal=use_portal))
    return events, client


def test_reply_streams_and_cites_only_read_articles():
    events, client = run("По статье 113 Трудового кодекса расчёт — не позднее трёх рабочих дней.")
    chunks = [e["text"] for e in events if e["type"] == "text"]
    assert len(chunks) >= 3 and {"type": "tool", "name": "get_article"} in events
    res = events[-1]["result"]
    assert res.unchecked is False and res.norms[0]["article"] == "113" and res.norms[0]["url"].endswith(TK)
    assert "Статья 113" in client.calls[1]["messages"][2]["content"][0]["content"] or Q113[:30] in json.dumps(
        client.calls[1]["messages"], ensure_ascii=False, default=str)
    ws = next(t for t in client.calls[0]["tools"] if t.get("name") == "web_search")
    assert ws["type"] == "web_search_20250305" and ws["allowed_domains"] == ["adilet.zan.kz"]


def test_article_not_opened_is_flagged_unchecked():
    events, _ = run("Ещё есть статья 200, по ней положен штраф работодателю.")
    assert events[-1]["result"].unchecked is True


def test_without_portal_no_law_tools():
    events, client = run("Расскажите подробнее, когда вас уволили?", use_portal=False)
    names = {t.get("name") for t in client.calls[0]["tools"]}
    assert names == {"forums", "deadline"} and events[-1]["result"].unchecked is False


def test_article_mentions():
    assert mentioned_articles("ст. 113-1 и статьи 22, 113-бап, article 5") == {"113-1", "22", "113", "5"}


# ------------------------------------------------------------------ API
def _sse(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_chat_endpoint_streams_saves_and_limits(ctx):
    from .test_e2e import web_user

    ctx.container.chat_agent = ChatAgent(StreamingClient(reply_turns(
        "По статье 113 расчёт — не позднее трёх рабочих дней.")), "claude-haiku-4-5", Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    r = ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Когда должны рассчитаться?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _sse(r)
    done = events[-1]
    assert done["type"] == "done" and done["message"]["norms"][0]["article"] == "113"
    hist = api.get(f"/v1/cases/{cid}/chat").json()
    assert [m["role"] for m in hist] == ["user", "assistant"] and "По статье 113" in hist[1]["text"]
    other = web_user(ctx)
    assert ctx.client.post(f"/v1/cases/{cid}/chat", headers=other.h, json={"text": "чужое"}).status_code == 404
    assert ctx.client.get("/v1/chat/info").json() == {"provider": "anthropic", "daily_limit": 40}
    ctx.container.settings.chat_daily_limit = 1
    r = ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "ещё вопрос"})
    assert r.status_code == 429


def test_chat_without_agent_is_503_and_failure_is_reported(ctx):
    from .test_e2e import web_user

    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    ctx.container.chat_agent = None
    assert ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"}).status_code == 503

    class Broken:
        portal_domain = "adilet.zan.kz"

        def stream(self, *a, **k):
            raise RuntimeError("credit balance is too low")
            yield

    ctx.container.chat_agent = Broken()
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"}))
    assert ev[-1]["type"] == "error" and ev[-1]["code"] == "agent_failed"
    assert [m["role"] for m in api.get(f"/v1/cases/{cid}/chat").json()] == ["user"]

# ------------------------------------------------------------------ Gemini adapter (free tier), offline
def _gemini_http(replies, seen):
    import httpx

    def handler(req):
        seen.append(json.loads(req.content))
        body = "".join(f"data: {json.dumps(r, ensure_ascii=False)}\r\n\r\n" for r in replies.pop(0))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_adapter_runs_tools_and_echoes_signature():
    from konsilier.gemini import GeminiClient

    call = {"functionCall": {"name": "get_article", "args": {"act": TK, "article": "113"}}, "thoughtSignature": "sig1"}
    usage = {"promptTokenCount": 40, "candidatesTokenCount": 5}
    replies = [
        [{"candidates": [{"content": {"role": "model", "parts": [call]}, "finishReason": "STOP"}], "usageMetadata": usage}],
        [{"candidates": [{"content": {"role": "model", "parts": [{"text": "По статье 113 расчёт — "}]}}]},
         {"candidates": [{"content": {"role": "model", "parts": [{"text": "не позднее трёх рабочих дней."}]},
                          "finishReason": "STOP"}], "usageMetadata": usage}],
    ]
    seen: list = []
    client = GeminiClient("k", http=_gemini_http(replies, seen))
    agent = ChatAgent(client, "gemini-3.1-flash-lite", Adilet(fetch=fake_fetch), web_search=False)
    events = list(agent.stream([{"role": "user", "text": "Когда рассчитаются?"}],
                               context={"pack": NS(add_days=lambda *a: None), "forums": [], "case": {},
                                        "key_acts": [{"code": TK, "title": "Трудовой кодекс"}]},
                               language="ru", country="X", use_portal=True))
    res = events[-1]["result"]
    assert "".join(e["text"] for e in events if e["type"] == "text").endswith("не позднее трёх рабочих дней.")
    assert res.unchecked is False and res.norms[0]["article"] == "113" and res.usage["input_tokens"] == 80
    first, second = seen
    assert TK in first["systemInstruction"]["parts"][0]["text"]  # the main acts are listed for the model
    decl = {d["name"]: d for d in first["tools"][0]["functionDeclarations"]}
    assert "web_search" not in decl and "additionalProperties" not in json.dumps(decl)
    model_turn, tool_turn = second["contents"][1], second["contents"][2]
    assert model_turn == {"role": "model", "parts": [call]}  # signature sent back unchanged
    fr = tool_turn["parts"][0]["functionResponse"]
    assert fr["name"] == "get_article" and Q113[:40] in fr["response"]["result"]


def test_gemini_error_is_raised_for_the_chat_to_report():
    import httpx
    import pytest

    from konsilier.gemini import GeminiClient

    http = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(400, json={"error": {"message": "User location is not supported"}})))
    agent = ChatAgent(GeminiClient("k", http=http), "m", Adilet(fetch=fake_fetch), web_search=False)
    with pytest.raises(RuntimeError, match="location is not supported"):
        list(agent.stream([{"role": "user", "text": "вопрос"}], context={"case": {}}, language="ru", country="X",
                          use_portal=False))


def test_gemini_retries_high_demand_before_the_reply_starts(monkeypatch):
    import httpx

    from konsilier import gemini

    monkeypatch.setattr(gemini, "RETRY_DELAYS", (0, 0))
    busy = httpx.Response(503, json={"error": {"message": "This model is currently experiencing high demand."}})
    ok = "data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]})
    answers = [busy, busy, httpx.Response(200, text=ok + "\r\n\r\n", headers={"content-type": "text/event-stream"})]
    http = httpx.Client(transport=httpx.MockTransport(lambda req: answers.pop(0)))
    with gemini.GeminiClient("k", http=http).stream(model="m", max_tokens=5, system="s", tools=[],
                                                    messages=[{"role": "user", "content": "?"}]) as st:
        assert [b.text for b in st.get_final_message().content] == ["ok"]
    assert answers == []

    urls: list = []

    def next_model(req):
        urls.append(req.url.path)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    answers[:] = [busy, busy, httpx.RemoteProtocolError("Server disconnected"), httpx.Response(200, text=ok + "\r\n\r\n", headers={"content-type": "text/event-stream"})]
    fb = gemini.GeminiClient("k", http=httpx.Client(transport=httpx.MockTransport(next_model)), fallback_models=("m2",))
    assert fb.stream(model="m1", max_tokens=5, system="s", tools=[],
                     messages=[{"role": "user", "content": "?"}]).get_final_message().content[0].text == "ok"
    assert [u.split("/")[-1] for u in urls] == ["m1:streamGenerateContent"] * 3 + ["m2:streamGenerateContent"]

    answers[:] = [busy, busy, busy]
    import pytest

    with pytest.raises(RuntimeError, match="gemini 503"):
        gemini.GeminiClient("k", http=http).stream(model="m", max_tokens=5, system="s", tools=[],
                                                   messages=[{"role": "user", "content": "?"}]).get_final_message()
