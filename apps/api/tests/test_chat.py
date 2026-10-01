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


def test_prompt_allows_article_numbers_only_when_opened():
    _, client = run("По статье 113 расчёт — не позднее трёх рабочих дней.")
    system = client.calls[0]["system"]
    assert "State an article number only if you opened that article's text" in system
    assert "without any article number" in system
    _, client = run("Смотрите Трудовой кодекс.", use_portal=False)
    assert "never state article numbers" in client.calls[0]["system"]


def test_unchecked_is_logged_not_shown(ctx, caplog):
    from .test_e2e import web_user

    ctx.container.chat_agent = ChatAgent(StreamingClient(reply_turns(
        "Ещё есть статья 200, по ней положен штраф работодателю.")), "claude-haiku-4-5", Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    with caplog.at_level("WARNING", logger="konsilier.api.chat"):
        done = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Какой штраф?"}))[-1]
    assert done["type"] == "done" and "unchecked" not in done["message"]
    assert all("unchecked" not in m for m in api.get(f"/v1/cases/{cid}/chat").json())
    assert "chat=unchecked_norms case=" in caplog.text
    from konsilier.core.models import ChatMessage
    with ctx.container.session_factory() as s:
        metas = [m.meta for m in s.query(ChatMessage).filter(ChatMessage.role == "assistant").all()]
    assert any(m.get("unchecked") is True for m in metas)


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
    assert (done["limit"], done["remaining"], done["window_hours"]) == (40, 39, 24)  # «Осталось N из 40»
    hist = api.get(f"/v1/cases/{cid}/chat").json()
    assert [m["role"] for m in hist] == ["user", "assistant"] and "По статье 113" in hist[1]["text"]
    other = web_user(ctx)
    assert ctx.client.post(f"/v1/cases/{cid}/chat", headers=other.h, json={"text": "чужое"}).status_code == 404
    assert ctx.client.get("/v1/chat/info").json() == {"available": True, "daily_limit": 40}
    ctx.container.settings.chat_daily_limit = 1
    r = ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "ещё вопрос"})
    assert r.status_code == 429
    assert r.json()["detail"] == {"code": "too_many_messages", "message": "too_many_messages", "limit": 1,
                                  "remaining": 0, "window_hours": 24}


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
    assert ev[-1]["type"] == "error" and ev[-1]["code"] == "busy" and "нагрузка" in ev[-1]["message"]
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


def _ok_sse():
    import httpx

    ok = "data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]})
    return httpx.Response(200, text=ok + "\r\n\r\n", headers={"content-type": "text/event-stream"})


def _ask(client, model="m1"):
    return client.stream(model=model, max_tokens=5, system="s", tools=[],
                         messages=[{"role": "user", "content": "?"}]).get_final_message()


def test_gemini_retries_once_then_takes_the_next_model(monkeypatch):
    import httpx
    import pytest

    from konsilier import gemini

    slept: list = []
    monkeypatch.setattr(gemini.time, "sleep", slept.append)
    busy = httpx.Response(503, json={"error": {"message": "This model is currently experiencing high demand."}})
    answers = [busy, _ok_sse()]
    http = httpx.Client(transport=httpx.MockTransport(lambda req: answers.pop(0)))
    assert _ask(gemini.GeminiClient("k", http=http)).content[0].text == "ok"
    assert answers == [] and slept == [gemini.RETRY_DELAY]

    urls: list = []

    def next_model(req):
        urls.append(req.url.path)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    slept.clear()
    answers[:] = [busy, busy, _ok_sse()]
    fb = gemini.GeminiClient("k", http=httpx.Client(transport=httpx.MockTransport(next_model)), fallback_models=("m2",))
    assert _ask(fb).content[0].text == "ok"
    assert [u.split("/")[-1] for u in urls] == ["m1:streamGenerateContent"] * 2 + ["m2:streamGenerateContent"]

    answers[:] = [busy, busy]
    with pytest.raises(gemini.GeminiUnavailable, match="gemini 503") as err:
        _ask(gemini.GeminiClient("k", http=http))
    assert err.value.status_code == 503


