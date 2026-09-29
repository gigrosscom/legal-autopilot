"""Google Gemini (Generative Language API, REST) behind the small part of the Anthropic client the chat uses.

ChatAgent calls ``client.messages.stream(model=, max_tokens=, system=, tools=, messages=)`` and reads
``text_stream`` and ``get_final_message()``. This adapter translates that request to ``streamGenerateContent``
(server-sent events) and the reply back to text / tool_use blocks, so the chat logic stays the same for both
providers. Server tools (Anthropic web search) have no equivalent here and are skipped.

Gemini 3 returns a ``thoughtSignature`` with function calls that must be sent back unchanged in the next turn;
every block keeps the raw part it came from for that reason.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"
RETRY_STATUSES = (429, 500, 503)  # "high demand" and rate spikes on the free tier pass within seconds
RETRY_DELAY = 1.0  # seconds before the single retry at a model when the answer names no Retry-After
MAX_RETRY_WAIT = 3.0  # Retry-After longer than this: go straight to the next model instead of waiting
MAX_TOTAL_WAIT = 5.0  # all pauses of one request together; the person is waiting for the reply


class GeminiUnavailable(RuntimeError):
    """Every model of the chain is over quota / overloaded (the last status is kept for the logs)."""

    def __init__(self, status: int, text: str):
        super().__init__(f"gemini {status}: {text}")
        self.status_code = status


def retry_after(r: httpx.Response) -> float | None:
    """Seconds the API asks to wait: the Retry-After header, else RetryInfo.retryDelay ("13s") in the body."""
    h = r.headers.get("retry-after")
    if h:
        try:
            return max(0.0, float(h))
        except ValueError:
            pass
    m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', r.text or "")
    return float(m.group(1)) if m else None


@dataclass
class Block:
    type: str  # text | tool_use
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    part: dict[str, Any] = field(default_factory=dict)  # raw Gemini part, echoed back as is


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Message:
    content: list[Block]
    stop_reason: str
    usage: Usage


def _schema(s: dict[str, Any]) -> dict[str, Any]:
    """JSON schema → the OpenAPI subset of function declarations (no additionalProperties)."""
    out = {k: v for k, v in s.items() if k != "additionalProperties"}
    if "properties" in out:
        out["properties"] = {k: _schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _schema(out["items"])
    return out


def _tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decls = [{"name": t["name"], "description": t.get("description", ""), "parameters": _schema(t["input_schema"])}
             for t in tools if "input_schema" in t]
    return [{"functionDeclarations": decls}] if decls else []


def _contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names: dict[str, str] = {}  # tool_use id → function name (function responses are matched by name)
    out = []
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            parts = [{"text": c}]
        else:
            parts = []
            for b in c:
                if isinstance(b, Block):
                    if b.type == "tool_use":
                        names[b.id] = b.name
                    parts.append(b.part or ({"text": b.text} if b.type == "text" else
                                            {"functionCall": {"name": b.name, "args": b.input}}))
                elif b.get("type") == "tool_result":
                    parts.append({"functionResponse": {"name": names.get(b["tool_use_id"], "tool"),
                                                       "response": {"result": b["content"]}}})
                elif b.get("type") == "text":
                    parts.append({"text": b["text"]})
        if parts:
            out.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
    return out


class _Stream:
    def __init__(self, http: httpx.Client, urls: list[str], body: dict[str, Any], headers: dict[str, str]):
        self._http, self._urls, self._body, self._headers = http, urls, body, headers
        self._final: Message | None = None

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    @property
    def text_stream(self) -> Iterator[str]:
        blocks: list[Block] = []
        usage = Usage()
        finish = "STOP"
        r = self._open()
        try:
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                meta = ev.get("usageMetadata") or {}
                usage = Usage(meta.get("promptTokenCount", usage.input_tokens),
                              meta.get("candidatesTokenCount", usage.output_tokens))
                for cand in ev.get("candidates", [])[:1]:
                    finish = cand.get("finishReason", finish)
                    for part in (cand.get("content") or {}).get("parts", []):
                        if "functionCall" in part:
                            fc = part["functionCall"]
                            blocks.append(Block("tool_use", id=fc.get("id") or uuid.uuid4().hex[:12],
                                                name=fc["name"], input=fc.get("args") or {}, part=part))
                        elif part.get("text") and not part.get("thought"):
                            if blocks and blocks[-1].type == "text" and not part.get("thoughtSignature"):
                                blocks[-1].text += part["text"]
                                blocks[-1].part = {**blocks[-1].part, "text": blocks[-1].text}
                            else:
                                blocks.append(Block("text", text=part["text"], part=dict(part)))
                            yield part["text"]
        finally:
            r.close()
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else (
            "max_tokens" if finish == "MAX_TOKENS" else "end_turn")
        self._final = Message(blocks, stop, usage)

    def _open(self) -> httpx.Response:
        """First model that answers. On 429/5xx or a dropped connection a model is retried once after a short pause
        (Retry-After when the API names one, if it is short), then the next model of the chain is tried (free-tier
        quotas are per model). Only before any text reached the reader, so nothing is shown twice."""
        waited = 0.0
        last: httpx.Response | None = None
        dropped: Exception | None = None
        for url in self._urls:
            for attempt in (0, 1):
                try:
                    r = self._http.send(self._http.build_request("POST", url, json=self._body,
                                                                 headers=self._headers), stream=True)
                except httpx.TransportError as e:  # dropped connection under load: same as an overload answer
                    dropped = e
                    if attempt:
                        break
                    time.sleep(RETRY_DELAY)
                    waited += RETRY_DELAY
                    continue
                if r.status_code < 400:
                    return r
                r.read()
                r.close()
                last = r
                if r.status_code not in RETRY_STATUSES:
                    raise RuntimeError(f"gemini {r.status_code}: {r.text[:300]}")
                if attempt:
                    break
                wait = retry_after(r)
                wait = RETRY_DELAY if wait is None else wait
                if wait > MAX_RETRY_WAIT or waited + wait > MAX_TOTAL_WAIT:
                    break  # a long wait: the next model is quicker
                time.sleep(wait)
                waited += wait
        if last is None:
            if dropped is not None:
                raise RuntimeError(f"gemini: {dropped.__class__.__name__}: {dropped}")
            raise RuntimeError("gemini: no model configured")
        raise GeminiUnavailable(last.status_code, last.text[:300])

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        assert self._final is not None
        return self._final


class GeminiClient:
    """``GeminiClient(api_key).messages.stream(...)`` — the Anthropic-shaped surface the chat needs."""

    def __init__(self, api_key: str, *, http: httpx.Client | None = None, timeout: float = 60,
                 fallback_models: tuple[str, ...] = ()):
        self.name, self.api_key, self.fallback_models = "gemini", api_key, fallback_models
        self.http = http or httpx.Client(timeout=timeout)
        self.messages = self

    def stream(self, *, model: str, max_tokens: int, system: str, tools: list[dict[str, Any]],
               messages: list[dict[str, Any]]) -> _Stream:
        body: dict[str, Any] = {"systemInstruction": {"parts": [{"text": system}]}, "contents": _contents(messages),
                                "generationConfig": {"maxOutputTokens": max_tokens}}
        if t := _tools(tools):
            body["tools"] = t
        models = [model, *(m for m in self.fallback_models if m != model)]
        return _Stream(self.http, [f"{BASE}/models/{m}:streamGenerateContent?alt=sse" for m in models], body,
                       {"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
