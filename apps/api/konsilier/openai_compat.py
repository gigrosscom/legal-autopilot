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
import queue
import threading
import time
import uuid
from types import SimpleNamespace as NS
from typing import Any, Iterator

import httpx

from .gemini import RETRY_STATUSES, Block, EmptyReply, Message, Usage, Warm, has_content, has_words, keepalive_http

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
        self._r: httpx.Response | None = None
        self._closed = False
        self.attempts: list[dict[str, Any]] = []  # every HTTP try: status (or error) and ms until the answer

    def close(self) -> None:
        """Stop reading (another provider of the chain answered first); safe to call from another thread."""
        self._closed = True
        if self._r is not None:
            self._r.close()

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def _open(self) -> httpx.Response:
        """Retried on overload and dropped connections, only before any text reached the reader."""
        for delay in (*RETRY_DELAYS, None):
            t0 = time.perf_counter()
            try:
                r = self._http.send(self._http.build_request("POST", self._url, json=self._body,
                                                             headers=self._headers), stream=True)
            except httpx.TransportError as e:
                error = f"{self._name}: {e.__class__.__name__}: {e}"
                self.attempts.append({"status": e.__class__.__name__, "ms": round((time.perf_counter() - t0) * 1000)})
            else:
                self.attempts.append({"status": r.status_code, "ms": round((time.perf_counter() - t0) * 1000)})
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
        r = self._r = self._open()
        if self._closed:
            r.close()
            return
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
                        # a provider that leaves out "index" sends a call's later argument pieces without id or
                        # name: they belong to the call being assembled, not to a new nameless one
                        idx = tc.get("index")
                        if idx is None:
                            fresh = tc.get("id") or (tc.get("function") or {}).get("name")
                            idx = len(calls) if fresh or not calls else max(calls)
                        call = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
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
            if c["name"]:  # a nameless fragment cannot be run
                blocks.append(Block("tool_use", id=c["id"] or uuid.uuid4().hex[:12], name=c["name"], input=args))
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else ("max_tokens" if finish == "length" else "end_turn")
        self._final = Message(blocks, stop, usage)

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        assert self._final is not None
        return self._final


