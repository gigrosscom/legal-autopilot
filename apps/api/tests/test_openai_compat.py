"""OpenAI-compatible providers (Groq, Cerebras, NVIDIA …) and the chain of free chat providers, offline."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import httpx
import pytest

from konsilier import gemini
from konsilier.chat import ChatAgent
from konsilier.config import Settings
from konsilier.container import free_chat_clients
from konsilier.lawagent.sources import Adilet
from konsilier.openai_compat import ChainClient, OpenAICompatClient

from .test_lawagent import Q113, TK, fake_fetch


def sse(*events):
    body = "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events) + "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def delta(**d):
    return {"choices": [{"delta": d, "finish_reason": None}]}


def client(answers, seen, name="groq"):
    def handler(req):
        seen.append(json.loads(req.content))
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    return OpenAICompatClient(name, "k", http=httpx.Client(transport=httpx.MockTransport(handler)))


def ask(c, text="Когда рассчитаются?"):
    agent = ChatAgent(c, "m", Adilet(fetch=fake_fetch), web_search=False)
    return list(agent.stream([{"role": "user", "text": text}],
                             context={"pack": NS(add_days=lambda *a: None), "forums": [], "case": {},
                                      "key_acts": [{"code": TK, "title": "Трудовой кодекс"}]},
                             language="ru", country="X", use_portal=True))


def test_tool_call_streamed_in_pieces_then_answer():
    usage = {"usage": {"prompt_tokens": 40, "completion_tokens": 5}, "choices": []}
    answers = [
        sse(delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "get_article", "arguments": ""}}]),
            delta(tool_calls=[{"index": 0, "function": {"arguments": json.dumps({"act": TK})[:-1]}}]),
            delta(tool_calls=[{"index": 0, "function": {"arguments": ', "article": "113"}'}}]), usage),
        sse(delta(content="По статье 113 расчёт — "), delta(content="не позднее трёх рабочих дней."), usage),
    ]
    seen: list = []
    events = ask(client(answers, seen))
    res = events[-1]["result"]
    assert "".join(e["text"] for e in events if e["type"] == "text").endswith("не позднее трёх рабочих дней.")
    assert res.unchecked is False and res.norms[0]["article"] == "113" and res.usage["input_tokens"] == 80
    first, second = seen
    assert first["model"] == "openai/gpt-oss-120b" and first["stream"] is True
    assert first["messages"][0]["role"] == "system" and TK in first["messages"][0]["content"]
    assert {t["function"]["name"] for t in first["tools"]} >= {"get_article", "act_contents"}
    call, result = second["messages"][2], second["messages"][3]
    assert call["tool_calls"][0]["id"] == "c1" and json.loads(call["tool_calls"][0]["function"]["arguments"]) == {
        "act": TK, "article": "113"}
    assert result["role"] == "tool" and result["tool_call_id"] == "c1" and Q113[:40] in result["content"]


def test_chain_moves_to_the_next_provider_before_the_reply_starts(monkeypatch):
    monkeypatch.setattr(gemini, "RETRY_DELAYS", (0, 0))
    busy = httpx.Response(429, json={"error": {"message": "rate limit"}})
    bad = httpx.Response(401, json={"error": {"message": "invalid key"}})
    first_seen: list = []
    second_seen: list = []
    third_seen: list = []
    chain = ChainClient([client([busy, busy, busy], first_seen, "cerebras"), client([bad], second_seen, "nvidia"),
                         client([sse(delta(content="Ответ."))], third_seen, "groq")])
    events = ask(chain, "вопрос")
    assert "".join(e["text"] for e in events if e["type"] == "text") == "Ответ."
    assert (len(first_seen), len(second_seen), len(third_seen)) == (3, 1, 1)

    with pytest.raises(RuntimeError, match="groq 401"):
        ask(ChainClient([client([bad], [], "cerebras"), client([bad], [], "groq")]))


def test_free_providers_without_a_key_are_skipped():
    s = Settings(chat_free_providers="gemini,cerebras,groq,nvidia", gemini_api_key="g", groq_api_key="q",
                 groq_model="llama-3.3-70b-versatile", cerebras_api_key="", nvidia_api_key="")
    clients = free_chat_clients(s)
    assert [c.name for c in clients] == ["gemini", "groq"] and clients[1].model == "llama-3.3-70b-versatile"
    with pytest.raises(ValueError, match="unknown chat provider"):
        free_chat_clients(Settings(chat_free_providers="gemini,foo"))
