"""Document payment by manual transfer (Kaspi): the invoice waits for the clients desk, the document is prepared and
downloadable only once the desk confirms the transfer. Chat stays free; stub mode (tests, dev) pays at once."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from konsilier.config import Settings
from konsilier.core.adapters.payment import (ManualTransferPaymentAdapter, StubPaymentAdapter, build_payments,
                                             new_payment_code)
from konsilier.core.models import AuditLog, Case, Invoice

from .test_e2e import run_intake, web_user
from .test_lawyer_onboarding import Outbox
from .test_ops_centre import operator

STORY = "Заказал шкаф на маркетплейсе 01.09.2026 за 90000, не доставили, хочу вернуть деньги"
ANSWERS = {"seller_name": "ИП Мебель", "seller_bin": "пропустить", "goods_description": "Шкаф",
           "applicant_name": "Петров Пётр", "applicant_phone": "+7 700 000 00 00", "applicant_iin": "пропустить",
           "seller_email": "пропустить", "evidence": "пропустить", "identity_document": "пропустить"}
# placeholders only: real requisites live in the server's .env
RECIPIENT, PHONE = "Получатель Тест", "+7 700 111 22 33"


def manual(ctx, name: str = RECIPIENT, phone: str = PHONE) -> None:
    ctx.container.engine.payments = ManualTransferPaymentAdapter(recipient_name=name, kaspi_phone=phone,
                                                                 comment_prefix="ka")
    ctx.container.engine.config.approval_required_first_n = 0


def qualified_case(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    assert run_intake(api, cid, ANSWERS)["status"] == "qualified"
    return api, cid


def test_build_payments_reads_mode_and_requisites():
    assert isinstance(build_payments(Settings(payment_mode="stub")), StubPaymentAdapter)
    off = build_payments(Settings(payment_mode="manual_transfer", payment_recipient_name="", payment_kaspi_phone=""))
    assert isinstance(off, ManualTransferPaymentAdapter) and not off.available() and off.details() == {}
    on = build_payments(Settings(payment_mode="manual_transfer", payment_recipient_name=RECIPIENT,
                                 payment_kaspi_phone=PHONE, payment_comment_prefix="KA"))
    assert on.available() and on.details() == {"recipient_name": RECIPIENT, "kaspi_phone": PHONE}
    inv = on.create_invoice(case_id="c", amount=1990, currency="KZT")
    assert inv.status == "pending" and inv.id.startswith("KA-") and len(inv.id) == 9
    assert len({new_payment_code() for _ in range(200)}) == 200


def test_manual_transfer_full_path(ctx):
    manual(ctx)
    st = ctx.container.settings
    st.ops_clients_emails = "support@konsilier.com"
    outbox = Outbox()
    ctx.container.email_sender = outbox
    api, cid = qualified_case(ctx)

    # first try: no document, an invoice with the price, requisites and a payment code
    out = api.post(f"/v1/cases/{cid}/actions/next")
    assert out["action_id"] is None and out["case"]["status"] == "qualified" and out["case"]["actions"] == []
    pay = out["payment"]
    assert pay["amount"] == 1990 and pay["currency"] == "KZT" and pay["status"] == "pending"
    assert pay["recipient_name"] == RECIPIENT and pay["kaspi_phone"] == PHONE and pay["code"].startswith("KA-")
    # pressing again keeps the same invoice
    again = api.post(f"/v1/cases/{cid}/actions/next")["payment"]
    assert again["code"] == pay["code"]

    # "I have paid" → awaiting confirmation, the clients desk is e-mailed with the code
    claimed = api.post(f"/v1/cases/{cid}/payment/claim")["case"]["payment"]
    assert claimed["status"] == "awaiting_confirmation"
    assert outbox.sent[-1][0] == "support@konsilier.com" and pay["code"] in outbox.sent[-1][2]
    assert api.post(f"/v1/cases/{cid}/actions/next")["action_id"] is None  # still not paid

    # the desk sees it and does not find the transfer → the client may report again
    cl = operator(ctx, "support@konsilier.com")
    assert cl.get("/v1/ops/me").json()["new"]["clients"] == 1
    rows = cl.get("/v1/ops/clients/payments").json()
    assert [r["code"] for r in rows] == [pay["code"]] and rows[0]["amount"] == 1990
    assert ctx.client.get("/v1/ops/clients/payments", headers=api.h).status_code == 403
    nf = cl.post(f"/v1/ops/clients/payments/{rows[0]['id']}", json={"decision": "not_found"})
    assert nf["status"] == "not_found"
    assert api.get(f"/v1/cases/{cid}").json()["payment"]["status"] == "not_found"
    assert api.post(f"/v1/cases/{cid}/payment/claim")["case"]["payment"]["status"] == "awaiting_confirmation"

    # payment received → paid; the client is told on the site
    ok = cl.post(f"/v1/ops/clients/payments/{rows[0]['id']}", json={"decision": "paid", "note": "Kaspi 12:05"})
    assert ok["status"] == "paid" and ok["decided_by"] == "support@konsilier.com"
    assert cl.get("/v1/ops/clients/payments").json() == []
    note = ctx.client.get("/v1/notifications", headers=api.h).json()
    assert any("Оплата получена" in n["text"] for n in note)
    assert ctx.client.post(f"/v1/ops/clients/payments/{rows[0]['id']}", headers=cl.h,
                           json={"decision": "not_found"}).status_code == 409

    # now the document is prepared and downloadable
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    a = case["actions"][0]
    assert case["payment"]["status"] == "paid" and a["downloadable"] is True
    api.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=docx")
    with ctx.container.session_factory() as s:
        events = [e.event for e in s.scalars(select(AuditLog).where(AuditLog.case_id == uuid.UUID(cid)))]
        assert {"invoice_created", "payment_claimed", "payment_not_found", "payment_confirmed"} <= set(events)
        assert s.scalar(select(Invoice)).status == "paid"


def test_no_requisites_means_no_documents(ctx):
    manual(ctx, name="", phone="")
    api, cid = qualified_case(ctx)
    r = ctx.client.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "payment_unavailable"
    view = api.get(f"/v1/cases/{cid}").json()
    assert view["payment"]["available"] is False and view["actions"] == []
    assert view["payment"]["kaspi_phone"] is None


def test_download_is_locked_until_paid(ctx):
    """A document that exists for an unpaid case (e.g. prepared by a lawyer) is not handed out."""
    api, cid = qualified_case(ctx)  # stub mode: paid at once
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    a = case["actions"][0]
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        c.paid = False
        s.query(Invoice).delete()
        s.commit()
    manual(ctx)
    assert ctx.client.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=docx",
                          headers=api.h).status_code == 402
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["downloadable"] is False


def test_stub_mode_pays_at_once_and_universal_path_is_priced(ctx):
    api, cid = qualified_case(ctx)
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    assert case["status"] == "action_ready" and case["payment"]["status"] == "paid"
    # universal path documents cost as much as the cheapest verified scenario of the country
    from .test_coverage_levels import _universal_case

    cid2, _ = _universal_case(api)
    case2 = api.post(f"/v1/cases/{cid2}/forum", json={"forum_id": "kz.labor_inspection"})["case"]
    assert case2["scenario"]["id"].startswith("kz.generic.")
    assert case2["scenario"]["price"] == {"amount": 1990, "currency": "KZT", "model": "fixed"}
