"""Every published KZ scenario, end to end: story → interview → EVERY document of its chain → hand-off to a lawyer.

The counterparty's / authority's answer is simulated at each step (refusal, no answer, partial answer), so the chain
branches the way it does for a real person. Each document is rendered to DOCX (and to PDF when LibreOffice is
installed) and checked for the requisites the law of Kazakhstan requires of that kind of document:

* any document: addressee, the applicant's full name, IIN, postal address and phone, the substance, what is asked,
  the list of attachments, the date and the signature line (АППК РК, ст. 63, п. 2 — обращение в госорган);
* a complaint to a state body about a company: who the complaint is about, with the address (Закон о ЗПП,
  ст. 42-5, п. 4) and copies of the earlier claim / answer among the attachments (ст. 42-5, п. 3; АППК, ст. 93);
* a lawsuit: the court, the plaintiff's date of birth, IIN, place of residence; the defendant and his place of
  residence; the claim value; pre-trial steps; copies for the defendant and the court fee among the attachments
  (ГПК РК, ст. 148, 149).

The LLM is the heuristic mock of the test suite; no paid calls.
"""

from __future__ import annotations

import re
import uuid

import pytest

from konsilier.core.documents import LibreOfficeConverter, docx_text
from konsilier.core.models import Action
from konsilier.core.packs import load_pack

from .test_e2e import admin_approve, web_user
from .test_pilot_drafts import PACKS

KZ = load_pack(PACKS / "kz", PACKS)
PUBLISHED = sorted(s.id for s in KZ.scenarios.values() if s.published)
VERIFIED_ACTS = {a.title["ru"] for s in KZ.manifest.legal_sources for a in s.key_acts if a.verified_on}

NAME, IIN, ADDRESS, PHONE = "Иванов Иван Иванович", "900101300128", "г. Алматы, ул. Абая, д. 1, кв. 2", "+77011234567"
RESP_NAME, RESP_ADDRESS, RESP_BIN = "ТОО «Ромашка»", "г. Алматы, пр. Достык, д. 10", "123456789012"
ANSWERS = {
    "respondent_name": RESP_NAME, "seller_name": RESP_NAME, "lender_name": RESP_NAME,
    "respondent_address": RESP_ADDRESS, "seller_address": RESP_ADDRESS, "lender_address": RESP_ADDRESS,
    "respondent_bin": RESP_BIN, "seller_bin": RESP_BIN, "lender_bin": RESP_BIN, "respondent_iin": "пропустить",
    "seller_email": "пропустить", "lender_email": "пропустить", "respondent_email": "пропустить",
    "applicant_email": "ivanov@example.kz",
    "appeal_date": "01.08.2026", "appeal_number": "пропустить", "appeal_subject": "Ремонт дороги",
    "higher_authority": "пропустить",
    "contract_number": "ZF-2026/001", "police_report_number": "пропустить", "goods_description": "Смартфон Nova 9",
    "decision_number": "№ 123456 от 01.09.2026",
    "event_date": "01.09.2026", "purchase_date": "01.09.2026", "loan_date": "01.09.2026", "amount": "150000",
    "problem_description": "Описание ситуации", "desired_outcome": "Вернуть деньги",
    "children_info": "Иванова Алия Ивановна, 01.02.2018",
    "applicant_name": NAME, "applicant_iin": IIN, "applicant_address": ADDRESS, "applicant_phone": PHONE,
    "applicant_birth_date": "01.01.1990", "identity_document": "пропустить",
}
# the simulated answer to each step in turn: the chain must go on after each of them
RESPONSES = ("refusal", "none", "partial")
TITLE_WORDS = ("ПРЕТЕНЗИЯ", "ЖАЛОБА", "ЗАЯВЛЕНИЕ", "ИСКОВОЕ ЗАЯВЛЕНИЕ")
PDF = LibreOfficeConverter("soffice")


def _only(ctx, sid: str) -> None:
    for pack in ctx.container.packs.packs.values():  # only the scenario under test is on offer
        for other, sc in list(pack.scenarios.items()):
            pack.scenarios[other] = sc.model_copy(update={"published": other == sid})