def test_gemini_429_honours_short_retry_after_and_skips_long_waits(monkeypatch):
    import httpx

    from konsilier import gemini

    slept: list = []
    monkeypatch.setattr(gemini.time, "sleep", slept.append)
    urls: list = []
    quota_short = httpx.Response(429, headers={"retry-after": "2"}, json={"error": {"message": "quota"}})
    quota_long = httpx.Response(429, json={"error": {"message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}]}})
    answers = [quota_short, quota_long, quota_long, _ok_sse()]

    def handler(req):
        urls.append(req.url.path.split("/")[-1].split(":")[0])
        return answers.pop(0)

    client = gemini.GeminiClient("k", http=httpx.Client(transport=httpx.MockTransport(handler)),
                                 fallback_models=("m2", "m3"))
    assert _ask(client).content[0].text == "ok"
    # m1: waits the 2 s it was told, retries, gets "37s" → m2 at once (no long wait) → m3 answers
    assert urls == ["m1", "m1", "m2", "m3"] and slept == [2.0]
    assert gemini.retry_after(quota_long) == 37.0


# ------------------------------------------------------------------ resilience: budget, limit, metrics
class Busy:
    """Gemini-like agent that is over quota."""

    portal_domain = "adilet.zan.kz"
    client = type("GeminiClient", (), {})()

    def stream(self, *a, **k):
        from konsilier.gemini import GeminiUnavailable

        raise GeminiUnavailable(429, "quota")
        yield


def _claude(reply="Расчёт — в день увольнения.", input_tokens=50, output_tokens=10):
    client = StreamingClient([([reply], "end_turn", [])] * 5)
    client.stream = lambda **kw: _Stream([reply], NS(stop_reason="end_turn", content=[text(reply)], usage=NS(
        input_tokens=input_tokens, output_tokens=output_tokens, server_tool_use=NS(web_search_requests=1))))
    return ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch))


def test_unavailable_chat_says_busy_and_keeps_the_daily_limit(ctx, caplog):
    import logging

    from .test_e2e import web_user

    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = Busy(), None
    ctx.container.settings.chat_daily_limit = 1
    with caplog.at_level(logging.WARNING, logger="konsilier.api.chat"):
        for _ in range(3):  # failed attempts do not use up the one free message
            ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"}))
            assert ev[-1] == {"type": "error", "code": "busy", "message": "Сейчас большая нагрузка, повторите через минуту."}
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("chat=unavailable")]
    assert len(lines) == 3 and "reason=gemini_429" in lines[0]

    ctx.container.chat_fallback_agent = _claude()
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"}))
    assert ev[-1]["type"] == "done"
    r = ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "ещё"})
    assert r.status_code == 429  # the answered message counts


def test_claude_fallback_stops_at_the_daily_budget(ctx, caplog):
    import logging

    from konsilier.api.chat import reply_cost_usd

    from .test_e2e import ADMIN, web_user

    s = ctx.container.settings
    assert reply_cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000, "web_search_requests": 2}, s) \
        == 1.0 + 5.0 + 0.02
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    ctx.container.chat_agent = Busy()
    # each Claude reply: 1M in + 0.2M out + 1 search = $1 + $1 + $0.01
    ctx.container.chat_fallback_agent = _claude(input_tokens=1_000_000, output_tokens=200_000)
    s.chat_fallback_daily_budget_usd = 3.0
    for _ in range(2):
        ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"}))
        assert ev[-1]["type"] == "done"
    with caplog.at_level(logging.WARNING, logger="konsilier.api.chat"):
        ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"}))
    assert ev[-1]["code"] == "busy"
    assert any("reason=gemini_429+anthropic_budget" in r.getMessage() for r in caplog.records)

    chat = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()["chat"]
    assert chat["anthropic"] == 2 and chat["gemini"] == 0 and chat["unavailable"] == 1
    assert chat["anthropic_cost_usd"] == 4.02 and chat["fallback_open"] is False

    s.chat_fallback_daily_budget_usd = 0  # 0 → Claude is never used as the fallback
    assert ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()["chat"]["fallback_open"] is False


def test_gemini_reply_is_counted_by_provider(ctx):
    import httpx

    from konsilier.gemini import GeminiClient

    from .test_e2e import ADMIN, web_user

    http = httpx.Client(transport=httpx.MockTransport(lambda req: _ok_sse()))
    ctx.container.chat_agent = ChatAgent(GeminiClient("k", http=http), "m", Adilet(fetch=fake_fetch), web_search=False)
    ctx.container.chat_fallback_agent = None
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    ev = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "вопрос"}))
    assert ev[-1]["type"] == "done"
    chat = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()["chat"]
    assert chat["gemini"] >= 1 and chat["anthropic_budget_usd"] == 10.0


def test_a_stray_chinese_word_never_reaches_the_person():
    from konsilier.chat import strip_foreign_script

    assert strip_foreign_script("если 母亲 работала", "русском") == "если работала"
    assert strip_foreign_script("обычный текст", "русском") == "обычный текст"


def test_document_is_offered_only_when_the_reply_says_so():
    events, _ = run("Вам нужна письменная претензия продавцу. Консильéр может её подготовить.\n[[DOCUMENT]]",
                    use_portal=False)
    res = events[-1]["result"]
    assert res.offer_document is True and "[[" not in res.text and res.text.endswith("подготовить.")
    events, client = run("Срок гарантии зависит от договора.", use_portal=False)
    assert events[-1]["result"].offer_document is False
    assert "[[DOCUMENT]]" in client.calls[0]["system"]  # the model is told how to offer one


