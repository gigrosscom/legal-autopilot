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
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"
RETRY_STATUSES = (429, 500, 503)  # "high demand" and rate spikes on the free tier pass within seconds
RETRY_DELAYS = (1.0, 3.0)  # seconds before the 2nd and 3rd attempt


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
    def __init__(self, http: httpx.Client, url: str, body: dict[str, Any], headers: dict[str, str]):
        self._http, self._url, self._body, self._headers = http, url, body, headers
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
        for delay in (*RETRY_DELAYS, None):  # retried only before any text reached the reader
            r = self._http.send(self._http.build_request("POST", self._url, json=self._body, headers=self._headers),
                                stream=True)
            if r.status_code < 400:
                break
            r.read()
            r.close()
            if r.status_code not in RETRY_STATUSES or delay is None:
                raise RuntimeError(f"gemini {r.status_code}: {r.text[:300]}")
            time.sleep(delay)
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

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        assert self._final is not None
        return self._final


class GeminiClient:
    """``GeminiClient(api_key).messages.stream(...)`` — the Anthropic-shaped surface the chat needs."""

    def __init__(self, api_key: str, *, http: httpx.Client | None = None, timeout: float = 60):
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=timeout)
        self.messages = self

    def stream(self, *, model: str, max_tokens: int, system: str, tools: list[dict[str, Any]],
               messages: list[dict[str, Any]]) -> _Stream:
        body: dict[str, Any] = {"systemInstruction": {"parts": [{"text": system}]}, "contents": _contents(messages),
                                "generationConfig": {"maxOutputTokens": max_tokens}}
        if t := _tools(tools):
            body["tools"] = t
        return _Stream(self.http, f"{BASE}/models/{model}:streamGenerateContent?alt=sse", body,
                       {"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
