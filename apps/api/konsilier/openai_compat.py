"""OpenAI-compatible chat completions (Groq, Cerebras, NVIDIA NIM, Mistral, OpenRouter …) behind the same small
Anthropic-shaped surface as ``konsilier.gemini.GeminiClient``, plus ``ChainClient`` that tries several free
providers in turn.

ChatAgent calls ``client.messages.stream(model=, max_tokens=, system=, tools=, messages=)`` and reads
``text_stream`` and ``get_final_message()``. The request becomes ``POST {base}/chat/completions`` with
``stream: true``; the reply comes back as text / tool_use blocks. Server tools (Anthropic web search) are skipped.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Iterator

import httpx

from .gemini import RETRY_STATUSES, Block, Message, Usage

log = logging.getLogger(__name__)
RETRY_DELAYS = (0.5, 1.5)  # seconds before the 2nd and 3rd attempt at a provider

# name → (base URL, default model). Models are overridable in settings; check them at the provider's /models.
# Chosen on a real case question in ru/kk with the portal tools (2026-09): qwen-3.8-27b on Cerebras answers best and
# has by far the largest free quota (150k tokens/min); Groq's free tier is 8k tokens/min (about one chat reply);
# NVIDIA's free models returned empty replies or timed out, so it is not in the default chain.
PROVIDERS: dict[str, tuple[str, str]] = {
    "cerebras": ("https://api.cerebras.ai/v1", "qwen-3.8-27b"),
    "groq": ("https://api.groq.com/openai/v1", "qwen/qwen3.8-27b"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3-super-120b-a12b"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-oss-120b:free"),
}


def _tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                              "parameters": t["input_schema"]}}
            for t in tools if "input_schema" in t]


def _messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            out.append({"role": m["role"], "content": c})
            continue
        if m["role"] == "assistant":
            text = "".join(b.text for b in c if isinstance(b, Block) and b.type == "text")
            calls = [{"id": b.id, "type": "function",
                      "function": {"name": b.name, "arguments": json.dumps(b.input, ensure_ascii=False)}}
                     for b in c if isinstance(b, Block) and b.type == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        texts = []
        for b in c:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                content = b["content"] if isinstance(b["content"], str) else json.dumps(b["content"], ensure_ascii=False)
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": content})
            elif isinstance(b, dict) and b.get("type") == "text":
                texts.append(b["text"])
        if texts:
            out.append({"role": "user", "content": "\n".join(texts)})
    return out


class _Stream:
    def __init__(self, http: httpx.Client, url: str, body: dict[str, Any], headers: dict[str, str], name: str):
        self._http, self._url, self._body, self._headers, self._name = http, url, body, headers, name
        self._final: Message | None = None

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def _open(self) -> httpx.Response:
        """Retried on overload and dropped connections, only before any text reached the reader."""
        for delay in (*RETRY_DELAYS, None):
            try:
                r = self._http.send(self._http.build_request("POST", self._url, json=self._body,
                                                             headers=self._headers), stream=True)
            except httpx.TransportError as e:
                error = f"{self._name}: {e.__class__.__name__}: {e}"
            else:
                if r.status_code < 400:
                    return r
                r.read()
                r.close()
                error = f"{self._name} {r.status_code}: {r.text[:300]}"
                if r.status_code not in RETRY_STATUSES:
                    raise RuntimeError(error)
            if delay is None:
                raise RuntimeError(error)
            time.sleep(delay)
        raise AssertionError("unreachable")

    @property
    def text_stream(self) -> Iterator[str]:
        text: list[str] = []
        calls: dict[int, dict[str, Any]] = {}  # index → {"id", "name", "arguments"} assembled from deltas
        usage = Usage()
        finish = "stop"
        r = self._open()
        try:
            for line in r.iter_lines():
                if not line.startswith("data: ") or line[6:].strip() == "[DONE]":
                    continue
                ev = json.loads(line[6:])
                if u := ev.get("usage"):
                    usage = Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
                for ch in ev.get("choices", [])[:1]:
                    finish = ch.get("finish_reason") or finish
                    delta = ch.get("delta") or {}
                    for tc in delta.get("tool_calls") or []:
                        call = calls.setdefault(tc.get("index", len(calls)), {"id": "", "name": "", "arguments": ""})
                        fn = tc.get("function") or {}
                        call["id"] = tc.get("id") or call["id"]
                        call["name"] += fn.get("name") or ""
                        call["arguments"] += fn.get("arguments") or ""
                    if chunk := delta.get("content"):
                        text.append(chunk)
                        yield chunk
        finally:
            r.close()
        blocks = [Block("text", text="".join(text))] if text else []
        for _, c in sorted(calls.items()):
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            blocks.append(Block("tool_use", id=c["id"] or uuid.uuid4().hex[:12], name=c["name"], input=args))
        stop = "tool_use" if calls else ("max_tokens" if finish == "length" else "end_turn")
        self._final = Message(blocks, stop, usage)

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        assert self._final is not None
        return self._final


class OpenAICompatClient:
    """``OpenAICompatClient(name, api_key, model).messages.stream(...)``; ``model=`` of the call is ignored in
    favour of the provider's own model (the chat agent passes one model name for all providers)."""

    def __init__(self, name: str, api_key: str, model: str = "", *, base_url: str = "",
                 http: httpx.Client | None = None, timeout: float = 60):
        default_base, default_model = PROVIDERS.get(name, ("", ""))
        self.name, self.api_key = name, api_key
        self.base_url, self.model = (base_url or default_base).rstrip("/"), model or default_model
        self.http = http or httpx.Client(timeout=timeout)
        self.messages = self

    def stream(self, *, model: str, max_tokens: int, system: str, tools: list[dict[str, Any]],
               messages: list[dict[str, Any]]) -> _Stream:
        body: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "stream": True,
                                "stream_options": {"include_usage": True},
                                "messages": _messages(system, messages)}
        if t := _tools(tools):
            body["tools"] = t
        return _Stream(self.http, f"{self.base_url}/chat/completions", body,
                       {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, self.name)


class _ChainStream:
    def __init__(self, clients: list[Any], kwargs: dict[str, Any]):
        self._clients, self._kwargs = clients, kwargs
        self._final: Message | None = None
        self.provider = ""

    def __enter__(self) -> "_ChainStream":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    @property
    def text_stream(self) -> Iterator[str]:
        for i, c in enumerate(self._clients):
            name = getattr(c, "name", type(c).__name__)
            started = False
            try:
                with c.messages.stream(**self._kwargs) as s:
                    for chunk in s.text_stream:
                        started = True
                        yield chunk
                    self._final = s.get_final_message()
                self.provider = name
                return
            except Exception as e:  # overloaded, daily limit reached, key revoked …: the next free provider
                if started or i == len(self._clients) - 1:
                    raise
                log.warning("chat provider %s failed, trying the next one: %s", name, str(e)[:200])

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        assert self._final is not None
        return self._final


class ChainClient:
    """Tries each client in turn until one starts answering; a failure after text was shown is raised."""

    def __init__(self, clients: list[Any]):
        if not clients:
            raise ValueError("ChainClient needs at least one client")
        self.clients = clients
        self.messages = self

    def stream(self, **kwargs: Any) -> _ChainStream:
        return _ChainStream(self.clients, kwargs)
