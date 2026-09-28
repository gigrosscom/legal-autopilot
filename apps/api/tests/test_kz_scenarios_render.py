"""Every published KZ scenario goes from the story to its first document: DRAFT mark, no raw placeholders."""

from __future__ import annotations

import uuid

import pytest

from konsilier.core.documents import docx_text
from konsilier.core.models import Action
from konsilier.core.packs import load_pack

from .test_e2e import web_user
from .test_pilot_drafts import PACKS

KZ = load_pack(PACKS / "kz", PACKS)
PUBLISHED = sorted(s.id for s in KZ.scenarios.values() if s.published)
ANSWERS = {
    "respondent_name": "ТОО «Ромашка»", "seller_name": "ТОО «Ромашка»", "lender_name": "АО «Банк»",
    "seller_bin": "пропустить", "lender_bin": "пропустить", "seller_email": "пропустить", "lender_email": "пропустить",
    "contract_number": "пропустить", "police_report_number": "пропустить", "goods_description": "Товар",
    "event_date": "01.09.2026", "purchase_date": "01.09.2026", "loan_date": "01.09.2026", "amount": "100000",
    "problem_description": "Описание ситуации", "desired_outcome": "Вернуть деньги",
    "applicant_name": "Иванов Иван Иванович", "applicant_iin": "900101300128", "applicant_address": "Алматы, ул. Абая 1",
    "applicant_phone": "+7 701 123 45 67",
}


@pytest.mark.parametrize("sid", PUBLISHED)
def test_first_document_renders(ctx, sid):
    for pack in ctx.container.packs.packs.values():  # only the scenario under test is on offer
        for other, sc in list(pack.scenarios.items()):
            pack.scenarios[other] = sc.model_copy(update={"published": other == sid})
    sc = KZ.scenarios[sid]
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": sc.classification.examples["ru"][0], "country": "KZ"})
    case = created["case"]
    assert case["scenario"]["id"] == sid
    q = case["question"]
    while q is not None:
        answer = "пропустить" if q["type"] == "evidence" else ANSWERS[q["field"]]
        out = api.answer(case["id"], answer)
        assert out["reply"]["error"] is None, (q["field"], out["reply"])
        q = out["case"]["question"]
    action = api.post(f"/v1/cases/{case['id']}/actions/next")["case"]["actions"][0]
    assert action["instructions"] and not any("{" in s for s in action["instructions"]), action["instructions"]
    with ctx.container.session_factory() as s:
        text = docx_text(ctx.container.storage.get(s.get(Action, uuid.UUID(action["id"])).docx_key))
    assert "ЧЕРНОВИК" in text
    assert "{" not in text.replace("{{", "")
    for ref in sc.actions[0].norm_refs:
        if ref != "TODO":
            assert ref in text
