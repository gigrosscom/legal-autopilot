"""Document payment by manual transfer (Kaspi): the invoice waits for the clients desk, the document is prepared and
downloadable only once the desk confirms the transfer. Chat stays free; stub mode (tests, dev) pays at once."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from konsilier.config import Settings
from konsilier.core.adapters.payment import (ManualTransferPaymentAdapter, StubPaymentAdapter, build_payments,
                                             new_payment_code)
from konsilier.core.models import AuditLog, Case, Invoice
from konsilier.identity.senders import LogSender

from .test_e2e import run_intake, web_user
from .test_lawyer_onboarding import Outbox
from .test_ops_centre import operator

STORY = "Заказал шкаф на маркетплейсе 01.09.2026 за 90000, не доставили, хочу вернуть деньги"
ANSWERS = {"seller_name": "ИП Мебель", "seller_bin": "пропустить", "goods_description": "Шкаф",
           "applicant_name": "Петров Пётр", "applicant_phone": "+7 700 000 00 00", "applicant_iin": "пропустить",
           "seller_email": "пропустить", "seller_address": "Алматы, ул. Мебельная 1",
           "applicant_address": "Алматы, ул. Абая 1", "evidence": "пропустить", "identity_document": "пропустить"}
# placeholders only: real requisites live in the server's .env
RECIPIENT, PHONE = "Получатель Тест", "+7 700 111 22 33"


def manual(ctx, name: str = RECIPIENT, phone: str = PHONE) -> None:
    ctx.container.engine.payments = ManualTransferPaymentAdapter(recipient_name=name, kaspi_phone=phone,
                                                                 comment_prefix="ka")
    ctx.container.engine.config.approval_required_first_n = 0
    ctx.container.sms_sender = LogSender("sms")  # SMS sign-in on: a phone is confirmed before paying


def confirm(api, kind: str = "phone", target: str = "+7 701 555 00 11") -> None:
    """The person confirms a phone (or an e-mail) by the one-time code, as in the payment window."""
    ctx = api.ctx
    ctx.container.settings.dev_show_codes = True
    code = api.post(f"/v1/auth/{kind}/start", json={"target": target})["dev_code"]
    api.post(f"/v1/auth/{kind}/verify", json={"target": target, "code": code})


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

    # first try: no document; the person chooses one document (1 990 ₸) or «Дело под ключ» (9 990 ₸)
    out = api.post(f"/v1/cases/{cid}/actions/next")
    assert out["action_id"] is None and out["case"]["status"] == "qualified" and out["case"]["actions"] == []
    assert out["payment"]["status"] == "none" and out["payment"]["code"] is None
    assert out["payment"]["options"] == [{"purpose": "document", "amount": 1990}, {"purpose": "case", "amount": 9990}]
    # a bill only once the phone is confirmed: the document and the reminders reach the person
    r = ctx.client.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert r.status_code == 422 and r.json()["detail"] == {"code": "contact_required", "message": "contact_required",
                                                           "methods": ["phone"]}
    confirm(api)
    pay = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]
    assert pay["amount"] == 1990 and pay["currency"] == "KZT" and pay["status"] == "pending"
    assert pay["purpose"] == "document"
    assert pay["recipient_name"] == RECIPIENT and pay["kaspi_phone"] == PHONE and pay["code"].startswith("KA-")
    # asking again keeps the same invoice
    again = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]
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
    note = ctx.client.get("/v1/notifications", headers=api.h).json()["items"]
    assert any("Оплата получена" in n["text"] for n in note)
    assert ctx.client.post(f"/v1/ops/clients/payments/{rows[0]['id']}", headers=cl.h,
                           json={"decision": "not_found"}).status_code == 409

    # now the document is prepared and downloadable; the paid document is used up
    assert api.get(f"/v1/cases/{cid}").json()["payment"]["credits"] == 1
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    a = case["actions"][0]
    assert a["downloadable"] is True and case["payment"]["credits"] == 0
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
        for act in c.actions:
            act.unlocked_by = None
        s.query(Invoice).delete()
        s.commit()
    manual(ctx)
    assert ctx.client.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=docx",
                          headers=api.h).status_code == 402
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["downloadable"] is False


def test_stub_mode_pays_at_once_and_universal_path_is_priced(ctx):
    api, cid = qualified_case(ctx)
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    assert case["status"] == "action_ready" and case["actions"][0]["downloadable"] is True
    # universal path documents cost as much as the cheapest verified scenario of the country
    from .test_coverage_levels import _universal_case

    cid2, _ = _universal_case(api)
    case2 = api.post(f"/v1/cases/{cid2}/forum", json={"forum_id": "kz.labor_inspection"})["case"]
    assert case2["scenario"]["id"].startswith("kz.generic.")
    assert case2["scenario"]["price"] == {"amount": 1990, "currency": "KZT", "model": "fixed"}


def test_one_document_or_the_whole_case(ctx):
    """1 990 ₸ pays for one document; «Дело под ключ» for every document of the case; switching the choice before
    paying cancels the first bill."""
    manual(ctx)
    api, cid = qualified_case(ctx)
    confirm(api)
    eng = ctx.container.engine
    first = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]["code"]
    whole = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "case"})["case"]["payment"]
    assert whole["purpose"] == "case" and whole["amount"] == 9990 and whole["code"] != first
    with ctx.container.session_factory() as s:
        assert s.scalar(select(Invoice).where(Invoice.code == first)).status == "cancelled"
        case = s.get(Case, uuid.UUID(cid))
        # a paid single document is spent on one document only
        case.doc_credits = 1
        assert eng.unlock_source(s, case) == "credit"
        case.doc_credits = 0
        assert eng.unlock_source(s, case) is None
        inv = s.scalar(select(Invoice).where(Invoice.code == whole["code"]))
        eng.decide_payment(s, inv, "support@konsilier.com", True)
        assert case.paid and eng.unlock_source(s, case) == "case"
        s.commit()
    view = api.get(f"/v1/cases/{cid}").json()["payment"]
    assert view["status"] == "paid" and view["case_paid"] is True and view["options"] == []
    r = ctx.client.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "case"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_paid"


def test_business_plan_subscription(ctx):
    """«Бизнес»: a bill without a case, confirmed by the clients desk, gives 30 days with 20 documents."""
    manual(ctx)
    st = ctx.container.settings
    st.ops_clients_emails = "support@konsilier.com"
    ctx.container.email_sender = Outbox()
    api, cid = qualified_case(ctx)
    r = ctx.client.post("/v1/plans/biz/invoice", headers=api.h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "contact_required"  # not signed in
    with ctx.container.session_factory() as s:
        owner = s.get(Case, uuid.UUID(cid)).owner
        owner.email = "owner@firm.kz"
        s.commit()
    view = api.post("/v1/plans/biz/invoice")
    assert view["plans"]["biz"] == {"price": 29990, "documents": 20, "days": 30}
    inv = view["invoice"]
    assert inv["purpose"] == "plan" and inv["plan"] == "biz" and inv["amount"] == 29990
    assert inv["kaspi_phone"] == PHONE and inv["status"] == "pending"
    assert ctx.client.post("/v1/plans/nope/invoice", headers=api.h).status_code == 409
    assert api.post("/v1/plans/invoice/claim")["invoice"]["status"] == "awaiting_confirmation"

    cl = operator(ctx, "support@konsilier.com")
    row = cl.get("/v1/ops/clients/payments").json()[0]
    assert row["case_id"] is None and row["case_title"] == "Тариф «Бизнес»" and row["purpose"] == "plan"
    cl.post(f"/v1/ops/clients/payments/{row['id']}", json={"decision": "paid"})

    plans = api.get("/v1/plans").json()
    assert plans["invoice"] is None
    assert {k: plans["subscription"][k] for k in ("plan", "documents", "left")} == {"plan": "biz", "documents": 20,
                                                                                   "left": 20}
    # the subscription pays for the owner's documents
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    assert case["actions"][0]["downloadable"] is True
    assert api.get("/v1/plans").json()["subscription"]["left"] == 19


def test_document_prepared_by_itself_once_payment_confirmed(ctx):
    """The person does not press "prepare" again: after the desk confirms, the scheduler prepares the document."""
    from datetime import timedelta

    from konsilier.core.models import utcnow

    manual(ctx)
    ctx.container.settings.ops_clients_emails = "support@konsilier.com"
    api, cid = qualified_case(ctx)
    confirm(api)
    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})
    api.post(f"/v1/cases/{cid}/payment/claim")
    cl = operator(ctx, "support@konsilier.com")
    inv_id = cl.get("/v1/ops/clients/payments").json()[0]["id"]
    cl.post(f"/v1/ops/clients/payments/{inv_id}", json={"decision": "paid"})
    engine = ctx.container.engine
    with ctx.container.session_factory() as s:
        assert engine.prepare_paid_documents(s, utcnow()) == 0  # the open page gets its chance first
        assert engine.prepare_paid_documents(s, utcnow() + timedelta(minutes=2)) == 1
        s.commit()
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["status"] == "action_ready" and case["actions"][0]["downloadable"] is True
    assert case["payment"]["credits"] == 0
    assert any("Документ готов" in n["text"] for n in ctx.client.get("/v1/notifications", headers=api.h).json()["items"])
    with ctx.container.session_factory() as s:  # done once only
        assert engine.prepare_paid_documents(s, utcnow() + timedelta(minutes=3)) == 0


def test_document_ready_the_moment_the_desk_confirms(ctx):
    """The text is written while the person pays; the desk's confirmation makes the document at once."""
    manual(ctx)
    ctx.container.settings.background_jobs = "inline"
    ctx.container.settings.ops_clients_emails = "support@konsilier.com"
    api, cid = qualified_case(ctx)
    confirm(api)
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).narrative  # written as soon as the interview was done
    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})
    api.post(f"/v1/cases/{cid}/payment/claim")
    cl = operator(ctx, "support@konsilier.com")
    inv_id = cl.get("/v1/ops/clients/payments").json()[0]["id"]
    calls = len(ctx.llm.calls) if hasattr(ctx.llm, "calls") else None
    cl.post(f"/v1/ops/clients/payments/{inv_id}", json={"decision": "paid"})
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["status"] == "action_ready" and case["actions"][0]["downloadable"] is True
    if calls is not None:
        assert len(ctx.llm.calls) == calls  # no model call after the payment: only the file is made
    api.get(f"/v1/cases/{cid}/actions/{case['actions'][0]['id']}/document?format=docx")


