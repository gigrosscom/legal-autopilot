"""ZANN 03.10 (owner's bug «субподрядчик RAMS»): one decision per case — contract for work, labour, a private loan or
a consumer — by the person's own words, without a model (routing.yaml direct rules; a sole trader or company goes to
the business path). The matrix: tests/data/classify/debt_labor.yaml (also team/zann/specs/2026-10-03-debt-labor-matrix.yaml)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from konsilier.core.packs import PackRegistry
from konsilier.core.safety import direct_dispute, writes_as_business

COV = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ").coverage
MATRIX = yaml.safe_load((Path(__file__).parent / "data/classify/debt_labor.yaml").read_text("utf-8"))["cases"]


def decide(text: str) -> str | None:
    if writes_as_business(COV, text):
        return "commercial.b2b_debt"
    rule = direct_dispute(COV, text)
    return rule.dispute if rule is not None else None


@pytest.mark.parametrize("case", [c for c in MATRIX if c.get("expect") and not c["expect"].startswith("consumer.")],
                         ids=lambda c: c["text"][:40])
def test_one_decision_by_the_words(case):
    got = decide(case["text"])
    assert got == case["expect"], (case["text"], got)
    for bad in case.get("never", []):
        assert got != bad


@pytest.mark.parametrize("case", [c for c in MATRIX if (c.get("expect") or "").startswith("consumer.")],
                         ids=lambda c: c["text"][:40])
def test_the_customer_is_never_taken_for_the_contractor(case):
    assert decide(case["text"]) not in ("civil.work_payment", "labor.unpaid_wages", "civil.debt")


def test_labour_inspection_only_on_a_labour_route():
    for key, route in COV.routes.items():
        if any(s.forum == "kz.labor_inspection" for s in route.steps):
            assert key.startswith(("labor.", "kz.labor.")), key
    assert all(s.forum != "kz.labor_inspection" for s in COV.routes["civil.work_payment"].steps)
