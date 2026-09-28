"""Gemini as the backend LLM (free tier): JSON by schema, attachments, errors. Offline (mock transport)."""

from __future__ import annotations

import json

import httpx
import pytest

from konsilier.core.llm.base import Attachment, LLMError
from konsilier.core.llm.gemini_provider import GeminiProvider, _openapi

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["kind", "note"],
          "properties": {"kind": {"type": "string", "enum": ["a", "b"]}, "note": {"type": ["string", "null"]}}}


def provider(handler):
    return GeminiProvider("key", "gemini-3.1-flash-lite", http=httpx.Client(transport=httpx.MockTransport(handler)))


def ok(payload):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]},
                                                     "finishReason": "STOP"}]})


def test_json_answer_with_schema_and_attachment():
    seen = []

    def handler(req):
        seen.append((req.url.path, req.headers["x-goog-api-key"], json.loads(req.content)))
        return ok({"kind": "a", "note": None})

    out = provider(handler).complete_json(task="qualify", system="S", user='{"x":1}', schema=SCHEMA,
                                          attachments=(Attachment("image/png", b"\x89PNG"),))
    assert out == {"kind": "a", "note": None}
    path, key, body = seen[0]
    assert path.endswith("/models/gemini-3.1-flash-lite:generateContent") and key == "key"
    assert body["generationConfig"]["responseJsonSchema"] == SCHEMA
    assert body["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
    assert body["systemInstruction"]["parts"][0]["text"] == "S"


def test_falls_back_to_openapi_schema_when_json_schema_is_rejected():
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body["generationConfig"])
        if "responseJsonSchema" in body["generationConfig"]:
            return httpx.Response(400, json={"error": {"message": "Unknown name \"responseJsonSchema\""}})
        return ok({"kind": "b", "note": "x"})

    p = provider(handler)
    assert p.complete_json(task="t", system="s", user="u", schema=SCHEMA)["kind"] == "b"
    assert calls[1]["responseSchema"]["properties"]["note"] == {"type": "string", "nullable": True}
    assert "additionalProperties" not in json.dumps(calls[1])
    p.complete_json(task="t", system="s", user="u", schema=SCHEMA)
    assert len(calls) == 3  # remembered: no second rejected attempt


@pytest.mark.parametrize("status,body,msg", [
    (429, {"error": {}}, "rate limited"),
    (400, {"error": {"message": "User location is not supported"}}, "location"),
])
def test_errors_become_llm_errors(status, body, msg):
    with pytest.raises(LLMError, match=msg):
        provider(lambda req: httpx.Response(status, json=body)).complete_json(task="t", system="s", user="u",
                                                                             schema=SCHEMA)


def test_blocked_or_truncated():
    for finish, msg in (("SAFETY", "refused"), ("MAX_TOKENS", "truncated")):
        resp = httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": finish}]})
        with pytest.raises(LLMError, match=msg):
            provider(lambda req, r=resp: r).complete_json(task="t", system="s", user="u", schema=SCHEMA)


def test_openapi_conversion():
    assert _openapi({"type": ["null", "integer"], "items": [{"additionalProperties": True}]}) == {
        "type": "integer", "nullable": True, "items": [{}]}


def test_build_provider_without_key_keeps_site_up():
    from konsilier.config import Settings
    from konsilier.core.llm import build_provider
    from konsilier.core.llm.mock import HeuristicMockProvider

    assert isinstance(build_provider(Settings(llm_provider="gemini", gemini_api_key="")), HeuristicMockProvider)
    assert isinstance(build_provider(Settings(llm_provider="gemini", gemini_api_key="k")), GeminiProvider)