def _interview(ctx, api, sid: str) -> str:
    sc = KZ.scenarios[sid]
    created = api.post("/v1/cases", expect=201, json={"text": sc.classification.examples["ru"][0], "country": "KZ"})
    case = created["case"]
    assert case["scenario"]["id"] == sid
    cid, q = case["id"], case["question"]
    guard = 0
    while q is not None:
        guard += 1
        assert guard < 40, q
        if q["type"] == "evidence" and q["field"] != "identity_document":
            if not q.get("uploaded"):  # one file of the first kind the scenario asks for, then "done"
                kind = q["evidence_kinds"][0]["kind"]
                up = api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": kind},
                              files={"file": ("dokument.txt", "Доказательство".encode(), "text/plain")})
                out = api.post(f"/v1/cases/{cid}/evidence/{up['evidence']['id']}/confirm", json={})
                q = out["case"]["question"]
                continue
            answer = "готово"
        else:
            assert q["field"] in ANSWERS, f"{sid}: no test answer for {q['field']}"
            answer = ANSWERS[q["field"]]
        out = api.answer(cid, answer)
        assert out["reply"]["error"] is None, (sid, q["field"], out["reply"])
        q = out["case"]["question"]
    return cid


def _check_document(sid: str, spec, a: dict, text: str, previous: list[str]) -> None:
    where = f"{sid}.{spec.id}"
    t = text.replace("\xa0", " ")
    # nothing left unfilled
    assert "{" not in t and "}" not in t, (where, t)
    assert "None" not in t and "TODO" not in t, (where, t)
    assert not re.search(r"^\s*(Кому|От|ИИН|БИН|Адрес|Тел\.|Ответчик):\s*$", t, re.M), (where, t)
    # addressee — the exact name of the body / organisation
    assert a["addressee"]["name"] and f"Кому: {a['addressee']['name']}" in t, where
    # applicant (АППК ст. 63 п. 2 пп. 1); ГПК ст. 148 ч. 2 пп. 2))
    # the lawyer's D-18: the ИИН only where the law asks for it (a state body, a court, a bank) — not in a claim to a
    # company or a person, and never asked when the scenario does not need it
    for req in (f"От: {NAME}", f"Адрес: {ADDRESS}", f"Тел.: {PHONE}"):
        assert req in t, (where, req)
    if where in ("kz.consumer.refund.claim_to_seller", "kz.consumer.service_refund.claim_to_provider"):
        assert IIN not in t, (where, "ИИН in a claim to a seller")  # the lawyer's D-18 for these claims
    assert any(w in t for w in TITLE_WORDS), where
    # substance, what is asked, legal basis
    assert "Описание ситуации" in t or "ситуац" in t.lower() or len(t) > 400, where
    demand_intro = re.search(r"^(На основании изложенного (прошу|требую)( суд)?|Прошу):\n(.+)$", t, re.M)
    assert demand_intro and len(demand_intro.group(4).strip()) > 20, (where, t)
    for ref in spec.norm_refs:
        if ref != "TODO":
            assert ref.rsplit(", статья", 1)[0] in VERIFIED_ACTS, (where, ref)
            assert ref in t, (where, ref)
        else:
            assert "[норма" in t, where
    # attachments: the uploaded file and, from the second step on, the earlier documents
    assert "Приложение:" in t and "(dokument.txt)" in t, where  # D-30
    for title in previous:
        assert f"Копия документа «{title}»" in t, (where, title)
    # date and signature
    # D-29: the date in words on the left, «И. Фамилия» on the right
    assert re.search(r"\d{1,2} [а-я]+ \d{4} года\t______________ И\. Иванов", t), where

    kind = a["addressee"].get("type") or a["addressee"]["kind"]
    if kind == "court":  # ГПК РК ст. 148, 149
        for req in ("ИСКОВОЕ ЗАЯВЛЕНИЕ", "Дата рождения: 01.01.1990", f"Ответчик: {RESP_NAME}",
                    f"Место жительства: {RESP_ADDRESS}", "Цена иска:", "E-mail: ivanov@example.kz",
                    "по числу ответчиков", "государственной пошлины", "Иванова Алия Ивановна, 01.02.2018"):
            assert req in t, (where, req)
    elif spec.addressee.party and KZ.scenarios[sid].parties["respondent"].kind == "authority":
        # КоАП РК ст. 826-2 п. 5, ст. 833: which decision is appealed, the appellant's address, a clear request
        has_decision = any(f.name == "decision_number" for f in KZ.scenarios[sid].intake)
        assert (not has_decision or "№ 123456 от 01.09.2026" in t) and a["addressee"]["name"] == RESP_NAME, where
    elif spec.addressee.party:  # to the other party itself
        assert a["addressee"]["name"] == RESP_NAME, where
    else:  # a complaint to a state body about the other party: who it is about, with requisites
        assert f"{RESP_NAME}, БИН {RESP_BIN}, адрес: {RESP_ADDRESS}" in t, where