def test_reply_follows_interface_language_not_pack_fallback(ctx):
    """The KZ pack has only ru and kk: an English page used to get Russian answers. The reply follows the interface."""
    from .test_e2e import web_user

    client = StreamingClient([(["Hello."], "end_turn", [])])
    ctx.container.chat_agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Меня уволили и не рассчитались", "country": "KZ"})["case"]["id"]
    _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Refund?", "language": "en"}))
    assert "ISO 639-1 code 'en'" in client.calls[0]["system"]
    client.turns = [(["Сәлем."], "end_turn", [])]
    _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "?", "language": "de"}))
    assert "ISO 639-1 code 'ru'" in client.calls[-1]["system"]  # an unsupported one falls back to the case's


def test_chat_opens_the_case_at_once_and_qualifies_it_afterwards(ctx):
    """The chat's first message must not wait for the scenario (an LLM call): the case opens with `defer`, the
    scenario is worked out afterwards (background job; called directly here)."""
    import uuid

    from konsilier.core.models import Case

    from .test_e2e import web_user

    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине, сломался, продавец не возвращает деньги", "country": "KZ", "defer": True})
    cid = out["case"]["id"]
    assert out["case"]["scenario"] is None and out["reply"]["message"] == ""
    with ctx.container.session_factory() as s:
        ctx.container.engine.qualify_later(s, uuid.UUID(cid))
        s.commit()
        assert s.get(Case, uuid.UUID(cid)).scenario_id == "kz.consumer.refund"
    assert api.get(f"/v1/cases/{cid}").json()["scenario"]["id"] == "kz.consumer.refund"


def test_document_is_not_offered_in_the_first_reply(ctx):
    """Owner 30.09: the «Составить документ» button in the very first reply scares people off; later it may come,
    and at once when the person asks for a document themselves."""
    from .test_e2e import web_user

    offer = "Могу подготовить претензию продавцу — показать?\n[[DOCUMENT]]"
    client = StreamingClient([([offer], "end_turn", []), ([offer], "end_turn", [])])
    ctx.container.chat_agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Сломался телефон", "country": "KZ", "defer": True})["case"]["id"]
    first = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Сломался телефон"}))[-1]
    assert first["message"]["offer_document"] is False
    second = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h, json={"text": "Чек есть, 200 000 тенге"}))[-1]
    assert second["message"]["offer_document"] is True

    client.turns = [([offer], "end_turn", [])]
    cid2 = api.post("/v1/cases", expect=201, json={"text": "Нужна претензия", "country": "KZ", "defer": True})["case"]["id"]
    asked = _sse(ctx.client.post(f"/v1/cases/{cid2}/chat", headers=api.h, json={"text": "Составьте претензию продавцу"}))[-1]
    assert asked["message"]["offer_document"] is True


def test_only_the_first_more_marker_is_kept():
    # QA BUG-05: a reply written in two rounds (around a tool call) had a second [[MORE]] that the client showed
    from konsilier.api.chat import one_more_marker
    assert one_more_marker("Коротко.[[MORE]]Детали. Проверяю…[[MORE]]Ещё.") == "Коротко.\n[[MORE]]\nДетали. Проверяю…\n\nЕщё."
    assert one_more_marker("A [[MORE]] B") == "A [[MORE]] B"
    assert one_more_marker("без метки") == "без метки"


def test_facts_told_in_the_chat_go_into_the_case(ctx):
    """QA BUG-03: the chat moves the case — the interview does not ask again what was already told in the chat."""
    from .test_e2e import web_user

    ctx.container.settings.background_jobs = "inline"
    client = StreamingClient([(["Понял. Сохраните чек.[[MORE]]Подробности."], "end_turn", [])])
    ctx.container.chat_agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={
        "text": "Купил смартфон в интернет-магазине, через неделю он сломался, продавец отказывается вернуть деньги",
        "country": "KZ"})["case"]["id"]
    facts = {f["field"] for f in api.get(f"/v1/cases/{cid}").json()["facts"]}
    assert "purchase_date" not in facts and "amount" not in facts
    _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h,
                         json={"text": "Купил 12.08.2026 за 150 000 тенге, чек сохранился"}))
    facts = {f["field"]: f["value"] for f in api.get(f"/v1/cases/{cid}").json()["facts"]}
    assert facts.get("purchase_date") == "12.08.2026" and facts.get("amount", "").replace("\xa0", " ") == "150 000"
