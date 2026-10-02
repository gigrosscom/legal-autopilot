"""PM 02.10 (QA BUG-24 run10): the same story gets the same right scenario five times out of five, and a document is never
made for another subject. The words decide flood, debt, tour and the rest after an accident (routing.direct) before any
model; the model runs at temperature 0."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from konsilier.core import ai
from konsilier.core.engine import EngineError
from konsilier.core.llm.base import DETERMINISTIC_TASKS

from .test_e2e import web_user

CASES = yaml.safe_load((Path(__file__).parent / "data" / "qa_run10_2026-10-02.yaml").read_text("utf-8"))


def _picked(case):
    sc = case["scenario"]["id"] if case["scenario"] else None
    dispute = (case["coverage"].get("dispute") or {}).get("id")
    return sc, dispute


@pytest.mark.parametrize("c", CASES, ids=[c["id"] for c in CASES])
def test_five_runs_one_scenario(ctx, c):
    ctx.container.packs.experimental = True
    seen = set()
    for _ in range(5):
        case = web_user(ctx).post("/v1/cases", expect=201, json={"text": c["text"], "country": "KZ"})["case"]
        sc, dispute = _picked(case)
        seen.add((sc if sc and ".generic." not in sc else None, dispute))
        if "expect" in c:
            assert sc == c["expect"], (c["id"], sc, dispute)
        if "expect_dispute" in c:
            assert dispute == c["expect_dispute"], (c["id"], sc, dispute)
    assert len(seen) == 1, (c["id"], seen)


@pytest.mark.parametrize("cid", ["K1", "K5", "K7", "K9"])
def test_words_win_over_a_wrong_model(ctx, monkeypatch, cid):
    c = next(x for x in CASES if x["id"] == cid)
    monkeypatch.setattr(ai, "qualify", lambda *a, **k: ("kz.consumer.poor_service", 0.9, "wrong guess"))
    monkeypatch.setattr(ai, "classify_taxonomy", lambda *a, **k: {"dispute_id": "consumer.refund", "role": "consumer",
                                                                   "confidence": 0.9})
    case = web_user(ctx).post("/v1/cases", expect=201, json={"text": c["text"], "country": "KZ"})["case"]
    sc, dispute = _picked(case)
    assert sc != "kz.consumer.poor_service"
    assert (c.get("expect") or c.get("expect_dispute")) in (sc, dispute)


def test_no_document_for_another_subject(ctx):
    """A case left with a neighbouring scenario (made before the rules) gets neither a bill nor a document."""
    import uuid

    from konsilier.core.models import Case

    c = next(x for x in CASES if x["id"] == "K7")
    cid = web_user(ctx).post("/v1/cases", expect=201, json={"text": c["text"], "country": "KZ"})["case"]["id"]
    engine = ctx.container.engine
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        assert engine.subject_mismatch(case) is None
        case.scenario_id = "kz.consumer.poor_service"  # what prod picked for the tour before the rules
        assert engine.subject_mismatch(case) == "kz.consumer.service_refund"
        with pytest.raises(EngineError) as e:
            engine.check_subject(case)
        assert e.value.code == "subject_mismatch"
        s.rollback()


def test_every_direct_scenario_exists(ctx):
    for pack in ctx.container.packs.packs.values():
        cov = pack.coverage
        for rule in (cov.routing.direct if cov is not None else []):
            if rule.scenario:
                assert rule.scenario in pack.scenarios, rule.scenario


def test_choosing_runs_at_temperature_zero():
    assert {"qualify", "classify_taxonomy", "extract_fields"} <= DETERMINISTIC_TASKS