def test_contact_before_paying_falls_back_to_email_and_spares_telegram(ctx):
    """Without SMS sign-in on the server the e-mail is asked; any confirmed contact is enough. Telegram
    users are reachable in the bot and pay as before; PAYMENT_REQUIRES_CONTACT=false switches the rule off."""
    from .test_e2e import telegram_user

    manual(ctx)
    ctx.container.sms_sender = None
    ctx.container.email_sender = LogSender("email")
    api, cid = qualified_case(ctx)
    r = ctx.client.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert r.status_code == 422 and r.json()["detail"]["methods"] == ["email"]
    confirm(api, "email", "owner@mail.kz")
    assert api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]["status"] == "pending"

    ctx.container.sms_sender = LogSender("sms")  # SMS on: the phone is what is asked of someone with no contact
    api2, cid2 = qualified_case(ctx)
    r = ctx.client.post(f"/v1/cases/{cid2}/payment", headers=api2.h, json={"purpose": "case"})
    assert r.status_code == 422 and r.json()["detail"]["methods"] == ["phone"]
    confirm(api2, "email", "other@mail.kz")  # QA BUG-01: any confirmed contact counts, not only the phone
    assert ctx.client.post(f"/v1/cases/{cid2}/payment", headers=api2.h, json={"purpose": "case"}).status_code == 200
    ctx.container.settings.payment_requires_contact = False
    assert ctx.client.post(f"/v1/cases/{cid2}/payment", headers=api2.h, json={"purpose": "case"}).status_code == 200
    ctx.container.settings.payment_requires_contact = True

    tg = telegram_user(ctx)
    cid3 = tg.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    assert run_intake(tg, cid3, ANSWERS)["status"] == "qualified"
    assert tg.post(f"/v1/cases/{cid3}/payment", json={"purpose": "document"})["case"]["payment"]["status"] == "pending"