class OpenAICompatClient(Warm):
    """``OpenAICompatClient(name, api_key, model).messages.stream(...)``; ``model=`` of the call is ignored in
    favour of the provider's own model (the chat agent passes one model name for all providers)."""

    def __init__(self, name: str, api_key: str, model: str = "", *, base_url: str = "",
                 http: httpx.Client | None = None, timeout: float = 60):
        default_base, default_model = PROVIDERS.get(name, ("", ""))
        self.name, self.api_key = name, api_key
        self.base_url, self.model = (base_url or default_base).rstrip("/"), model or default_model
        self.http = http or keepalive_http(timeout)
        self.messages = self

    def warm(self) -> None:
        self._warm(f"{self.base_url}/models", {"Authorization": f"Bearer {self.api_key}"})

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
    """The first provider of the chain that starts answering. With ``first_token_timeout`` the next provider is
    asked in parallel once the current one has been silent that long (and at once after a failure); the first to
    start (a word — not blanks or a lone [[MORE]] — or a finished tool call) answers and the others are cancelled
    (their connections closed). Without it, one after another, only after a failure. Nothing is shown twice: only the
    answering provider's words reach the reader. A reply with neither words nor a tool call counts as a failure,
    never as the answer."""

    def __init__(self, clients: list[Any], kwargs: dict[str, Any], first_token_timeout: float = 0):
        self._clients, self._kwargs, self._timeout = clients, kwargs, first_token_timeout
        self._final: Message | None = None
        self.provider = ""
        self.attempts: list[dict[str, Any]] = []  # per provider: how long until it started, or why it did not

    def __enter__(self) -> "_ChainStream":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    @property
    def text_stream(self) -> Iterator[str]:
        if self._timeout > 0 and len(self._clients) > 1:
            yield from self._hedged()
            return
        for i, c in enumerate(self._clients):
            name = getattr(c, "name", type(c).__name__)
            started = False
            t0 = time.perf_counter()
            try:
                with c.messages.stream(**self._kwargs) as s:
                    held = ""
                    for chunk in s.text_stream:
                        if not started:
                            held += chunk
                            if not has_words(held):
                                continue  # blank pieces or a lone marker are no answer yet
                            chunk, held = held.lstrip(), ""
                            self._attempt(name, t0, "answered", s)
                        started = True
                        yield chunk
                    final = s.get_final_message()
                if not started and not has_content(final):
                    raise EmptyReply(f"{name}: empty reply")  # nothing to show: the next provider
                self._final = final
                if not started:
                    self._attempt(name, t0, "answered", s)
                self.provider = name
                return
            except Exception as e:  # overloaded, daily limit reached, key revoked …: the next free provider
                if not started:
                    self._attempt(name, t0, _why(e))
                if started or i == len(self._clients) - 1:
                    raise
                log.warning("chat provider %s failed, trying the next one: %s", name, str(e)[:200])

    def _attempt(self, name: str, t0: float, result: str, s: Any = None) -> None:
        a: dict[str, Any] = {"provider": name, "ms": round((time.perf_counter() - t0) * 1000), "result": result}
        if tries := getattr(s, "attempts", None):
            a["tries"] = tries
        self.attempts.append(a)

    def _hedged(self) -> Iterator[str]:
        events: queue.Queue[tuple[int, str, Any]] = queue.Queue()
        stop = [threading.Event() for _ in self._clients]
        names = [getattr(c, "name", type(c).__name__) for c in self._clients]
        started_at: dict[int, float] = {}
        failed: set[int] = set()
        streams: dict[int, Any] = {}

        def run(i: int) -> None:
            begun = False
            held = ""
            try:
                with self._clients[i].messages.stream(**self._kwargs) as s:
                    streams[i] = s
                    if stop[i].is_set():
                        return
                    for chunk in s.text_stream:
                        if stop[i].is_set():
                            return
                        if not begun:
                            held += chunk
                            if not has_words(held):
                                continue  # blank pieces or a lone marker must not win the race (an empty reply)
                            chunk, held = held.lstrip(), ""
                        begun = True
                        events.put((i, "text", chunk))
                    if stop[i].is_set():
                        return
                    final = s.get_final_message()
                if not begun and not has_content(final):
                    raise EmptyReply(f"{names[i]}: empty reply")  # an empty reply never wins the race
                events.put((i, "final", (final, getattr(s, "attempts", None))))
            except Exception as e:  # reported to the reader thread, which decides
                if not stop[i].is_set():
                    events.put((i, "error", e))

        def launch(i: int) -> None:
            started_at[i] = time.perf_counter()
            threading.Thread(target=run, args=(i,), name=f"chat-{names[i]}", daemon=True).start()

        def cancel(j: int) -> None:
            """The loser stops at once: its connection is closed, whatever it would still send is never read."""
            stop[j].set()
            close = getattr(streams.get(j), "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 — closing a finished or broken stream
                    pass

        launch(0)
        winner: int | None = None
        try:
            while True:
                pending = [i for i in started_at if i not in failed]
                nxt = len(started_at) if len(started_at) < len(self._clients) else None
                if winner is None and nxt is not None and not pending:
                    launch(nxt)  # everyone asked so far failed: the next one at once
                    continue
                wait = None
                if winner is None and nxt is not None:
                    wait = max(0.0, started_at[nxt - 1] + self._timeout - time.perf_counter())
                try:
                    i, kind, payload = events.get(timeout=wait)
                except queue.Empty:  # the latest one is silent too long: ask the next in parallel
                    log.info("chat provider %s has not started after %.1f s, asking %s too", names[nxt - 1],
                             self._timeout, names[nxt])
                    launch(nxt)
                    continue
                if winner is None:
                    if kind == "error":
                        failed.add(i)
                        self._attempt(names[i], started_at[i], _why(payload))
                        log.warning("chat provider %s failed, trying the next one: %s", names[i], str(payload)[:200])
                        if len(failed) == len(self._clients):
                            raise payload
                        continue
                    winner = i
                    self._attempt(names[i], started_at[i], "answered",
                                  NS(attempts=payload[1]) if kind == "final" else streams.get(i))
                    for j in list(started_at):
                        if j != i:
                            cancel(j)
                            if j not in failed:
                                self._attempt(names[j], started_at[j], "dropped")
                if i != winner:
                    continue
                if kind == "text":
                    yield payload
                elif kind == "final":
                    self._final = payload[0]
                    self.provider = names[i]
                    return
                else:
                    raise payload
        finally:  # the reader stopped (answer done, the person left): every provider still reading stops
            for j in range(len(self._clients)):
                if not stop[j].is_set() and not (j == winner and self._final is not None):
                    cancel(j)
                stop[j].set()

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        assert self._final is not None
        return self._final


def _why(e: Exception) -> str:
    status = getattr(e, "status_code", None)
    return f"error {status}" if status else f"error {type(e).__name__}: {str(e)[:80]}"


class ChainClient:
    """Tries each client in turn until one starts answering; a failure after text was shown is raised.
    ``first_token_timeout`` > 0: a provider silent that long gets the next one asked in parallel (see
    ``_ChainStream``). ``stream(prefer=name)`` asks that provider first (the one that began the conversation's turn
    keeps its own tool calls)."""

    accepts_prefer = True
    name = "free"

    def __init__(self, clients: list[Any], first_token_timeout: float = 0):
        if not clients:
            raise ValueError("ChainClient needs at least one client")
        self.clients, self.first_token_timeout = clients, first_token_timeout
        self.messages = self

    def stream(self, prefer: str = "", **kwargs: Any) -> _ChainStream:
        clients = self.clients
        if prefer:
            # a continuation of a turn (after a tool call) is never raced: another model would not continue the
            # text already shown but write the whole answer again (a doubled reply, 30.09); the others are asked
            # only if this one fails before its first word
            clients = sorted(clients, key=lambda c: getattr(c, "name", "") != prefer)
            return _ChainStream(clients, kwargs, 0)
        return _ChainStream(clients, kwargs, self.first_token_timeout)

    def warm(self) -> None:
        """Open the connections of the first providers (TLS takes a few hundred ms) before the person's message."""
        for c in self.clients[:2]:
            if hasattr(c, "warm"):
                c.warm()
