"""Owner 01.10 (the first paid case): the subject of the dispute is decided before the scenario, and a document is
read against the lawyer's rules before it is given (team/legal-drafts/document-rules.md D-18, D-19)."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from konsilier.core import ai, legal_check
from konsilier.core.models import Action, AuditLog, Case

from .test_doc_quality import claim_text

ADMIN = {"X-Admin-Token": "adm"}


class FakeLLM:
    def __init__(self, out):
        self.out = out

    def complete_json(self, **_):
        return self.out


def test_the_subject_decides_the_scenario(ctx):
    packs = ctx.container.packs
    candidates = packs.published("KZ")
    details: dict = {}
    # the model says «service» but picks the goods scenario: never a confident document from it
    sid, conf, why = ai.qualify(FakeLLM({"subject": "service", "channel": "online", "counterparty": "business",
                                         "scenario_id": "kz.consumer.refund", "confidence": 0.9, "reason": "купил"}),
                                candidates, packs.packs, "Купил токены ИИ-сервиса", "ru", details)
    assert sid == "kz.consumer.refund" and conf <= 0.3 and "subject service" in why
    assert details == {"subject": "service", "channel": "online", "counterparty": "business"}
    sid, conf, _ = ai.qualify(FakeLLM({"subject": "service", "channel": "online", "counterparty": "business",
                                       "scenario_id": "kz.consumer.service_refund", "confidence": 0.9, "reason": ""}),
                              candidates, packs.packs, "Купил токены ИИ-сервиса", "ru")
    assert sid == "kz.consumer.service_refund" and conf == 0.9
    sid, conf, _ = ai.qualify(FakeLLM({"subject": "goods", "channel": "offline", "counterparty": "business",
                                       "scenario_id": "kz.consumer.refund", "confidence": 0.9, "reason": ""}),
                              candidates, packs.packs, "Купил холодильник, сломался", "ru")
    assert sid == "kz.consumer.refund" and conf == 0.9
    # the scenarios say what they are about
    assert packs.scenario("kz.consumer.refund").classification.subject == ("goods",)
    assert "service" in packs.scenario("kz.consumer.service_refund").classification.subject


def test_a_goods_claim_for_a_service_is_not_given(ctx):
    """The first paid case's mistake: a service in the goods scenario (ЗПП ст. 30). The document waits for the owner
    with the reasons; nothing is downloadable."""
    _, _ = claim_text(ctx, facts={"goods_description": "токены ИИ-сервиса"})  # the goods path, as on 01.10
    with ctx.container.session_factory() as s:
        a = s.scalars(select(Action)).first()
        reasons = a.approval_note or ""
        assert a.approval_status == "pending" and reasons.startswith("Самопроверка")
        assert "D-19" in reasons and "товар" in reasons
        assert s.scalar(select(AuditLog.id).where(AuditLog.event == "legal_check_failed")) is not None
    row = ctx.client.get("/v1/admin/reviews", headers=ADMIN).json()[0]
    assert row["check_note"] == reasons


def test_a_clean_goods_claim_is_given(ctx):
    _, _ = claim_text(ctx, facts={"goods_description": "Смартфон Nova 9", "seller_address": "г. Алматы, пр. Достык, 10"}, email="someone.else@mail.kz")
    with ctx.container.session_factory() as s:
        a = s.scalars(select(Action)).first()
        assert not (a.approval_note or "").startswith("Самопроверка")


def test_rules_on_the_text():
    rules = {"no_applicant_id_in": ["x.consumer.refund.claim"], "goods_only_norms": ["«О защите прав потребителей», статья 30"], "goods_only_words": ["бракован"],
             "subject_words": {"service": ["токен"]}, "subject_names": {"service": "услуга"}}

    class P:  # a party
        id_field = "applicant_iin"

    class Sc:
        id = "x.consumer.refund"
        parties = {"applicant": P()}

        class classification:
            subject = ("goods",)

    class Spec:
        id = "claim"
        norm_refs = ("Закон «О защите прав потребителей», статья 30",)

        class addressee:
            party = "respondent"

    case = type("C", (), {"taxonomy": {}, "initial_text": "купил токены", "facts": {"applicant_iin": "900101300123"}})()
    text = ("Кому: Антропик\nИИН: 900101300123\nя приобрел(а) бракованный товар на 10 352 KZT\n"
            "Приложения:\n1. Чек (a.pdf)\n2. Чек (a.pdf)\n")
    found = " ".join(legal_check.check(case, Sc, Spec, text, {"kind": "business", "email": "me@mail.kz"}, rules, "KZT",
                                       {"me@mail.kz"}))
    for part in ("D-19", "нормы о товаре", "бракован", "D-18", "приобрел(а)", "KZT", "контактом клиента", "повторяющиеся"):
        assert part in found, part
