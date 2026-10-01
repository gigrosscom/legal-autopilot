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


def test_clients_own_email_is_never_the_sellers_and_the_owner_can_fix_a_document(ctx):
    """The first client's claim (01.10): the seller's e-mail was the client's own; the owner corrects the data and the
    document is made again."""
    import uuid

    from konsilier.core.models import Case

    manual(ctx)
    api, cid = qualified_case(ctx)
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        case.owner.email = "client@gmail.com"
        eng = ctx.container.engine
        sc, pack = eng.scenario_of(case), eng.pack_of(case)
        case.facts = {k: v for k, v in case.facts.items() if k != "seller_email"}
        eng._apply_values(case, sc, pack, {"seller_email": "Client@gmail.com"}, None, strict=True)
        assert "seller_email" not in case.facts  # the person's own e-mail is not taken as the seller's
        eng._apply_values(case, sc, pack, {"seller_email": "support@shop.kz"}, None, strict=True)
        assert case.facts["seller_email"] == "support@shop.kz"
        s.commit()

    r = ctx.client.post(f"/v1/admin/cases/{cid}/facts", headers=ADM,
                        json={"values": {"seller_name": "Anthropic, PBC", "seller_email": ""}})
    assert r.status_code == 200, r.text
    assert r.json()["facts"]["seller_name"] == "Anthropic, PBC" and "seller_email" not in r.json()["facts"]
    assert ctx.client.post(f"/v1/admin/cases/{cid}/facts", json={"values": {}}).status_code in (401, 403)


def test_telegram_invitation_counts_and_paid_by_invitation_metric(ctx):
    """Marketing 01.10: /start <code> in the bot records the invitation; metrics count invited people who paid."""
    from konsilier.core.models import User

    inviter = web_user(ctx)
    code = inviter.get("/v1/referral").json()["code"]
    r = ctx.client.post("/v1/users/telegram", headers={"X-Bot-Secret": "bot"},
                        json={"telegram_id": "777001", "language": "ru", "ref": code, "src": "telegram"})
    assert r.status_code == 200, r.text
    with ctx.container.session_factory() as s:
        from sqlalchemy import select
        u = s.scalar(select(User).where(User.external_id == "777001"))
        assert u.referred_by is not None and u.source == "telegram"
    m = ctx.client.get("/v1/admin/metrics", headers=ADM).json()
    assert m["referral"]["referred_users"] >= 1 and m["referral"]["referred_paid"] == 0
