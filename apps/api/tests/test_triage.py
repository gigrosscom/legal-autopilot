"""«Юридический разбор» of the first message before the scenario (owner 01.10): category, subject, parties, where the
case is filed, the scenario, how sure and what is missing — one model call with the lawyer's rules
(packs/kz/triage.yaml), a check by the rules' own words, kept in the case and the log, shown in /ops, one clarifying
question when unsure."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from konsilier.core import ai, triage
from konsilier.core.llm.mock import HeuristicMockProvider

from .test_e2e import web_user

ADMIN = {"X-Admin-Token": "adm"}
FIRST = yaml.safe_load((Path(__file__).parent / "data" / "triage_first_messages.yaml").read_text("utf-8"))


@pytest.fixture
def rules(ctx):
    return ctx.container.packs.pack("KZ").triage


def test_the_rules_are_the_packs(ctx, rules):
    launch = [sid for sid, sc in rules["scenarios"].items() if sc.get("launch")]
    assert len(launch) == 10
    for sid in launch:  # every launch scenario is published and has a route in its category
        assert ctx.container.packs.scenario(sid).published
        assert triage.route(rules, rules["scenarios"][sid]["category"])["files_to"]
    assert 0 < rules["min_confidence"] <= 1
    # the lawyer's routes: a labour court only after the conciliation commission; the police — the person files
    assert triage.route(rules, "labor")["pretrial"] == "required"
    assert triage.route(rules, "criminal")["files_to"] == "police"


@pytest.mark.parametrize("case", FIRST, ids=[c["text"][:40] for c in FIRST])
def test_thirty_first_messages(rules, case):
    got = triage.guess(rules, case["text"])
    assert (got["scenario_id"], got["category"]) == (case["scenario"], case["category"]), got
    assert case["subject"] in rules["scenarios"][got["scenario_id"]]["subject"]


def test_the_lawyers_never_when_words_cap_the_model(ctx, rules):
    """The first paid case: AI tokens in the goods scenario — never a confident document, whatever the model says."""
    packs = ctx.container.packs
    out = {"category": "consumer", "subcategory": "goods_refund", "subject": "goods", "client_kind": "person",
           "respondent_kind": "seller", "channel": "online", "counterparty": "business", "missing": [],
           "question": "", "scenario_id": "kz.consumer.refund", "confidence": 0.95, "reason": "купил"}
    llm = type("L", (), {"complete_json": lambda self, **_: out})()
    details: dict = {}
    sid, conf, why = ai.qualify(llm, packs.published("KZ"), packs.packs, "Купил токены для ИИ-сервиса", "ru",
                                details, rules)
    assert sid == "kz.consumer.refund" and conf <= 0.3 and "never_when" in why
    assert details["_triage"]["category"] == "consumer"


def _mock(monkeypatch, outs):
    """The model's triage answers, one per call, in order."""
    queue = list(outs)
    real = HeuristicMockProvider._qualify

    def qualify(self, p):
        assert "triage" in p and p["scenarios"][0].get("choose_when") is not None  # the rules reach the model
        return queue.pop(0) if queue else real(self, p)
    monkeypatch.setattr(HeuristicMockProvider, "_qualify", qualify)


SURE = {"category": "consumer", "subcategory": "digital", "subject": "digital_content", "client_kind": "person",
        "respondent_kind": "provider", "channel": "online", "counterparty": "business",
        "missing": ["дата оплаты", "сумма"], "question": "", "scenario_id": "kz.consumer.service_refund",
        "confidence": 0.9, "reason": "токены сервиса — услуга"}


def test_the_triage_is_kept_logged_and_shown(ctx, monkeypatch):
    _mock(monkeypatch, [SURE])
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Оплатил токены ИИ-сервиса, не начислили", "country": "KZ"})["case"]["id"]
    case = ctx.client.get(f"/v1/admin/cases/{cid}", headers=ADMIN).json()
    t = case["triage"]
    assert t["scenario_id"] == "kz.consumer.service_refund" and t["category"] == "consumer"
    assert t["subject"] == "digital_content" and t["respondent_kind"] == "provider" and t["missing"] == ["дата оплаты", "сумма"]
    assert t["route"]["files_to"] == "respondent" and "42-4" in t["route"]["first"]  # from the rules, not the model
    assert t["agrees"] is True and t["confidence"] == 0.9
    log = ctx.client.get("/v1/admin/triage", headers=ADMIN).json()
    assert log["count"] >= 1 and log["items"][0]["case_id"] == cid
    assert log["items"][0]["triage"]["scenario_id"] == "kz.consumer.service_refund"
    assert "токены" in log["items"][0]["text"]
    assert ctx.client.get("/v1/admin/triage", params={"since": "2999-01-01T00:00:00"}, headers=ADMIN).json()["count"] == 0
    assert ctx.client.get("/v1/admin/triage").status_code in (401, 403)


def test_unsure_asks_one_question_first(ctx, monkeypatch):
    unsure = {**SURE, "confidence": 0.5, "question": "Это была подписка на сервис или вещь?"}
    _mock(monkeypatch, [unsure, unsure])
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": "Купил и не работает, верните деньги", "country": "KZ"})
    assert out["reply"]["message"] == "Это была подписка на сервис или вещь?"
    assert out["case"]["scenario"] is None and out["case"]["status"] == "intake"
    # the answer goes into the story; still unsure — but the question is never asked twice
    nxt = api.answer(out["case"]["id"], "Подписка на нейросеть")
    assert nxt["case"]["scenario"]["id"] == "kz.consumer.service_refund"
    assert "Подписка на нейросеть" in ctx.client.get(f"/v1/admin/cases/{out['case']['id']}", headers=ADMIN).json()["initial_text"]
