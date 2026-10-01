"""Owner 01.10: the deals board in the command centre — real clients only, a column per stage (case + bill), the
paid sum; and the clients' questions as a board."""

from __future__ import annotations

from .test_e2e import web_user
from .test_payment import manual, qualified_case

ADM = {"X-Admin-Token": "adm"}


def test_deals_board_follows_the_bill_and_hides_test_accounts(ctx):
    manual(ctx)
    ctx.container.settings.payment_requires_contact = False
    api, cid = qualified_case(ctx)
    board = ctx.client.get("/v1/admin/deals", headers=ADM).json()
    col = {c["id"]: [x["id"] for x in c["cards"]] for c in board["columns"]}
    assert cid in col["to_pay"]
    assert ctx.client.get("/v1/admin/deals").status_code in (401, 403)  # owner only

    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})
    api.post(f"/v1/cases/{cid}/payment/claim")
    board = ctx.client.get("/v1/admin/deals", headers=ADM).json()
    card = next(x for c in board["columns"] for x in c["cards"] if x["id"] == cid)
    assert card["column"] == "confirm" and card["bill"]["code"] and card["title"]
    assert board["waiting_for_owner"] == 1

    # a QA account's case is not a deal
    qa = web_user(ctx)
    with ctx.container.session_factory() as s:
        from konsilier.core.models import User
        u = s.get(User, qa.user_id) if hasattr(qa, "user_id") else None
        if u is None:
            import uuid
            from konsilier.core.models import Case
            qcid = qa.post("/v1/cases", expect=201, json={"text": "Купил телефон, сломался", "country": "KZ"})["case"]["id"]
            u = s.get(Case, uuid.UUID(qcid)).owner
        u.email = "qa-test+1@konsilier.com"
        s.commit()
    ids = [x["id"] for c in ctx.client.get("/v1/admin/deals", headers=ADM).json()["columns"] for x in c["cards"]]
    assert cid in ids and len(ids) == 1


def test_questions_board(ctx):
    api = web_user(ctx)
    r = ctx.client.post("/v1/support", headers=api.h, json={"kind": "question", "text": "Как оплатить?",
                                                             "email": "client@mail.kz"})
    assert r.status_code in (200, 201), r.text
    board = ctx.client.get("/v1/admin/tickets", headers=ADM).json()
    new = next(c for c in board["columns"] if c["id"] == "new")["cards"]
    assert len(new) == 1
    tid = new[0]["id"]
    assert ctx.client.post(f"/v1/admin/tickets/{tid}/status", headers=ADM, json={"status": "done"}).status_code == 200
    board = ctx.client.get("/v1/admin/tickets", headers=ADM).json()
    assert [x["id"] for x in next(c for c in board["columns"] if c["id"] == "done")["cards"]] == [tid]
