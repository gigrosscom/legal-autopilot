import uuid

from fastapi.testclient import TestClient


def new_user(client: TestClient, **body) -> dict:
    r = client.post("/v1/users", json={"language": "ru", **body})
    assert r.status_code == 200
    return r.json()


def test_invite_link_counts_new_people_and_channels(ctx):
    client = ctx.client
    alice = new_user(client, src="tiktok")
    h = {"Authorization": f"Bearer {alice['token']}"}
    ref = client.get("/v1/referral", headers=h).json()
    assert ref["link"].endswith(f"?ref={ref['code']}") and ref["invited"] == 0
    assert client.get("/v1/referral", headers=h).json()["code"] == ref["code"]  # stable

    new_user(client, ref=ref["code"].upper())
    new_user(client, ref=ref["code"], src="whatsapp")
    new_user(client, ref="nosuchcode")
    assert client.get("/v1/referral", headers=h).json()["invited"] == 2

    m = client.get("/v1/admin/metrics", headers={"X-Admin-Token": "adm"}).json()["referral"]
    assert m["referred_users"] == 2 and m["inviters"] == 1
    assert m["sources"]["tiktok"] == 1 and m["sources"]["referral"] == 1 and m["sources"]["whatsapp"] == 1
    assert m["k_factor"] == round(2 / 2, 3)


def _case(api) -> str:
    from .test_e2e import run_intake
    from .test_payment import ANSWERS, STORY

    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    assert run_intake(api, cid, ANSWERS)["status"] == "qualified"
    return cid


def _pay_document(desk, api, cid: str) -> None:
    """The person pays for one document and the clients desk confirms the transfer."""
    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})
    api.post(f"/v1/cases/{cid}/payment/claim")
    row = next(r for r in desk.get("/v1/ops/clients/payments").json() if r["case_id"] == cid)
    desk.post(f"/v1/ops/clients/payments/{row['id']}", json={"decision": "paid"})


def test_invited_person_pays_and_both_get_one_free_document(ctx):
    """The old reward (REFERRAL_BONUS_POINTS=0): one free document to each on the first payment."""
    from .test_e2e import Api
    from .test_ops_centre import operator
    from .test_payment import confirm, manual

    manual(ctx)
    ctx.container.engine.config.referral_bonus_points = 0
    ctx.container.settings.ops_clients_emails = "support@konsilier.com"
    desk = operator(ctx, "support@konsilier.com")
    alice = Api(ctx, new_user(ctx.client)["token"])
    code = alice.get("/v1/referral").json()["code"]
    bob = Api(ctx, new_user(ctx.client, ref=code)["token"])
    cid = _case(bob)
    alice_cid = _case(alice)
    # before anyone pays there is no bonus: Alice's payment window opens as usual
    assert alice.post(f"/v1/cases/{alice_cid}/actions/next")["payment"]["status"] == "none"

    confirm(bob)
    _pay_document(desk, bob, cid)
    assert alice.get("/v1/me").json()["bonus_documents"] == 1
    assert bob.get("/v1/me").json()["bonus_documents"] == 1
    assert alice.get("/v1/referral").json()["bonus_documents"] == 1
    for who in (alice, bob):
        assert any(n["kind"] == "referral" for n in who.get("/v1/notifications").json()["items"])

    # Bob's paid document is made from his payment; the bonus stays for later
    case = bob.post(f"/v1/cases/{cid}/actions/next")["case"]
    assert case["actions"][0]["downloadable"] is True and case["payment"]["bonus"] == 1

    # Alice's next document is free: the payment window does not open, the document is prepared at once
    view = alice.get(f"/v1/cases/{alice_cid}").json()["payment"]
    assert view["status"] == "paid" and view["bonus"] == 1 and view["credits"] == 0
    out = alice.post(f"/v1/cases/{alice_cid}/actions/next")
    assert out["action_id"] is not None and out["case"]["actions"][0]["downloadable"] is True
    assert alice.get("/v1/me").json()["bonus_documents"] == 0
    with ctx.container.session_factory() as s:
        from konsilier.core.models import Action

        assert s.get(Action, uuid.UUID(out["action_id"])).unlocked_by == "bonus"

    # credited once per invited person: Bob's next payment gives nothing more
    cid2 = _case(bob)
    _pay_document(desk, bob, cid2)
    assert alice.get("/v1/me").json()["bonus_documents"] == 0
    assert bob.get("/v1/me").json()["bonus_documents"] == 1


