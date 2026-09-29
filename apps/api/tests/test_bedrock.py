"""Claude on Amazon Bedrock (LLM_PROVIDER=bedrock): same requests, Bedrock client and model ids."""

import json
from types import SimpleNamespace

import anthropic

from konsilier.config import Settings
from konsilier.core.llm import build_provider
from konsilier.core.llm.anthropic_provider import AnthropicProvider, bedrock_model_id


def test_model_ids_get_the_bedrock_prefix():
    assert bedrock_model_id("claude-sonnet-5") == "anthropic.claude-sonnet-5"
    assert bedrock_model_id("anthropic.claude-haiku-4-5") == "anthropic.claude-haiku-4-5"
    assert bedrock_model_id("eu.anthropic.claude-sonnet-5") == "eu.anthropic.claude-sonnet-5"


def test_build_provider_uses_the_bedrock_client():
    s = Settings(llm_provider="bedrock", llm_model="claude-sonnet-5", llm_fast_model="claude-haiku-4-5",
                 bedrock_region="eu-central-1", bedrock_access_key="AKIATEST", bedrock_secret_key="secret")
    p = build_provider(s)
    assert isinstance(p.client, anthropic.AnthropicBedrockMantle)
    assert p.model_for("narrative") == "anthropic.claude-sonnet-5"
    assert p.model_for("qualify") == "anthropic.claude-sonnet-5"  # deciding the case: main model
    assert p.model_for("extract_fields") == "anthropic.claude-haiku-4-5"
    assert p.refusal_fallback is None  # server-side fallbacks are not offered on Bedrock


class _FakeMessages:
    def __init__(self):
        self.requests = []

    def create(self, **kw):
        self.requests.append(kw)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps({"ok": True}))])


def test_same_structured_request_through_any_client():
    fake = SimpleNamespace(messages=_FakeMessages())
    p = AnthropicProvider(model="anthropic.claude-sonnet-5", fast_model="anthropic.claude-haiku-4-5",
                          refusal_fallback=None, client=fake)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
    assert p.complete_json(task="extract_fields", system="s", user="{}", schema=schema) == {"ok": True}
    req = fake.messages.requests[0]
    assert req["model"] == "anthropic.claude-haiku-4-5"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert "extra_headers" not in req