@pytest.mark.parametrize("sid", PUBLISHED)
def test_every_document_of_the_chain(ctx, sid):
    if PDF.available():  # real PDF, as in production (LibreOffice headless)
        ctx.container.engine.pdf = PDF
    _only(ctx, sid)
    sc = KZ.scenarios[sid]
    api = web_user(ctx)
    cid = _interview(ctx, api, sid)

    documents: list[str] = []
    previous: list[str] = []
    step = 0
    while True:
        case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
        a = case["actions"][-1]
        spec = sc.action(a["action_id"])
        if a["kind"] == "handoff":
            assert case["status"] == "handed_to_lawyer", sid
            break
        documents.append(spec.id)
        if spec.addressee.forum and KZ.coverage.forums[spec.addressee.forum].type == "court":
            # a lawsuit is filed only after a lawyer's check — never weakened
            assert a["approval_status"] == "pending", (sid, spec.id)
            api.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=docx", expect=409)
        if a["approval_status"] == "pending":
            admin_approve(ctx, a["id"])
        assert a["instructions"], (sid, spec.id)
        for line in a["instructions"]:
            assert "{" not in line and "  " not in line and "()" not in line, (sid, spec.id, line)

        docx = api.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=docx").content
        _check_document(sid, spec, a, docx_text(docx), previous)
        with ctx.container.session_factory() as s:
            row = s.get(Action, uuid.UUID(a["id"]))
            if PDF.available():
                assert row.pdf_key, (sid, spec.id, "PDF was not produced")
                pdf = api.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=pdf").content
                assert pdf.startswith(b"%PDF") and re.search(rb"/Type\s*/Page\b", pdf), (sid, spec.id)

        sub = api.post(f"/v1/cases/{cid}/actions/{a['id']}/submitted", json={})
        assert sub["case"]["status"] == "awaiting_response"
        if spec.deadline:
            assert sub["case"]["actions"][-1]["deadline"]["due_date"], (sid, spec.id)
        rc = RESPONSES[step % len(RESPONSES)]
        resp = api.post(f"/v1/cases/{cid}/actions/{a['id']}/response", json={"response_class": rc})
        assert resp["proposal"]["type"] in ("prepare_action", "handoff"), (sid, spec.id, rc, resp["proposal"])
        previous.append(KZ.localized(spec.title, "ru"))
        step += 1

    expected = [x.id for x in sc.actions if x.kind == "document"]
    assert documents == expected, (sid, documents, expected)


@pytest.mark.parametrize("sid", PUBLISHED)
def test_full_answer_closes_the_case(ctx, sid):
    """The other branch: the first document is satisfied in full → the case is closed as won, no escalation."""
    _only(ctx, sid)
    api = web_user(ctx)
    cid = _interview(ctx, api, sid)
    a = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    if a["approval_status"] == "pending":
        admin_approve(ctx, a["id"])
    api.post(f"/v1/cases/{cid}/actions/{a['id']}/submitted", json={})
    resp = api.post(f"/v1/cases/{cid}/actions/{a['id']}/response", json={"response_class": "full"})
    assert resp["proposal"]["type"] == "close" and resp["proposal"]["suggested_result"] == "won", sid
    api.post(f"/v1/cases/{cid}/actions/next", expect=409)
    closed = api.post(f"/v1/cases/{cid}/close", json={"result": "won"})
    assert closed["case"]["status"] == "resolved"
