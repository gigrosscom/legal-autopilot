"""The consultant's interview: story → evidence (several files) → identity document → personal data → document."""

from tests.conftest import hide_scenarios
from tests.test_e2e import assert_no_pii_reached_llm, run_intake, web_user

REFUND = ("Купил смартфон в интернет-магазине 12.08.2026 за 150 000 тенге, через неделю он сломался, "
          "продавец отказывается вернуть деньги")
STORY = {"seller_name": "ТОО «Техномир»", "seller_bin": "пропустить", "goods_description": "Смартфон",
         "seller_email": "пропустить", "seller_address": "Алматы, пр. Абая 10"}


def _upload(api, cid, kind, name, body, ctype="text/plain"):
    up = api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": kind}, files={"file": (name, body, ctype)})
    return up, api.post(f"/v1/cases/{cid}/evidence/{up['evidence']['id']}/confirm", json={})


def test_documents_come_first_and_take_several_files(ctx):
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": REFUND, "country": "KZ"})
    cid = created["case"]["id"]
    assert created["reply"]["question"]["field"] == "evidence"  # documents before any other question
    _, first = _upload(api, cid, "receipt", "receipt.txt", "Кассовый чек".encode())
    _, second = _upload(api, cid, "receipt", "photo.txt", "Фото чека".encode())
    assert second["case"]["question"]["field"] == "evidence" and second["case"]["question"]["uploaded"] == 2
    api.answer(cid, "готово")
    body = api.get(f"/v1/cases/{cid}").json()
    while body["question"] and body["question"]["field"] in STORY:  # the story's questions
        body = api.answer(cid, STORY[body["question"]["field"]])["case"]
    # then personal data; no ID copy for a claim to a seller (lawyer 01.10, D-18)
    assert body["question"]["field"].startswith("applicant_")
    assert not any(f["field"].startswith("applicant_") for f in body["facts"])


def test_a_document_fills_the_case_and_is_not_asked_again(ctx):
    """What the uploaded contract shows (seller, BIN, date, amount) is never asked; a DOCX is read too."""
    import io

    from docx import Document

    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": REFUND, "country": "KZ"})["case"]["id"]
    doc = Document()
    doc.add_paragraph("Договор купли-продажи от 03.09.2026")
    doc.add_paragraph("Итого к оплате: 275000")
    buf = io.BytesIO()
    doc.save(buf)
    up = api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": "other"}, files={"file": (
        "договор.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert up["evidence"]["has_text"] is True
    assert up["evidence"]["kind"] != "other"  # filed under the scenario's document kinds by its content
    assert up["evidence"]["extracted_facts"]["amount"] == "275000.00"  # read from the DOCX
    asked = set()
    q = up["case"]["question"]
    out = api.answer(cid, "готово")
    q = out["case"]["question"]
    while q and q["type"] != "evidence" and len(asked) < 30:
        asked.add(q["field"])
        out = api.answer(cid, STORY.get(q["field"], "пропустить"))
        q = out["case"]["question"]
    assert not asked & set(up["evidence"]["extracted_facts"])


