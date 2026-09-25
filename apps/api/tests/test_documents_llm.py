import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from konsilier.core.documents import LibreOfficeConverter, docx_text, render_docx
from konsilier.core.llm.anthropic_provider import AnthropicProvider
from konsilier.core.llm.base import LLMError

TEMPLATE = Path(__file__).resolve().parents[3] / "packs" / "kz" / "templates" / "consumer" / "claim_seller.docx"
CTX = {"f": {"purchase_date": "12.08.2026", "goods_description": "Чайник <A&B>", "amount": "5 000",
             "applicant_phone": "+7700"}, "addressee": {"name": "ТОО Ромашка", "id": None},
       "applicant": {"name": "Иванов И.И.", "id": ""}, "narrative": "Чайник сломался.", "demands": "вернуть деньги",
       "norm_refs": ["TODO"], "evidence": [], "currency": "KZT", "date": "25.09.2026"}


def test_render_adds_ai_label_and_draft_and_escapes():
    data = render_docx(TEMPLATE, CTX, ai_label="AI-LABEL", draft_disclaimer="DRAFT-NOTE")
    text = docx_text(data)
    assert "Чайник <A&B>" in text  # autoescaped in XML, intact in text
    assert text.count("AI-LABEL") == 2  # body + footer
    assert "DRAFT-NOTE" in text
    assert "БИН" not in text  # optional line suppressed
    assert "Приложения" not in text  # empty list → section suppressed


def test_reviewed_scenario_has_no_draft_note():
    assert "DRAFT-NOTE" not in docx_text(render_docx(TEMPLATE, CTX, ai_label="AI", draft_disclaimer=None))


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_pdf_conversion_with_libreoffice():
    pdf = LibreOfficeConverter("soffice").convert(render_docx(TEMPLATE, CTX, ai_label="AI", draft_disclaimer=None))
    assert pdf is not None and pdf.startswith(b"%PDF")


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def provider_with(response) -> tuple[AnthropicProvider, FakeMessages]:
    p = AnthropicProvider(model="claude-opus-5", api_key="test-key")
    fake = FakeMessages(response)
    p.client = SimpleNamespace(messages=fake)
    return p, fake


def test_anthropic_provider_request_shape():
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"a": 1}')])
    p, fake = provider_with(resp)
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"],
              "additionalProperties": False}
    assert p.complete_json(task="t", system="sys", user=json.dumps({"x": 1}), schema=schema) == {"a": 1}
    kw = fake.kwargs
    assert kw["model"] == "claude-opus-5"
    assert kw["output_config"] == {"format": {"type": "json_schema", "schema": schema}}
    assert kw["system"] == "sys"
    assert kw["messages"][0]["content"][-1] == {"type": "text", "text": '{"x": 1}'}
    assert kw["extra_body"] == {"fallbacks": "default"}


def test_anthropic_provider_refusal_raises():
    p, _ = provider_with(SimpleNamespace(stop_reason="refusal", content=[]))
    with pytest.raises(LLMError, match="refused"):
        p.complete_json(task="t", system="s", user="{}", schema={})