def test_payment_is_not_blocked_by_a_channel_that_is_down(ctx):
    """QA BUG-01: SMS off, the e-mail code fails to go out → the payment goes on instead of asking for e-mail forever;
    and a person signed in with ЭЦП (or any confirmed contact) is never asked for another one."""
    from konsilier.identity.senders import SendError

    class Broken:
        def send(self, to, subject, text):
            raise SendError("mail provider down")

    manual(ctx)
    ctx.container.sms_sender = None
    ctx.container.email_sender = Broken()
    api, cid = qualified_case(ctx)
    r = ctx.client.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert r.status_code == 422 and r.json()["detail"]["methods"] == ["email"]
    r = ctx.client.post("/v1/auth/email/start", headers=api.h, json={"target": "me@mail.kz"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "send_failed"
    pay = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]
    assert pay["status"] == "pending" and pay["code"]

    # a confirmed ЭЦП counts as a contact, even while every channel works
    ctx.container.send_failed_at.clear()
    ctx.container.email_sender = LogSender("email")
    api2, cid2 = qualified_case(ctx)
    r = ctx.client.post(f"/v1/cases/{cid2}/payment", headers=api2.h, json={"purpose": "document"})
    assert r.status_code == 422
    from konsilier.core.models import Identity, User
    with ctx.container.session_factory() as s:
        owner = s.get(Case, uuid.UUID(cid2)).owner
        s.add(Identity(user_id=owner.id, kind="iin", subject_hash="h-" + cid2[:8], display="ЭЦП"))
        s.commit()
    assert api2.post(f"/v1/cases/{cid2}/payment", json={"purpose": "document"})["case"]["payment"]["code"]