def test_no_bonus_without_an_inviter(ctx):
    from .test_e2e import Api
    from .test_ops_centre import operator
    from .test_payment import confirm, manual

    manual(ctx)
    ctx.container.settings.ops_clients_emails = "support@konsilier.com"
    desk = operator(ctx, "support@konsilier.com")
    carol = Api(ctx, new_user(ctx.client)["token"])
    cid = _case(carol)
    confirm(carol)
    _pay_document(desk, carol, cid)
    assert carol.get("/v1/me").json()["bonus_documents"] == 0
    assert not any(n["kind"] == "referral" for n in carol.get("/v1/notifications").json()["items"])


def test_bonus_account_points_on_joining_and_for_the_inviter(ctx):
    """Owner 02.10 «Бонусный счёт»: 1000 points to the invited person on joining, 1000 to the inviter on that
    person's first payment; points pay at most half of a document bill and come back if the bill is cancelled."""
    from .test_e2e import Api
    from .test_ops_centre import operator
    from .test_payment import confirm, manual

    manual(ctx)
    assert ctx.container.engine.config.referral_bonus_points == 1000
    ctx.container.settings.ops_clients_emails = "support@konsilier.com"
    desk = operator(ctx, "support@konsilier.com")
    alice = Api(ctx, new_user(ctx.client)["token"])
    code = alice.get("/v1/referral").json()["code"]
    bob = Api(ctx, new_user(ctx.client, ref=code)["token"])
    assert bob.get("/v1/me").json()["bonus_balance"] == 1000
    assert alice.get("/v1/me").json()["bonus_balance"] == 0

    cid = _case(bob)
    confirm(bob)
    price = bob.get(f"/v1/cases/{cid}").json()["payment"]["options"][0]["amount"]
    use = min(1000, int(price * 0.5))
    # «Дело под ключ» first, then a document: the cancelled bill gives its points back, the new one takes them
    pay = bob.post(f"/v1/cases/{cid}/payment", json={"purpose": "case"})["case"]["payment"]
    assert pay["bonus_used"] == 1000 and bob.get("/v1/me").json()["bonus_balance"] == 0
    pay = bob.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]
    assert pay["bonus_used"] == use and pay["amount"] == price - use
    assert bob.get("/v1/me").json()["bonus_balance"] == 1000 - use
    # nothing for the inviter until the payment is really found
    assert alice.get("/v1/me").json()["bonus_balance"] == 0
    bob.post(f"/v1/cases/{cid}/payment/claim")
    row = next(r for r in desk.get("/v1/ops/clients/payments").json() if r["case_id"] == cid)
    assert row["amount"] == price - use
    desk.post(f"/v1/ops/clients/payments/{row['id']}", json={"decision": "paid"})
    assert alice.get("/v1/me").json()["bonus_balance"] == 1000
    assert alice.get("/v1/referral").json()["bonus_balance"] == 1000
    assert any(n["kind"] == "referral" for n in alice.get("/v1/notifications").json()["items"])
    # no free documents in this mode
    assert alice.get("/v1/me").json()["bonus_documents"] == 0 and bob.get("/v1/me").json()["bonus_documents"] == 0

    # once per invited person
    cid2 = _case(bob)
    _pay_document(desk, bob, cid2)
    assert alice.get("/v1/me").json()["bonus_balance"] == 1000


def test_no_joining_points_without_a_valid_invite(ctx):
    carol = new_user(ctx.client, ref="nosuchcode")
    me = ctx.client.get("/v1/me", headers={"Authorization": f"Bearer {carol['token']}"}).json()
    assert me["bonus_balance"] == 0
