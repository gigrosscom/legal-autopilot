from __future__ import annotations

import base64
import json
import logging
from typing import Any

import anthropic

from .base import Attachment, LLMError

log = logging.getLogger(__name__)


class AnthropicProvider:
    """Claude via the official SDK, JSON guaranteed by structured outputs."""

    def __init__(self, model: str, api_key: str | None = None, refusal_fallback: str | None = "default",
                 max_tokens: int = 16000):
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model
        self.refusal_fallback = refusal_fallback
        self.max_tokens = max_tokens

    def complete_json(self, *, task: str, system: str, user: str, schema: dict[str, Any],
                      attachments: tuple[Attachment, ...] = ()) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        for att in attachments:
            data = base64.standard_b64encode(att.data).decode()
            if att.content_type == "application/pdf":
                content.append({"type": "document",
                                "source": {"type": "base64", "media_type": att.content_type, "data": data}})
            elif att.content_type.startswith("image/"):
                content.append({"type": "image",
                                "source": {"type": "base64", "media_type": att.content_type, "data": data}})
        content.append({"type": "text", "text": user})

        extra: dict[str, Any] = {}
        if self.refusal_fallback:
            # Server-side fallback: a policy decline is retried on a fallback model in the same call.
            extra = {"extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
                     "extra_body": {"fallbacks": self.refusal_fallback}}
        request = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                       messages=[{"role": "user", "content": content}],
                       output_config={"format": {"type": "json_schema", "schema": schema}})
        try:
            try:
                response = self.client.messages.create(**request, **extra)
            except anthropic.BadRequestError as e:
                if not extra:
                    raise
                # e.g. the model or account does not support server-side fallbacks: retry without them
                log.warning("request with refusal fallback rejected (%s); retrying without it", e.message)
                self.refusal_fallback = None
                response = self.client.messages.create(**request)
        except anthropic.RateLimitError as e:
            raise LLMError(f"rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"LLM API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"LLM connection error: {e}") from e

        if response.stop_reason == "refusal":
            raise LLMError(f"LLM refused task {task}")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"LLM output truncated for task {task}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError(f"no text in LLM response for task {task}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON from LLM for task {task}") from e
