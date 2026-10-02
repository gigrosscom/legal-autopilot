"""«Юрист по кнопке», paid directly (owner 01.10: «15 % по счёту ТОО раз в месяц», LAWYER_PAY_DIRECT): no company bill
for the client; after «принял» the lawyer gets the case and the client's contacts and sends the contract and the
bill; the lawyer marks «оплачено клиентом»; the platform's 15 % is counted from that mark."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from konsilier.core.models import AuditLog, Invoice, Notification

from .test_lawyer_pilot import ADM, CONTACT, set_pilot, world  # noqa: F401  (world is a fixture)


def test_direct_payment_flow(world):  # noqa: F811
    ctx, customer, lawyer, cid, app_id = world
    ctx.container.engine.config.lawyer_pay_direct = True
    set_pilot(ctx, app_id, pilot=True, price=30000)
    customer.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json={**CONTACT, "application_id": app_id})
    req_id = lawyer.get("/v1/lawyer/requests").json()[0]["id"]
    # before «принял»: no contacts; «оплачено клиентом» is refused
    assert ctx.client.post(f"/v1/lawyer/requests/{req_id}/client-paid", headers=lawyer.h).status_code == 409

    accepted = lawyer.post(f"/v1/lawyer/requests/{req_id}/accept")
    assert accepted["client"]["phone"].replace(" ", "") == CONTACT["phone"].replace(" ", "") and accepted["direct"] is True
    assert ctx.client.get(f"/v1/lawyer/cases/{cid}/dossier", headers=lawyer.h).status_code == 200
    with ctx.container.session_factory() as s:
        texts = s.scalars(select(Notification.text).where(Notification.case_id == uuid.UUID(cid))).all()
    assert any("свяжется с вами и пришлёт договор и счёт" in t for t in texts)

    # the client is never billed by the company
    view = customer.get(f"/v1/cases/{cid}/lawyers").json()["request"]
    assert view["direct"] is True and view["invoice"] is None
    r = ctx.client.post(f"/v1/cases/{cid}/lawyer-payment", headers=customer.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "direct_payment"
    with ctx.container.session_factory() as s:
        assert s.scalars(select(Invoice).where(Invoice.purpose == "lawyer")).all() == []

    # the lawyer marks the client's payment: the request is paid, 15 % is due to the platform
    paid = lawyer.post(f"/v1/lawyer/requests/{req_id}/client-paid")
    assert paid["status"] == "paid" and paid["commission"] == 4500
    with ctx.container.session_factory() as s:
        assert s.scalar(select(AuditLog.id).where(AuditLog.event == "lawyer_client_paid")) is not None
    owner = ctx.client.get("/v1/admin/pilot-lawyers", headers=ADM).json()
    row = next(x for x in owner["lawyers"] if x["id"] == app_id)
    assert owner["direct"] is True and row["commission_due"] == 4500 and row["requests"]["paid"] == 1
    assert ctx.client.post(f"/v1/lawyer/requests/{req_id}/client-paid", headers=lawyer.h).status_code == 409


def test_off_by_default_the_company_bill_as_before(world):  # noqa: F811
    ctx, customer, lawyer, cid, app_id = world
    set_pilot(ctx, app_id, pilot=True, price=30000)
    customer.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json={**CONTACT, "application_id": app_id})
    req_id = lawyer.get("/v1/lawyer/requests").json()[0]["id"]
    lawyer.post(f"/v1/lawyer/requests/{req_id}/accept")
    assert customer.post(f"/v1/cases/{cid}/lawyer-payment")["request"]["invoice"]["amount"] == 30000
    assert ctx.client.post(f"/v1/lawyer/requests/{req_id}/client-paid", headers=lawyer.h).status_code == 409