def test_identity_document_never_reaches_the_llm_and_fills_the_iin(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": REFUND, "country": "KZ"})["case"]["id"]
    body = api.answer(cid, "пропустить")["case"]  # no documents
    while body["question"] and body["question"]["field"] in STORY:
        body = api.answer(cid, STORY[body["question"]["field"]])["case"]
    calls = len(ctx.llm.calls)
    id_text = "УДОСТОВЕРЕНИЕ ЛИЧНОСТИ\nИВАНОВ ИВАН ИВАНОВИЧ\nИИН 900101300123\nМВД РК".encode()
    up, conf = _upload(api, cid, "id_document", "id.txt", id_text)
    assert len(ctx.llm.calls) == calls  # nothing about the ID went to the model
    assert up["evidence"]["extracted_facts"] == {"applicant_iin": "900101300123"}
    # the claim to a seller does not ask for the ID (D-18), but one uploaded anyway still fills the IIN, unread
    body = run_intake(api, cid, {"applicant_name": "Иванов Иван Иванович",
                                 "applicant_address": "Алматы, ул. Абая 1", "applicant_phone": "+7 701 123 45 67"})
    assert body["status"] == "qualified"  # the IIN question is not asked: it came from the ID
    a = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert a["approval_status"] == "not_required"
    assert_no_pii_reached_llm(ctx, "900101300123", "ИВАНОВ", "Иванов")


def _motion_case(api, text):
    created = api.post("/v1/cases", expect=201, json={"text": text, "country": "KZ"})
    cov = created["case"]["coverage"]  # the system's recipient and «Другой адресат» (owner 02.10)
    return created["case"]["id"], {o["id"] for o in cov["options"] + cov["other_forums"]}, created["case"]


ANSWERS = {"applicant_name": "Иванов Иван Иванович", "applicant_iin": "пропустить",
           "applicant_address": "Алматы, ул. Абая 1", "applicant_phone": "+7 701 123 45 67",
           "respondent_name": "УП Алмалинского района", "case_number": "пропустить", "event_date": "пропустить",
           "problem_description": "Заявление о краже подано месяц назад, проверка не идёт",
           "desired_outcome": "Допросить свидетелей и истребовать записи камер"}


def test_motion_to_the_police_is_self_service(ctx):
    api = web_user(ctx)
    cid, options, _ = _motion_case(api, "Следователь бездействует, полиция не принимает мер по моему заявлению")
    assert "kz.police.case" in options
    case = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.police.case"})["case"]
    q = case["question"]
    while q is not None:
        out = api.answer(cid, "пропустить" if q["type"] == "evidence" else ANSWERS[q["field"]])
        assert out["reply"]["error"] is None, out["reply"]
        q = out["case"]["question"]
    a = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert a["title"].startswith("Ходатайство")
    assert a["approval_status"] == "not_required" and a["downloadable"] is True


def test_motion_in_court_waits_for_a_lawyer(ctx):
    hide_scenarios(ctx, "kz.labor.")
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={
        "text": "Работодатель не платит зарплату три месяца, задолженность 450000 тенге", "country": "KZ"})
    cid = created["case"]["id"]
    assert "kz.court.pending" in {o["id"] for o in created["case"]["coverage"]["other_forums"]}  # never by the system
    case = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.court.pending"})["case"]
    answers = {**ANSWERS, "respondent_name": "ТОО «Ромашка»", "amount": "450000"}
    q = case["question"]
    while q is not None:
        out = api.answer(cid, "пропустить" if q["type"] == "evidence" else answers[q["field"]])
        q = out["case"]["question"]
    a = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert a["approval_status"] == "pending"  # court filings only after a lawyer's check


def test_solution_is_proposed_right_after_the_story(ctx):
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": REFUND, "country": "KZ"})["case"]
    plan = case["plan"]
    assert plan["document"] == "Претензия продавцу о возврате денег"
    assert {c["kind"] for c in plan["channels"]} >= {"in_person", "post"}
    assert "Чек или квитанция об оплате" in plan["attachments"]  # asked for up front
    assert "Копия удостоверения личности" not in plan["attachments"]  # lawyer 01.10, D-18: not needed here
    assert plan["lawyer_check"] is False


def test_universal_plan_names_the_portal_and_the_checklist(ctx):
    hide_scenarios(ctx, "kz.labor.")
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={
        "text": "Работодатель не платит зарплату три месяца, задолженность 450000 тенге", "country": "KZ"})
    case = api.post(f"/v1/cases/{created['case']['id']}/forum", json={"forum_id": "kz.labor_inspection"})["case"]
    plan = case["plan"]
    assert plan["document"].startswith("Жалоба")
    assert {"kind": "portal", "url": "https://eotinish.kz"} in plan["channels"]
    assert any("претензия" in a.lower() for a in plan["attachments"])
