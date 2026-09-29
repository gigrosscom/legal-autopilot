"""Zann: the training consent, the anonymised export and the benchmark runner."""

from __future__ import annotations

import json
from pathlib import Path

from konsilier.zann import bench
from konsilier.zann.export import export

from .test_e2e import run_intake, web_user
from .test_payment import ANSWERS, STORY

REPO = Path(__file__).resolve().parents[3]


def test_consent_is_off_by_default_and_can_be_withdrawn(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    assert api.get(f"/v1/cases/{cid}").json()["training_consent"] is False
    assert ctx.client.put(f"/v1/cases/{cid}/training-consent", headers=api.h, json={"given": True}).json()["case"]["training_consent"] is True
    assert ctx.client.put(f"/v1/cases/{cid}/training-consent", headers=api.h, json={"given": False}).json()["case"]["training_consent"] is False


def test_export_has_only_consented_cases_without_personal_data(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    answers = {**ANSWERS, "applicant_name": "Петров Пётр", "applicant_phone": "+7 701 555 44 33",
               "applicant_iin": "900101300123"}
    run_intake(api, cid, answers)
    api.post(f"/v1/cases/{cid}/actions/next")
    other = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]  # no consent
    ctx.client.put(f"/v1/cases/{cid}/training-consent", headers=api.h, json={"given": True})
    with ctx.container.session_factory() as s:
        records = list(export(s, ctx.container.engine))
    assert len(records) == 1 and other not in json.dumps(records)
    text = json.dumps(records[0], ensure_ascii=False)
    for secret in ("Петров", "900101300123", "701 555 44 33", cid):
        assert secret not in text
    assert records[0]["route"]["dispute"] == "consumer.refund" and records[0]["documents"]


def test_benchmark_runs_and_scores_the_first_client_story(ctx):
    items = [i for i in bench.load(REPO / "zann" / "bench") if i["id"] in ("kz-routing-ru-001", "kz-extract-ru-001")]
    assert len(items) == 2
    report = bench.run(ctx.settings.model_copy(update={"packs_dir": ctx.settings.packs_dir}), items,
                       with_examples=False)
    by_id = {r["id"]: r for r in report["results"]}
    assert by_id["kz-routing-ru-001"]["got"]["dispute"] == "commercial.contract_breach"
    assert by_id["kz-routing-ru-001"]["ok"] and by_id["kz-extract-ru-001"]["ok"]
    assert set(report["score"]) == {"routing/cases", "extraction/cases"}
