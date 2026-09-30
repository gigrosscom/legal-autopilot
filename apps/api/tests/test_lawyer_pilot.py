"""«Юрист по кнопке» (closed pilot): request → the lawyer accepts → the client pays the lawyer's price to the
company's account (15 % commission) → the lawyer is assigned and gets the dossier. Documents stay unpaid."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from konsilier.core.models import Case, Invoice, Notification

from .test_e2e import web_user
from .test_lawyer_agreements import LAWYER_IIN, Verifier, ecp_login

ADM = {"X-Admin-Token": "adm"}
CONTACT = {"full_name": "Асем Серикова", "phone": "+7 701 234 56 78", "consent": True}


def lawyer_account(ctx, iin: str, name: str, phone: str):
    api = web_user(ctx)
    ecp_login(ctx, api, iin)
    app = api.post("/v1/lawyer-applications", expect=201, json={
        "country": "KZ", "full_name": name, "kind": "advocate", "license_number": "12345", "city": "Алматы",
        "phone": phone, "email": f"{iin}@lawyer.kz", "consent": True})
    r = ctx.client.post(f"/v1/admin/lawyer-applications/{app['id']}/status", headers=ADM, json={"status": "verified"})
    assert r.status_code == 200, r.text
    return api, app["id"]


def set_pilot(ctx, app_id: int, **body):
    r = ctx.client.post(f"/v1/admin/lawyer-applications/{app_id}/pilot", headers=ADM, json=body)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def world(ctx):
    ctx.container.signature_verifier = Verifier()
    ctx.container.engine.config.lawyer_pay_link = "https://pay.kaspi.kz/pay/konsilier"
    ctx.container.engine.config.company_name = "ТОО «Konsilier AI»"
    customer = web_user(ctx)
    cid = customer.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине, через неделю сломался, деньги не возвращают 150000",
        "country": "KZ"})["case"]["id"]
    lawyer, app_id = lawyer_account(ctx, LAWYER_IIN, "Адвокат Пилот", "+77010000001")
    return ctx, customer, lawyer, cid, app_id


def test_pilot_list_shows_only_pilot_verified_priced_lawyers(world):
    ctx, customer, lawyer, cid, app_id = world
    other, other_id = lawyer_account(ctx, "800202400999", "Юрист Без Цены", "+77010000002")
    unverified = ctx.client.post("/v1/lawyer-applications", json={
        "country": "KZ", "full_name": "Не Проверен", "kind": "advocate", "license_number": "7777", "city": "Алматы",
        "phone": "+77010000003", "email": "x@y.kz", "consent": True}).json()["id"]
    assert customer.get(f"/v1/cases/{cid}/lawyers").json()["lawyers"] == []

    # a pilot lawyer needs a price; an unverified one cannot join the pilot
    r = ctx.client.post(f"/v1/admin/lawyer-applications/{other_id}/pilot", headers=ADM, json={"pilot": True})
    assert r.status_code == 422
    r = ctx.client.post(f"/v1/admin/lawyer-applications/{unverified}/pilot", headers=ADM,
                        json={"pilot": True, "price": 20000})
    assert r.status_code == 409
    set_pilot(ctx, other_id, pilot=False, price=10000)  # priced but not in the pilot
    view = set_pilot(ctx, app_id, pilot=True, price=30000, price_note="Анализ дела и претензия")
    assert view["listed"] is True and view["price"] == 30000

    listed = customer.get(f"/v1/cases/{cid}/lawyers").json()
    assert [x["id"] for x in listed["lawyers"]] == [app_id]
    one = listed["lawyers"][0]
    assert one["price"] == 30000 and one["price_note"] == "Анализ дела и претензия" and one["name"] == "Адвокат Пилот"
    assert listed["payment_available"] is True
    owner = ctx.client.get("/v1/admin/pilot-lawyers", headers=ADM).json()
    assert {x["id"]: x["pilot"] for x in owner["lawyers"]} == {app_id: True, other_id: False}
    assert owner["commission_pct"] == 15.0
    assert ctx.client.get("/v1/admin/pilot-lawyers").status_code == 403


def test_request_accept_pay_assigns_lawyer_without_unlocking_documents(world):
    ctx, customer, lawyer, cid, app_id = world
    set_pilot(ctx, app_id, pilot=True, price=30000)
    # the request snapshots the price; a second one while it is open is refused
    out = customer.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json={**CONTACT, "application_id": app_id})
    assert out["request"]["status"] == "new" and out["request"]["price"] == 30000
    assert ctx.client.post(f"/v1/cases/{cid}/lawyer-request", headers=customer.h,
                           json={**CONTACT, "application_id": app_id}).status_code == 409
    set_pilot(ctx, app_id, pilot=True, price=50000)  # a new price does not change the sent request

    # no bill before the lawyer accepts
    r = ctx.client.post(f"/v1/cases/{cid}/lawyer-payment", headers=customer.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_accepted"

    # the lawyer sees the kind of case, not the client's contacts
    reqs = lawyer.get("/v1/lawyer/requests").json()
    assert len(reqs) == 1 and reqs[0]["client"] is None and reqs[0]["price"] == 30000
    assert reqs[0]["summary"]["title"]
    assert ctx.client.get(f"/v1/cases/{cid}/lawyers", headers=lawyer.h).status_code == 404  # not their case
    req_id = reqs[0]["id"]
    lawyer.post(f"/v1/lawyer/requests/{req_id}/accept")
    assert ctx.client.post(f"/v1/lawyer/requests/{req_id}/decline", headers=lawyer.h).status_code == 409
    with ctx.container.session_factory() as s:
        texts = s.scalars(select(Notification.text).where(Notification.case_id == uuid.UUID(cid))).all()
        assert any("принял запрос" in t for t in texts)

    # dossier: not before the payment
    assert ctx.client.get(f"/v1/lawyer/cases/{cid}/dossier", headers=lawyer.h).status_code == 403

    bill = customer.post(f"/v1/cases/{cid}/lawyer-payment")["request"]["invoice"]
    assert bill["amount"] == 30000 and bill["purpose"] == "lawyer" and bill["status"] == "pending"
    assert bill["kaspi_pay_link"] == "https://pay.kaspi.kz/pay/konsilier" and "kaspi_phone" not in bill
    with ctx.container.session_factory() as s:
        inv = s.get(Invoice, bill["id"])
        assert float(inv.commission_pct) == 15.0 and float(inv.commission_amount) == 4500.0
        assert inv.method == "company"
        assert ctx.container.engine.invoice_of(s, s.get(Case, uuid.UUID(cid))) is None  # not a document bill

    claimed = customer.post(f"/v1/cases/{cid}/lawyer-payment/claim")["request"]["invoice"]
    assert claimed["status"] == "awaiting_confirmation"
    # the owner's payment view shows whose work, the commission and the payout
    listed = ctx.client.get("/v1/admin/payments", headers=ADM).json()
    row = next(x for x in listed if x["id"] == bill["id"])
    assert row["lawyer"] == {"name": "Person 0456", "commission_pct": 15.0, "commission_amount": 4500.0,
                             "payout": 25500.0}
    r = ctx.client.post(f"/v1/admin/payments/{bill['id']}", headers=ADM, json={"decision": "paid"})
    assert r.status_code == 200, r.text

    # the lawyer is on the case with the papers to sign; documents are not unlocked
    block = customer.get(f"/v1/cases/{cid}/lawyer").json()
    assert block["lawyer"]["name"] == "Person 0456"
    assert {a["kind"] for a in block["agreements"]} == {"consent", "engagement"}
    state = customer.get(f"/v1/cases/{cid}/lawyers").json()
    assert state["request"]["status"] == "paid"
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        assert case.paid is False and case.doc_credits == 0
        assert ctx.container.engine.unlock_source(s, case) in (None, "free")

    reqs = lawyer.get("/v1/lawyer/requests").json()
    assert reqs[0]["status"] == "paid" and reqs[0]["client"]["phone"] == "+77012345678"
    d = lawyer.get(f"/v1/lawyer/cases/{cid}/dossier").json()
    assert "телефон" in d["initial_text"] and d["client"]["name"] == "Асем Серикова"
    assert {"facts", "evidence", "deadlines", "documents", "story", "agreements"} <= set(d)


def test_lawyer_payment_refused_without_company_channel(world):
    ctx, customer, lawyer, cid, app_id = world
    ctx.container.engine.config.lawyer_pay_link = ""
    ctx.container.engine.config.lawyer_pay_account = ""
    # the personal Kaspi Gold of the document bills is never used for a lawyer
    ctx.container.engine.payments.recipient_name = "Иван И."
    ctx.container.engine.payments.kaspi_phone = "+77000000000"
    set_pilot(ctx, app_id, pilot=True, price=30000)
    customer.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json={**CONTACT, "application_id": app_id})
    assert customer.get(f"/v1/cases/{cid}/lawyers").json()["payment_available"] is False
    req_id = lawyer.get("/v1/lawyer/requests").json()[0]["id"]
    lawyer.post(f"/v1/lawyer/requests/{req_id}/accept")
    r = ctx.client.post(f"/v1/cases/{cid}/lawyer-payment", headers=customer.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "lawyer_payment_unavailable"

    # the company's requisites open it
    ctx.container.engine.config.lawyer_pay_account = "ТОО «Konsilier AI», БИН 260940036818, IBAN KZ00…"
    bill = customer.post(f"/v1/cases/{cid}/lawyer-payment")["request"]["invoice"]
    assert bill["company_account"].startswith("ТОО") and "kaspi_phone" not in bill and "kaspi_pay_link" not in bill


def test_decline_lets_the_client_choose_another(world):
    ctx, customer, lawyer, cid, app_id = world
    set_pilot(ctx, app_id, pilot=True, price=30000)
    customer.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json={**CONTACT, "application_id": app_id})
    req_id = lawyer.get("/v1/lawyer/requests").json()[0]["id"]
    lawyer.post(f"/v1/lawyer/requests/{req_id}/decline")
    state = customer.get(f"/v1/cases/{cid}/lawyers").json()
    assert state["request"] is None and state["last"]["status"] == "declined"
    customer.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json={**CONTACT, "application_id": app_id})


def test_dossier_closed_to_another_lawyer(world):
    ctx, customer, lawyer, cid, app_id = world
    stranger, _ = lawyer_account(ctx, "700303500789", "Другой Юрист", "+77010000004")
    set_pilot(ctx, app_id, pilot=True, price=30000)
    customer.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json={**CONTACT, "application_id": app_id})
    req_id = lawyer.get("/v1/lawyer/requests").json()[0]["id"]
    assert ctx.client.post(f"/v1/lawyer/requests/{req_id}/accept", headers=stranger.h).status_code == 404
    lawyer.post(f"/v1/lawyer/requests/{req_id}/accept")
    bill = customer.post(f"/v1/cases/{cid}/lawyer-payment")["request"]["invoice"]
    ctx.client.post(f"/v1/admin/payments/{bill['id']}", headers=ADM, json={"decision": "paid"})
    up = ctx.client.post(f"/v1/cases/{cid}/evidence", headers=customer.h, data={"kind": "receipt"},
                         files={"file": ("chek.txt", "Чек №1 на 150000".encode(), "text/plain")})
    assert up.status_code == 201, up.text
    d = lawyer.get(f"/v1/lawyer/cases/{cid}/dossier").json()
    ev = next(e for e in d["evidence"] if e["filename"] == "chek.txt")
    got = lawyer.get(f"/v1/lawyer/cases/{cid}/evidence/{ev['id']}")
    assert got.content == "Чек №1 на 150000".encode()
    assert ctx.client.get(f"/v1/lawyer/cases/{cid}/evidence/{ev['id']}", headers=stranger.h).status_code == 403
    assert ctx.client.get(f"/v1/lawyer/cases/{cid}/dossier", headers=stranger.h).status_code == 403
    assert ctx.client.get(f"/v1/lawyer/cases/{cid}/dossier", headers=customer.h).status_code == 403


def test_document_bill_is_not_cancelled_by_a_lawyer_bill(ctx):
    """invoice_of sees only document bills; a lawyer bill beside it neither replaces nor cancels it."""
    from konsilier.core.models import LawyerRequest

    customer = web_user(ctx)
    cid = customer.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине, через неделю сломался, деньги не возвращают 150000",
        "country": "KZ"})["case"]["id"]
    eng = ctx.container.engine
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        doc = Invoice(case_id=case.id, user_id=case.owner_id, purpose="document", code="DOC-1", method="manual_transfer",
                      amount=1990, currency="KZT", status="pending")
        s.add(doc)
        req = LawyerRequest(case_id=case.id, user_id=case.owner_id, full_name="А", phone="+77010000000",
                            status="accepted", price=30000)
        s.add(req)
        s.flush()
        law = Invoice(case_id=case.id, user_id=case.owner_id, purpose="lawyer", code="LAW-1", method="company",
                      amount=30000, currency="KZT", status="pending", lawyer_request_id=req.id)
        s.add(law)
        s.flush()
        assert eng.invoice_of(s, case).code == "DOC-1"
        s.commit()
    with ctx.container.session_factory() as s:
        assert s.scalar(select(Invoice.status).where(Invoice.code == "DOC-1")) == "pending"
        assert s.scalar(select(Invoice.status).where(Invoice.code == "LAW-1")) == "pending"


def test_private_invite_link_marks_the_application(ctx):
    # owner 30.09: pilot lawyers join by a private link; a forged or expired link is not accepted
    r = ctx.client.post("/v1/admin/pilot-invite", headers=ADM)
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert "/join?t=" in url
    token = url.split("t=", 1)[1]
    assert ctx.client.post("/v1/admin/pilot-invite").status_code in (401, 403)  # owner only
    assert ctx.client.get(f"/v1/lawyer-invite/{token}").json() == {"valid": True}
    exp, sig = token.split(".")
    assert ctx.client.get(f"/v1/lawyer-invite/{exp}.{sig[:-2]}xx").json() == {"valid": False}
    assert ctx.client.get(f"/v1/lawyer-invite/{int(exp) + 1}.{sig}").json() == {"valid": False}
    assert ctx.client.get("/v1/lawyer-invite/100.abc").json() == {"valid": False}  # long expired

    base = {"country": "KZ", "kind": "advocate", "license_number": "12345", "city": "Алматы", "consent": True}
    with_link = ctx.client.post("/v1/lawyer-applications", json={
        **base, "full_name": "Пилот Ссылкин", "phone": "+77010000011", "invite": token}).json()["id"]
    without = ctx.client.post("/v1/lawyer-applications", json={
        **base, "full_name": "Без Ссылки", "phone": "+77010000012", "invite": "1.bad"}).json()["id"]
    notes = {a["id"]: a.get("desk_note") for a in ctx.client.get("/v1/admin/lawyer-applications", headers=ADM).json()}
    assert "закрытой ссылке" in (notes[with_link] or "")
    assert not notes[without]
