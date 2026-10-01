"""BUG-20 (QA run 5, 01.10): with the model out of quota the scenario is chosen by keywords (confidence ≤ 0.55 →
needs_review), and every paid pre-trial document waited for the owner. The owner's rule (30.09): the manual check is
for court documents only; the case is still flagged for the owner in /ops."""
from __future__ import annotations

from konsilier.core import ai
from konsilier.core.llm import LLMError

from .test_payment import qualified_case


def test_keyword_fallback_still_gives_a_claim_at_once(ctx, monkeypatch):
    def down(*a, **k):
        raise LLMError("quota")
    real = ai.qualify
    monkeypatch.setattr(ai, "qualify", lambda llm, *a, **k: real(type("L", (), {"complete_json": down})(), *a, **k))
    api, cid = qualified_case(ctx)
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["needs_review"] is True  # the owner still sees it in /ops
    out = api.post(f"/v1/cases/{cid}/actions/next")  # stub payment: paid at once
    action = out["case"]["actions"][-1]
    assert action["approval_status"] != "pending" and action["downloadable"]


def test_a_lawsuit_still_waits_for_the_check(ctx):
    eng = ctx.container.engine
    sc = eng.packs.scenario("kz.family.alimony")
    spec = next(a for a in sc.actions if eng._to_court(type("C", (), {"scenario_id": sc.id, "jurisdiction": "KZ", "facts": {}, "taxonomy": {}})(), a))
    case = type("C", (), {"scenario_id": sc.id, "jurisdiction": "KZ", "facts": {}, "taxonomy": {}, "needs_review": True, "hold_reason": None,
                          "coverage_level": "verified", "created_at": None})()
    assert eng.approval_required(None, case, spec) is True
