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
