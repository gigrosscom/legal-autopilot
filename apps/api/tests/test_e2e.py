"""End-to-end: both KZ scenarios through the HTTP API with a mocked LLM.

intake → evidence → document (+ lawyer approval) → submitted → deadline & reminders
→ counterparty response → escalation → hand-off / close with Outcome.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from konsilier.core.documents import docx_text
from konsilier.core.models import AuditLog, Case, Deadline, Outcome

from .test_pilot_drafts import AI_LINE_RU

ADMIN = {"X-Admin-Token": "adm"}


class Api:
    def __init__(self, ctx, token: str):
        self.ctx = ctx
        self.c = ctx.client
        self.h = {"Authorization": f"Bearer {token}"}

    def post(self, url: str, expect: int = 200, **kw):
        r = self.c.post(url, headers=self.h, **kw)
        assert r.status_code == expect, (url, r.status_code, r.text)
        return r.json()

    def get(self, url: str, expect: int = 200):
        r = self.c.get(url, headers=self.h)
        assert r.status_code == expect, (url, r.status_code, r.text)
        return r

    def answer(self, case_id: str, text: str) -> dict:
        return self.post(f"/v1/cases/{case_id}/messages", json={"text": text})


def web_user(ctx) -> Api:
    r = ctx.client.post("/v1/users", json={"language": "ru"})
    return Api(ctx, r.json()["token"])


def telegram_user(ctx, tg_id: str = "555001") -> Api:
    r = ctx.client.post("/v1/users/telegram", json={"telegram_id": tg_id}, headers={"X-Bot-Secret": "bot"})
    assert r.status_code == 200
    return Api(ctx, r.json()["token"])


def admin_approve(ctx, action_id: str):
    r = ctx.client.post(f"/v1/admin/actions/{action_id}/approval", headers=ADMIN,
                        json={"approved": True, "reviewer": "lawyer:kz-01"})
    assert r.status_code == 200, r.text
    return r.json()


def assert_no_pii_reached_llm(ctx, *secrets: str):
    assert ctx.llm.calls, "LLM was never called"
    for call in ctx.llm.calls:
        for s in secrets:
            assert s not in call["user"], (call["task"], s)


def statuses(ctx, case_id: str) -> list[str]:
    import uuid

    with ctx.container.session_factory() as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.case_id == uuid.UUID(case_id),
                                                AuditLog.event == "status_changed").order_by(AuditLog.id))
        return [r.to_status for r in rows]


def run_intake(api: Api, case_id: str, answers: dict[str, str], first_question: str | None = None) -> dict:
    """Answer questions in whatever order the engine asks them."""
    body = api.get(f"/v1/cases/{case_id}").json()
    q = body["question"]
    guard = 0
    # evidence questions are answered only when the test says so ("пропустить" / "готово"), else we stop there
    while q is not None and (q["type"] != "evidence" or q["field"] in answers):
        guard += 1
        assert guard < 30
        assert q["field"] in answers, f"unexpected question {q['field']}"
        out = api.answer(case_id, answers[q["field"]])
        assert out["reply"]["error"] is None, out["reply"]
        q = out["case"]["question"]
    return api.get(f"/v1/cases/{case_id}").json()


def tick_at(ctx, day: date) -> int:
    return ctx.container.scheduler.tick(datetime(day.year, day.month, day.day, 9, 0, tzinfo=timezone.utc))


# ======================================================================
def test_consumer_refund_full_path(ctx):
    ctx.container.engine.config.self_service = False  # the lawyer-review policy (SELF_SERVICE=false)
    api = web_user(ctx)
    story = ("Купил смартфон в интернет-магазине 12.08.2026 за 150 000 тенге, через неделю он сломался, "
             "продавец отказывается вернуть деньги")
    created = api.post("/v1/cases", expect=201, json={"text": story, "country": "KZ"})
    case = created["case"]
    cid = case["id"]
    assert case["scenario"]["id"] == "kz.consumer.refund"
    assert case["scenario"]["draft"] is True
    assert case["needs_review"] is False
    assert case["ai_label"].startswith("Подготовлено с помощью ИИ")
    # facts from the free story were pre-filled, interviewer asks only for the rest
    facts = {f["field"]: f["value"] for f in case["facts"]}
    assert facts["purchase_date"] == "12.08.2026"
    assert facts["amount"] == "150 000"
    # order: documents → what happened → personal data
    assert created["reply"]["question"]["field"] == "evidence"
    assert created["case"]["status"] == "intake"

    # a document is read at once: what it shows goes into the case, no confirmation step; more files may follow
    receipt = "ТОО Техномир\nКассовый чек от 12.08.2026\nСмартфон Nova 9\nИТОГО: 150000"
    up = api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": "receipt"},
                  files={"file": ("receipt.txt", receipt.encode(), "text/plain")})
    assert up["evidence"]["extracted_facts"] == {"purchase_date": "2026-08-12", "amount": "150000.00"}
    assert up["evidence"]["applied"] is True
    assert up["case"]["question"]["field"] == "evidence" and up["case"]["question"]["uploaded"] == 1
    assert up["reply"]["message"].startswith("Прочитал документ «receipt.txt». Взял из него:")
    out = api.answer(cid, "готово")
    assert out["case"]["question"]["field"] == "seller_name"

    # «пропустить» on a required answer: a blank for the draft, never asked again (QA BUG-08, PM 01.10)
    out = api.answer(cid, "пропустить")
    assert "черновике" in out["reply"]["message"] and out["case"]["question"]["field"] != "seller_name"
    body = run_intake(api, cid, {  # no ID copy is asked for a claim to a seller (lawyer 01.10, D-18)
        "seller_bin": "123456789012",
        "goods_description": "Смартфон Nova 9",
        "seller_email": "пропустить",
        "seller_address": "г. Алматы, пр. Достык, 10",
        "applicant_name": "Иванов Иван Иванович",
        "applicant_address": "г. Алматы, ул. Абая, 1", "applicant_phone": "+7 701 123 45 67",
        "applicant_iin": "900101300123"})
    # the draft shows the blank in brackets; the person fills it there
    draft = api.get(f"/v1/cases/{cid}/draft").json()
    assert [b["field"] for b in draft["blanks"]] == ["seller_name"] and draft["paid"] is False and draft["hidden"]
    assert "[" in draft["visible"] + draft["hidden"]
    r = ctx.client.post(f"/v1/cases/{cid}/facts", headers=api.h, json={"values": {"seller_bin": "12"}})
    assert r.status_code == 422 and r.json()["detail"]["fields"] == {"seller_bin": "pattern"}
    api.post(f"/v1/cases/{cid}/facts", json={"values": {"seller_name": "ТОО «Техномир»"}})
    assert api.get(f"/v1/cases/{cid}/draft").json()["blanks"] == []
    body = api.get(f"/v1/cases/{cid}").json()
    assert body["status"] == "qualified"
    assert body["proposal"]["type"] == "prepare_action"

    # document #1 — first N cases need lawyer approval
    prep = api.post(f"/v1/cases/{cid}/actions/next")
    case = prep["case"]
    assert case["status"] == "action_ready"
    a1 = case["actions"][0]
    assert a1["action_id"] == "claim_to_seller" and a1["approval_status"] == "pending"
    assert a1["addressee"]["name"] == "ТОО «Техномир»"
    assert any("Техномир" in s for s in a1["instructions"])
    api.get(f"/v1/cases/{cid}/actions/{a1['id']}/document?format=docx", expect=409)
    api.post(f"/v1/cases/{cid}/actions/{a1['id']}/submitted", expect=409, json={})

    admin_list = ctx.client.get("/v1/admin/cases?pending_approval=true", headers=ADMIN).json()
    assert [c["id"] for c in admin_list] == [cid]
    preview = ctx.client.get(f"/v1/admin/actions/{a1['id']}/preview", headers=ADMIN).json()["text"]
    assert "ПРЕТЕНЗИЯ" in preview
    admin_approve(ctx, a1["id"])

    docx = api.get(f"/v1/cases/{cid}/actions/{a1['id']}/document?format=docx").content
    text = docx_text(docx)
    for expected in ("ПРЕТЕНЗИЯ", "ТОО «Техномир»", "БИН: 123456789012", "Иванов Иван Иванович",
                     "150 000", "Смартфон Nova 9", "Подготовлено с помощью ИИ",
                     AI_LINE_RU, "Закон Республики Казахстан «О защите прав потребителей», статьи 30 и 42-4",
                     "Адрес: г. Алматы, пр. Достык, 10", "Адрес: г. Алматы, ул. Абая, 1",
                     "1. Чек или квитанция об оплате (receipt.txt)"):
        assert expected in text.replace(" ", " "), expected
    assert_no_pii_reached_llm(ctx, "Иванов", "900101300123", "701 123 45 67")

    # submitted → deadline (10 calendar days) → reminders at D-2 and D-0
    sub = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/submitted", json={"via": "user_submits"})
    assert sub["case"]["status"] == "awaiting_response"
    dl = sub["case"]["actions"][0]["deadline"]
    due = date.fromisoformat(dl["due_date"])
    submitted_day = datetime.fromisoformat(sub["case"]["actions"][0]["submitted_at"]).astimezone(
        ctx.container.packs.pack("KZ").tz).date()
    assert due == submitted_day + timedelta(days=10)
    assert tick_at(ctx, due - timedelta(days=3)) == 0
    assert tick_at(ctx, due - timedelta(days=2)) == 1
    assert tick_at(ctx, due - timedelta(days=2)) == 0  # idempotent
    assert tick_at(ctx, due) == 1
    sent = [t for _, t in ctx.channels["web"].sent]
    assert any("осталось 2 дн." in t for t in sent)
    assert any("последний день" in t for t in sent)
    inbox = api.get("/v1/notifications").json()["items"]
    assert any(n["kind"] == "deadline_reminder" for n in inbox)

    # counterparty refuses → engine proposes the next step from YAML
    resp = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/response",
                    json={"text": "В удовлетворении претензии отказано: товар исправен."})
    assert resp["proposal"]["type"] == "prepare_action"
    assert resp["proposal"]["action_id"] == "complaint_consumer_authority"
    assert resp["case"]["actions"][0]["response_class"] == "refusal"
    assert resp["case"]["actions"][0]["deadline"]["status"] == "met"

    # escalation: complaint to the consumer authority (eOtinish instructions)
    prep = api.post(f"/v1/cases/{cid}/actions/next")
    a2 = prep["case"]["actions"][1]
    assert a2["action_id"] == "complaint_consumer_authority"
    assert a2["addressee"]["kind"] == "authority"
    assert any("eotinish.kz" in s for s in a2["instructions"])
    assert a2["email_allowed"] is False
    api.post(f"/v1/cases/{cid}/actions/{a2['id']}/submitted", expect=409, json={"via": "email"})
    admin_approve(ctx, a2["id"])
    text2 = docx_text(api.get(f"/v1/cases/{cid}/actions/{a2['id']}/document?format=docx").content)
    assert "ЖАЛОБА" in text2 and "Ранее предпринятые действия" in text2 and "Отказ" in text2
    sub2 = api.post(f"/v1/cases/{cid}/actions/{a2['id']}/submitted", json={})
    # no response deadline for the authority: 15 working days are not in the consumer law (lawyer, 01.10) — only a
    # lawyer adds one; the 2-month limit to complain is in the instructions (ЗПП ст. 42-5 п. 2)
    assert sub2["case"]["actions"][1]["deadline"] is None
    assert any("двух месяцев" in s for s in a2["instructions"])

    # no answer from the authority → hand-off to a lawyer
    resp2 = api.post(f"/v1/cases/{cid}/actions/{a2['id']}/response", json={"no_response": True})
    assert resp2["proposal"]["type"] == "handoff"
    ho = api.post(f"/v1/cases/{cid}/actions/next")
    assert ho["case"]["status"] == "handed_to_lawyer"

    # lawyer closes the case → Outcome is filled
    r = ctx.client.post(f"/v1/admin/cases/{cid}/close", headers=ADMIN,
                        json={"result": "partial", "amount_recovered": "75000", "comment": "settled in court"})
    assert r.status_code == 200, r.text
    final = r.json()
    assert final["status"] == "resolved"
    assert final["outcome"]["result"] == "partial"
    assert final["outcome"]["amount_recovered"] == "75000.00"
    assert final["outcome"]["resolved_at_step"] == "handoff_lawyer"
    assert final["outcome"]["days_to_resolution"] >= 0

    assert statuses(ctx, cid) == ["qualified", "action_ready", "submitted", "awaiting_response", "escalated",
                                  "action_ready", "submitted", "awaiting_response", "escalated",
                                  "handed_to_lawyer", "resolved"]
    with ctx.container.session_factory() as s:
        c = s.get(Case, __import__("uuid").UUID(cid))
        assert {p.role for p in c.parties} == {"applicant", "respondent"}
        assert c.claims[0].type == "refund" and str(c.claims[0].amount) == "150000.00"
        assert s.scalar(select(Outcome).where(Outcome.case_id == c.id)).scenario_version == "0.1.0"
        assert s.scalars(select(Deadline).where(Deadline.case_id == c.id, Deadline.status == "active")).all() == []


def test_credit_fraud_via_telegram_full_path(ctx):
    ctx.container.engine.config.self_service = False  # the lawyer-review policy (SELF_SERVICE=false)
    api = telegram_user(ctx)
    story = "Мне пришло SMS, что на меня оформлен займ в МФО на 300000 тенге 01.09.2026, я его не брал, это мошенники"
    created = api.post("/v1/cases", expect=201, json={"text": story})  # country inferred from scenario
    case = created["case"]
    cid = case["id"]
    assert case["scenario"]["id"] == "kz.money.credit_fraud"
    assert case["jurisdiction"] == "KZ"

    body = run_intake(api, cid, {
        "evidence": "пропустить",  # evidence is optional: user skips
        "identity_document": "пропустить",
        "lender_name": "ТОО МФО «Быстрые деньги»",
        "lender_bin": "пропустить",
        "contract_number": "ZF-2026/001",
        "police_report_number": "КУИ № 2026-555 от 03.09.2026",
        "applicant_name": "Сейтказиева Айгерим Болатовна",
        "applicant_iin": "950505400789",
        "applicant_address": "г. Астана, ул. Кенесары, 5",
        "applicant_phone": "+7 777 000 11 22",
        "lender_address": "пропустить",
        "lender_email": "support@fastmoney.example",
    })
    assert body["status"] == "qualified"

    prep = api.post(f"/v1/cases/{cid}/actions/next")
    a1 = prep["case"]["actions"][0]
    assert a1["action_id"] == "statement_to_lender" and a1["email_allowed"] is True
    admin_approve(ctx, a1["id"])
    text = docx_text(api.get(f"/v1/cases/{cid}/actions/{a1['id']}/document?format=docx").content)
    for expected in ("ЗАЯВЛЕНИЕ", "ТОО МФО «Быстрые деньги»", "ZF-2026/001", "КУИ № 2026-555",
                     "Сейтказиева Айгерим Болатовна", "ИИН: 950505400789", "300 000",
                     "Подготовлено с помощью ИИ"):
        assert expected in text.replace(" ", " "), expected
    assert_no_pii_reached_llm(ctx, "Сейтказиева", "950505400789", "777 000 11 22")
    # telegram user was notified about the approval through the Telegram adapter
    assert any("Документ проверен" in t for _, t in ctx.channels["telegram"].sent)

    sub = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/submitted", json={})
    due = date.fromisoformat(sub["case"]["actions"][0]["deadline"]["due_date"])
    assert tick_at(ctx, due + timedelta(days=1)) == 1  # expired notice
    assert any("истёк" in t for _, t in ctx.channels["telegram"].sent)

    # partial answer → escalate to the regulator (ARDFM)
    resp = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/response",
                    json={"text": "Мы частично согласны: начисление вознаграждения приостановлено."})
    assert resp["case"]["actions"][0]["response_class"] == "partial"
    assert resp["proposal"]["action_id"] == "complaint_arrf"
    prep2 = api.post(f"/v1/cases/{cid}/actions/next")
    a2 = prep2["case"]["actions"][1]
    assert "АРРФР" in a2["addressee"]["name"]
    admin_approve(ctx, a2["id"])
    api.post(f"/v1/cases/{cid}/actions/{a2['id']}/submitted", json={})

    # unclear answer → user must clarify; then full → close with Outcome
    resp2 = api.post(f"/v1/cases/{cid}/actions/{a2['id']}/response", json={"text": "Ваше обращение получено."})
    assert resp2["proposal"]["type"] == "clarify"
    api.post(f"/v1/cases/{cid}/actions/next", expect=409)
    # the user clarifies by picking the class explicitly (buttons in web/bot)
    resp3 = api.post(f"/v1/cases/{cid}/actions/{a2['id']}/response", json={"response_class": "full"})
    assert resp3["proposal"]["type"] == "close" and resp3["proposal"]["suggested_result"] == "won"
    closed = api.post(f"/v1/cases/{cid}/close", json={"result": "won", "amount_recovered": "300000"})
    assert closed["case"]["status"] == "resolved"
    assert closed["case"]["outcome"]["result"] == "won"
    assert closed["case"]["outcome"]["resolved_at_step"] == "complaint_arrf"
    assert statuses(ctx, cid)[-1] == "resolved"


def test_low_confidence_goes_to_needs_review_and_forces_approval(ctx):
    ctx.settings.approval_required_first_n = 0
    ctx.container.engine.config.approval_required_first_n = 0
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": "Проблема с товаром", "country": "KZ"})
    assert created["case"]["needs_review"] is True  # 1 keyword → confidence below threshold
    only_review = ctx.client.get("/v1/admin/cases?needs_review=true", headers=ADMIN).json()
    assert [c["id"] for c in only_review] == [created["case"]["id"]]


def test_unknown_problem_is_not_qualified(ctx):
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": "Сосед шумит по ночам", "country": "KZ"})
    assert created["case"]["scenario"] is None
    assert created["case"]["needs_review"] is True
    assert "не хватает деталей" in created["reply"]["message"]


def test_colloquial_follow_up_qualifies_and_explains_next_steps(ctx):
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": "Всё плохо, помогите", "country": "KZ"})
    cid = created["case"]["id"]
    assert created["case"]["scenario"] is None
    assert created["case"]["coverage"]["level"] == "pending"  # never "verified" before classification
    out = api.answer(cid, "купил макбук в технодоме, не понравилось, хочу вернуть - как это сделать?")
    assert out["case"]["scenario"]["id"] == "kz.consumer.refund"
    assert "Претензия продавцу о возврате денег" in out["reply"]["message"]  # what happens next
    assert out["case"]["question"] is not None


def test_approval_not_required_after_first_n(ctx):
    ctx.container.engine.config.approval_required_first_n = 0
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={
        "text": "Заказал шкаф на маркетплейсе 01.09.2026 за 90000, не доставили, хочу вернуть деньги",
        "country": "KZ"})["case"]["id"]
    run_intake(api, cid, {"seller_name": "ИП Мебель", "seller_bin": "пропустить", "goods_description": "Шкаф",
                          "applicant_name": "Петров Пётр", "applicant_phone": "+7 700 000 00 00",
                          "applicant_iin": "пропустить", "seller_email": "пропустить",
                          "seller_address": "Алматы, ул. Мебельная 1", "applicant_address": "Алматы, ул. Абая 1",
                          "evidence": "пропустить", "identity_document": "пропустить"})
    a = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert a["approval_status"] == "not_required" and a["status"] == "ready"
    api.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=docx")


def test_other_users_cannot_see_case(ctx):
    alice, bob = web_user(ctx), web_user(ctx)
    cid = alice.post("/v1/cases", expect=201, json={"text": "Хочу вернуть деньги за товар", "country": "KZ"})["case"]["id"]
    bob.get(f"/v1/cases/{cid}", expect=404)
    assert ctx.client.get(f"/v1/cases/{cid}").status_code == 401


def test_packs_and_waitlist(ctx):
    packs = ctx.client.get("/v1/packs").json()
    assert [p["country"] for p in packs] == ["KZ"]  # test packs are hidden
    assert {s["id"] for s in packs[0]["scenarios"] if not s["beta"]} == {  # beta: test_beta_scenarios.py
        "kz.consumer.refund", "kz.money.credit_fraud", "kz.labor.unpaid_wages", "kz.administrative.fine_appeal",
        "kz.gov.inaction_complaint",
        "kz.family.alimony", "kz.consumer.non_delivery", "kz.consumer.poor_service", "kz.consumer.air_ticket",
        "kz.consumer.paid_medical", "kz.consumer.education_refund", "kz.consumer.service_refund", "kz.labor.final_settlement", "kz.labor.dismissal",
        "kz.housing.deposit_return", "kz.housing.management_company", "kz.housing.utility_billing",
        "kz.finance.debt_collectors", "kz.finance.imposed_insurance", "kz.finance.loan_restructuring",
        "kz.finance.unauthorized_debit", "kz.civil.road_accident"}
    r = ctx.client.post("/v1/waitlist", json={"country": "uz", "contact": "@someone", "problem": "долг"})
    assert r.status_code == 201
    rows = ctx.client.get("/v1/admin/waitlist", headers=ADMIN).json()
    assert rows[0]["country"] == "UZ"
    assert ctx.client.get("/v1/admin/waitlist").status_code == 403


def test_lawyer_application_with_referral(ctx):
    first = ctx.client.post("/v1/lawyer-applications", json={
        "country": "kz", "full_name": "Адвокат Первый", "kind": "advocate", "license_number": "12345",
        "city": "Алматы", "phone": "+77010000000", "consent": True, "specializations": ["consumer"]})
    assert first.status_code == 201, first.text
    code = first.json()["referral_code"]
    second = ctx.client.post("/v1/lawyer-applications", json={
        "country": "KZ", "full_name": "Коллега Второй", "kind": "legal_consultant", "license_number": "ПЮК-123",
        "city": "Астана", "phone": "8 707 111 22 33", "consent": True,
        "referred_by": code.lower(), "wants_expert": True})
    assert second.status_code == 201
    rows = ctx.client.get("/v1/admin/lawyer-applications", headers=ADMIN).json()
    by_name = {r["full_name"]: r for r in rows}
    assert by_name["Коллега Второй"]["referred_by"] == code
    assert by_name["Адвокат Первый"]["invited"] == 1
    assert by_name["Коллега Второй"]["wants_expert"] is True and by_name["Адвокат Первый"]["wants_expert"] is False
    bad = ctx.client.post("/v1/lawyer-applications", json={"country": "KZ", "full_name": "X Y Z", "kind": "wizard",
                                                            "contact": "abc"})
    assert bad.status_code == 422


def test_client_errors_are_stored_for_admin(ctx):
    r = ctx.client.post("/v1/client-errors", json={"message": "NotFoundError: removeChild", "stack": "at x",
                                                   "url": "/case/1", "translated": False})
    assert r.status_code == 204
    rows = ctx.client.get("/v1/admin/client-errors", headers=ADMIN).json()
    assert rows[0]["message"] == "NotFoundError: removeChild" and rows[0]["url"] == "/case/1"
    assert ctx.client.get("/v1/admin/client-errors").status_code in (401, 403)


def test_postal_address_is_checked_softly():
    # QA BUG-10: a company name or a BIN given as a party's postal address is asked again; ordinary addresses pass
    from konsilier.core.fields import looks_like_address
    for ok in ("г. Алматы, пр. Достык, 10", "Астана, ул. Кенесары 40, кв. 12", "050000, Алматы, Абая 1"):
        assert looks_like_address(ok)
    for bad in ("ТОО «Тест-Компания», БИН 123456789012", "Алматы", "магазин Технодом"):
        assert not looks_like_address(bad)
