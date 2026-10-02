from __future__ import annotations

import base64
import json
import logging
import threading
from typing import Any

import anthropic

from .base import DETERMINISTIC_TASKS, Attachment, LLMError

log = logging.getLogger(__name__)


# Tasks that write text for the applicant's document get the main model; the rest (classification,
# field extraction, reading a receipt) are short structured answers and go to the cheaper model.
# the steps that decide the case and read its documents run on the main model too: quality over speed
MAIN_MODEL_TASKS = frozenset({"narrative", "generic_demands", "qualify", "extract_evidence"})
# Server-side refusal fallbacks are offered for these model families only.
_FALLBACK_MODEL_PREFIXES = ("claude-opus-5", "claude-fable-5")


class AnthropicProvider:
    """Claude via the official SDK, JSON guaranteed by structured outputs.

    The same code serves the Claude API and Amazon Bedrock (``bedrock()`` below): only the client and the
    model ids differ, requests and responses are identical."""

    def __init__(self, model: str, api_key: str | None = None, refusal_fallback: str | None = "default",
                 max_tokens: int = 16000, fast_model: str | None = None, client: Any = None):
        self.client = client or (anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic())
        self.model = model
        self.fast_model = fast_model or model
        self.refusal_fallback = refusal_fallback
        self.max_tokens = max_tokens
        self._usage = threading.local()  # tokens of this thread's last call, read by the spend guard

    @property
    def last_usage(self) -> dict[str, Any] | None:
        return getattr(self._usage, "value", None)

    @last_usage.setter
    def last_usage(self, value: dict[str, Any] | None) -> None:
        self._usage.value = value

    def model_for(self, task: str) -> str:
        return self.model if task in MAIN_MODEL_TASKS else self.fast_model

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

        model = self.model_for(task)
        extra: dict[str, Any] = {}
        if self.refusal_fallback and model.startswith(_FALLBACK_MODEL_PREFIXES):
            # Server-side fallback: a policy decline is retried on a fallback model in the same call.
            extra = {"extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
                     "extra_body": {"fallbacks": self.refusal_fallback}}
        request = dict(model=model, max_tokens=self.max_tokens, system=system,
                       messages=[{"role": "user", "content": content}],
                       output_config={"format": {"type": "json_schema", "schema": schema}})
        if task in DETERMINISTIC_TASKS:
            request["temperature"] = 0
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

        usage = getattr(response, "usage", None)
        if usage is not None:
            self.last_usage = {"model": model, "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                               "output_tokens": int(getattr(usage, "output_tokens", 0) or 0)}
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


def bedrock_model_id(model: str) -> str:
    """Bedrock model ids carry the "anthropic." prefix: claude-sonnet-5 → anthropic.claude-sonnet-5.
    Ids that already have a prefix (anthropic.…, or a regional profile like eu.anthropic.…) stay as they are."""
    return model if "." in model else f"anthropic.{model}"


def bedrock(model: str, fast_model: str | None, region: str, access_key: str | None = None,
            secret_key: str | None = None, max_tokens: int = 16000) -> AnthropicProvider:
    """Claude on Amazon Bedrock (paid from AWS credits, e.g. AWS Activate). Credentials: explicit keys,
    else the standard AWS chain (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, profile, instance role).
    Server-side refusal fallbacks are not available on Bedrock, so they are off."""
    kw: dict[str, Any] = {"aws_region": region}
    if access_key and secret_key:
        kw.update(aws_access_key=access_key, aws_secret_key=secret_key)
    client = anthropic.AnthropicBedrockMantle(**kw)
    return AnthropicProvider(model=bedrock_model_id(model),
                             fast_model=bedrock_model_id(fast_model) if fast_model else None,
                             refusal_fallback=None, max_tokens=max_tokens, client=client)
