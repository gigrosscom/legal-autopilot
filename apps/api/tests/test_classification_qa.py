"""QA BUG-17/18 (01.10): the nine first messages that got no scenario or a neighbouring one. Checked on the keyword
fallback (no LLM): every scenario's own keywords must lead to the right one; the LLM sees the same keywords, the
examples and «not_when» on top."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from konsilier.core import ai
from konsilier.core.packs import PackRegistry

REPO = Path(__file__).resolve().parents[3]
CASES = yaml.safe_load((Path(__file__).parent / "data" / "classification_qa_2026-10-01.yaml").read_text("utf-8"))


def _options(lang: str):
    pack = PackRegistry.load(REPO / "packs").pack("KZ")
    return [{"id": sc.id, "keywords": [k for ks in sc.classification.keywords.values() for k in ks]}
            for sc in pack.scenarios.values()], pack


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_qa_message_gets_its_scenario(case):
    options, _ = _options(case["lang"])
    sid, _, why = ai._keyword_qualify(options, case["text"])
    assert sid == case["expect"], (case["id"], sid, why)


def test_neighbouring_scenarios_say_when_they_do_not_apply():
    _, pack = _options("ru")
    for sid in ("kz.money.credit_fraud", "kz.social.benefit_application", "kz.services.tender_application",
                "kz.consumer.refund"):
        assert pack.scenarios[sid].classification.not_when.get("ru"), sid
