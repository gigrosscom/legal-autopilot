"""Production smoke checks run as a marked test user: out of the metrics and the operations centre, the team is
never notified, and the smoke token only touches test users' own bills."""

from __future__ import annotations

from .test_e2e import Api, web_user
from .test_lawyer_onboarding import Outbox
from .test_ops_centre import operator
from .test_payment import manual, qualified_case

HDR = {"X-Smoke-Token": "smoke-secret"}


def test_closed_without_the_token(ctx):
    assert ctx.client.post("/v1/smoke/user").status_code == 404  # SMOKE_TOKEN unset: the endpoints do not exist
    ctx.container.settings.smoke_token = "smoke-secret"
    assert ctx.client.post("/v1/smoke/user", headers={"X-Smoke-Token": "wrong"}).status_code == 404


def test_test_user_path_stays_invisible_to_the_team(ctx):
    manual(ctx)
    st = ctx.container.settings
    st.smoke_token, st.ops_clients_emails, st.background_jobs = "smoke-secret", "support@konsilier.com", "inline"
    outbox = Outbox()
    ctx.container.email_sender = outbox
    real_api, real_case = qualified_case(ctx)  # a real client, for comparison

    token = ctx.client.post("/v1/smoke/user", headers=HDR).json()["token"]
    api = Api(ctx, token)
    cid = api.post("/v1/cases", expect=201, json={
        "text": "Заказал шкаф на маркетплейсе 01.09.2026 за 90000, не доставили, хочу вернуть деньги",
        "country": "KZ"})["case"]["id"]
    from .test_e2e import run_intake
    from .test_payment import ANSWERS
    assert run_intake(api, cid, ANSWERS)["status"] == "qualified"
    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})
    api.post(f"/v1/cases/{cid}/payment/claim")
    assert outbox.sent == []  # «клиент оплатил» is not mailed for a test user

    desk = operator(ctx, "support@konsilier.com")
    assert desk.get("/v1/ops/clients/payments").json() == []  # the desk never sees the test bill
    # the smoke token confirms the test user's bill; the document is made at once
    case = ctx.client.post(f"/v1/smoke/cases/{cid}/payment/confirm", headers=HDR).json()["case"]
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["actions"] and case["actions"][0]["downloadable"] is True
    # …but never a real client's bill
    real_api.post(f"/v1/cases/{real_case}/payment", json={"purpose": "document"})
    assert ctx.client.post(f"/v1/smoke/cases/{real_case}/payment/confirm", headers=HDR).status_code == 404

    metrics = ctx.client.get("/v1/admin/metrics", headers={"X-Admin-Token": "adm"}).json()
    assert metrics["totals"]["cases"] == 1 and metrics["totals"]["documents"] == 0  # only the real client's case


def test_real_users_are_not_test_users(ctx):
    api = web_user(ctx)
    from sqlalchemy import select

    from konsilier.core.models import User
    with ctx.container.session_factory() as s:
        assert s.scalars(select(User.is_test)).all() == [False]
    assert api
