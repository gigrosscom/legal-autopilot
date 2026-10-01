"""«Документы» in /ops (owner 01.10): every document made for an order, newest first, with the case, the service,
the client (masked), the bill and its state; filters «оплаченные», «сегодня» and a search by case or bill code."""
from __future__ import annotations

from .test_lawyer_onboarding import Outbox
from .test_payment import confirm, qualified_case

ADMIN = {"X-Admin-Token": "adm"}


def paid_document(ctx, email: str):
    ctx.container.email_sender = Outbox()
    api, cid = qualified_case(ctx)
    confirm(api, "email", email)
    pay = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]  # stub: paid at once
    action = api.post(f"/v1/cases/{cid}/actions/next")["action_id"]
    assert action
    return api, cid, pay, action


def test_documents_list_filters_and_download(ctx):
    c = ctx.client
    assert c.get("/v1/admin/documents").status_code == 403
    _, cid, _, action = paid_document(ctx, "aigerim.nurlanova@mail.kz")
    _, cid2, _, action2 = paid_document(ctx, "second.client@mail.kz")
    out = c.get("/v1/admin/documents", headers=ADMIN).json()
    assert out["total"] == 2 and [d["id"] for d in out["items"]] == [action2, action]  # newest first
    row = out["items"][1]
    assert row["case_id"] == cid and row["case_short"] == cid[:8] and row["service"] and row["docx"]
    code = row["bill"]["code"]
    assert code and row["bill"]["status"] == "paid" and row["bill"]["label"] == "оплачен"
    assert row["client"] and "aigerim.nurlanova@mail.kz" not in row["client"]  # never the full address
    assert c.get("/v1/admin/documents", headers=ADMIN, params={"paid": True}).json()["total"] == 2
    assert c.get("/v1/admin/documents", headers=ADMIN, params={"today": True}).json()["total"] == 2
    found = c.get("/v1/admin/documents", headers=ADMIN, params={"q": code.lower()}).json()
    assert [d["id"] for d in found["items"]] == [action]
    assert c.get("/v1/admin/documents", headers=ADMIN, params={"q": cid2[:8]}).json()["items"][0]["case_id"] == cid2
    page = c.get("/v1/admin/documents", headers=ADMIN, params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and [d["id"] for d in page["items"]] == [action]
    r = c.get(f"/v1/admin/actions/{action}/document", headers=ADMIN, params={"format": "docx"})
    assert r.status_code == 200 and len(r.content) > 1000
