from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from .base import Attachment, LLMError

log = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _openapi(s: Any) -> Any:
    """JSON schema → the OpenAPI subset of ``responseSchema`` (older endpoint form): no additionalProperties,
    ``["string", "null"]`` becomes ``nullable``."""
    if isinstance(s, list):
        return [_openapi(x) for x in s]
    if not isinstance(s, dict):
        return s
    out = {k: _openapi(v) for k, v in s.items() if k not in ("additionalProperties", "$schema")}
    t = out.get("type")
    if isinstance(t, list):
        rest = [x for x in t if x != "null"]
        out["type"] = rest[0] if rest else "string"
        if "null" in t:
            out["nullable"] = True
    return out


class GeminiProvider:
    """Google Gemini (REST, free tier of AI Studio keys) with JSON constrained to the schema."""

    def __init__(self, api_key: str, model: str, *, http: httpx.Client | None = None, timeout: float = 45):
        self.api_key, self.model = api_key, model
        self.http = http or httpx.Client(timeout=timeout)
        self._json_schema_field = "responseJsonSchema"  # falls back to responseSchema if the API rejects it

    def model_for(self, task: str) -> str:
        return self.model

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        return self.http.post(f"{BASE}/models/{self.model}:generateContent", json=body,
                              headers={"x-goog-api-key": self.api_key})

    def complete_json(self, *, task: str, system: str, user: str, schema: dict[str, Any],
                      attachments: tuple[Attachment, ...] = ()) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [
            {"inlineData": {"mimeType": a.content_type, "data": base64.standard_b64encode(a.data).decode()}}
            for a in attachments if a.content_type == "application/pdf" or a.content_type.startswith("image/")]
        parts.append({"text": user})

        def body(field: str) -> dict[str, Any]:
            return {"systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"responseMimeType": "application/json",
                                         field: schema if field == "responseJsonSchema" else _openapi(schema)}}

        try:
            r = self._post(body(self._json_schema_field))
            if r.status_code == 400 and self._json_schema_field == "responseJsonSchema" and "responseJsonSchema" in r.text:
                log.warning("responseJsonSchema rejected; using responseSchema")
                self._json_schema_field = "responseSchema"
                r = self._post(body("responseSchema"))
        except httpx.HTTPError as e:
            raise LLMError(f"LLM connection error: {e}") from e
        if r.status_code == 429:
            raise LLMError("rate limited: free Gemini quota reached")
        if r.status_code >= 400:
            raise LLMError(f"LLM API error {r.status_code}: {r.text[:300]}")
        try:
            data = r.json()
        except ValueError as e:
            raise LLMError(f"invalid response from LLM for task {task}") from e
        cand = (data.get("candidates") or [{}])[0]
        finish = cand.get("finishReason")
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"):
            raise LLMError(f"LLM refused task {task}")
        if finish == "MAX_TOKENS":
            raise LLMError(f"LLM output truncated for task {task}")
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
        if not text:
            raise LLMError(f"no text in LLM response for task {task}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON from LLM for task {task}") from e
