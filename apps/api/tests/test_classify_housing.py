"""ZANN 04.10 (housing & tenancy domain): deposit, eviction, a tenant who won't leave, utility recalculation, the
condominium — by the person's own words, without a model (routing.yaml direct rules). The matrix:
tests/data/classify/housing.yaml (also team/zann/specs/2026-10-04-housing-matrix.yaml)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from konsilier.core.packs import PackRegistry
from konsilier.core.safety import direct_dispute

COV = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ").coverage
MATRIX = yaml.safe_load((Path(__file__).parent / "data/classify/housing.yaml").read_text("utf-8"))["cases"]


def decide(text: str) -> str | None:
    rule = direct_dispute(COV, text)
    return (rule.scenario or rule.dispute) if rule is not None else None


@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c["text"][:40])
def test_housing_by_the_words(case):
    got = decide(case["text"])
    if case.get("expect"):
        assert got == case["expect"], (case["text"], got)
    for bad in case.get("never", []):
        assert got != bad, (case["text"], got)


def test_the_tenancy_route_says_eviction_is_by_court_only():
    why = COV.routes["housing.tenancy"].steps[0].why["ru"]
    assert "только по решению суда" in why and "3 месяца" in why and "1 месяц" in why
    assert "ст. 24 п. 5" in COV.routes["housing.tenancy"].steps[0].norm
