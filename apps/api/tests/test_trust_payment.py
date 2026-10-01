"""Owner 02.10: documents on trust until the payment channel is set up (PAYMENT_TRUST_MODE). «Оплатил(а)» is taken as
paid — the document is given at once; the desk reconciles it later in /ops; the KPI counts confirmed payments only."""

from __future__ import annotations

from konsilier.core.engine import TRUST

from .test_lawyer_onboarding import Outbox
from .test_ops_centre import operator
from .test_payment import confirm, manual, qualified_case

ADMIN = {"X-Admin-Token": "adm"}


def trusted_claim(ctx):
    manual(ctx)
    ctx.container.engine.config.trust_payments = True
    ctx.container.settings.ops_clients_emails = "support@konsilier.com"
    outbox = Outbox()
    ctx.container.email_sender = outbox
    api, cid = qualified_case(ctx)
    confirm(api)
    pay = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]
    claimed = api.post(f"/v1/cases/{cid}/payment/claim")["case"]["payment"]
    return api, cid, pay, claimed, outbox


def test_paid_on_the_press_and_the_document_is_given(ctx):
    api, cid, pay, claimed, outbox = trusted_claim(ctx)
    assert claimed["status"] == "paid"
    out = api.post(f"/v1/cases/{cid}/actions/next")
    assert out["action_id"] is not None and out["case"]["actions"][-1]["downloadable"]
    # the client is told honestly: not «оплата подтверждена»
    texts = [n["text"] for n in ctx.client.get("/v1/notifications", headers=api.h).json()["items"]]
    assert any("Мы сверим оплату в течение дня" in t for t in texts) and not any("Оплата получена" in t for t in texts)
    # the desk is told to reconcile it
    assert outbox.sent[-1][0] == "support@konsilier.com" and "на доверии" in outbox.sent[-1][2]


def test_the_desk_reconciles_and_the_kpi_counts_confirmed_only(ctx):
    api, cid, pay, _, _ = trusted_claim(ctx)
    m = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()["payments"]
    assert m["paid"] == 0 and m["on_trust"] == 1 and m["revenue"] == {}
    rows = ctx.client.get("/v1/admin/payments", params={"status": "on_trust"}, headers=ADMIN).json()
    assert [r["code"] for r in rows] == [pay["code"]] and rows[0]["on_trust"] is True
    ok = ctx.client.post(f"/v1/admin/payments/{rows[0]['id']}", headers=ADMIN, json={"decision": "paid"}).json()
    assert ok["status"] == "paid" and ok["decided_by"] != TRUST and ok["on_trust"] is False
    assert ctx.client.get("/v1/admin/payments", params={"status": "on_trust"}, headers=ADMIN).json() == []
    m = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()["payments"]
    assert m["paid"] == 1 and m["on_trust"] == 0


def test_not_found_keeps_the_document_and_asks_to_pay(ctx):
    api, cid, pay, _, _ = trusted_claim(ctx)
    action = api.post(f"/v1/cases/{cid}/actions/next")["action_id"]
    cl = operator(ctx, "support@konsilier.com")
    row = cl.get("/v1/ops/clients/payments?status=on_trust").json()[0]
    nf = cl.post(f"/v1/ops/clients/payments/{row['id']}", json={"decision": "not_found"})
    assert nf["status"] == "not_found"
    case = api.get(f"/v1/cases/{cid}").json()
    assert any(a["id"] == action and a["downloadable"] for a in case["actions"])  # given on trust, it stays
    texts = [n["text"] for n in ctx.client.get("/v1/notifications", headers=api.h).json()["items"]]
    assert any("не нашли оплату" in t and pay["code"] in t for t in texts)


def test_off_by_default(ctx):
    manual(ctx)
    api, cid = qualified_case(ctx)
    confirm(api)
    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})
    assert api.post(f"/v1/cases/{cid}/payment/claim")["case"]["payment"]["status"] == "awaiting_confirmation"
