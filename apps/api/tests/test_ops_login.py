"""«Konsiliér Ops» sign-in by a code to e-mail (owner 01.10): only OWNER_EMAILS; the session has the key's rights for
/v1/admin/*, is not the key, lasts 30 days and «Выйти» revokes it; codes keep the sign-in limits."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from konsilier.core.models import LoginChallenge

from .test_lawyer_onboarding import Outbox

OWNER = "owner@konsilier.com"


def setup(ctx, owners: str = OWNER) -> Outbox:
    outbox = Outbox()
    ctx.container.email_sender = outbox
    ctx.settings.owner_emails = owners
    ctx.settings.dev_show_codes = True
    return outbox


def sign_in(ctx, email: str = OWNER) -> str:
    c = ctx.client
    code = c.post("/v1/ops-auth/start", json={"email": email}).json()["dev_code"]
    r = c.post("/v1/ops-auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_off_without_owner_emails(ctx):
    setup(ctx, owners="")
    assert ctx.client.get("/v1/ops-auth/methods").json() == {"email": False}
    assert ctx.client.post("/v1/ops-auth/start", json={"email": OWNER}).status_code == 404


def test_owner_signs_in_with_a_code_and_gets_admin_rights(ctx):
    outbox = setup(ctx, owners=f" {OWNER.upper()} , second@konsilier.com")
    c = ctx.client
    assert c.get("/v1/ops-auth/methods").json() == {"email": True}
    assert c.get("/v1/admin/metrics?weeks=1").status_code == 403
    token = sign_in(ctx)
    assert outbox.sent[-1][0] == OWNER and "Konsiliér Ops" in outbox.sent[-1][2]
    assert token.startswith("ops_") and token != ctx.settings.admin_token
    assert c.get("/v1/admin/metrics?weeks=1", headers={"X-Admin-Token": token}).status_code == 200
    # the key still works as before
    assert c.get("/v1/admin/metrics?weeks=1", headers={"X-Admin-Token": "adm"}).status_code == 200
    # only the HMAC of the session is stored, for 30 days
    with ctx.container.session_factory() as s:
        row = s.scalar(select(LoginChallenge).where(LoginChallenge.kind == "ops_session"))
        assert token not in (row.secret_hash, str(row.result))
        assert timedelta(days=29) < row.expires_at.replace(tzinfo=None) - row.created_at.replace(tzinfo=None) <= timedelta(days=30, seconds=5)
    # «Выйти» revokes it
    c.post("/v1/ops-auth/logout", headers={"X-Admin-Token": token})
    assert c.get("/v1/admin/metrics?weeks=1", headers={"X-Admin-Token": token}).status_code == 403


def test_other_addresses_get_no_letter_and_no_session(ctx):
    outbox = setup(ctx)
    c = ctx.client
    r = c.post("/v1/ops-auth/start", json={"email": "someone@mail.kz"})
    assert r.status_code == 200 and r.json() == {"sent": True} and outbox.sent == []  # the same answer, no letter
    assert c.post("/v1/ops-auth/verify", json={"email": "someone@mail.kz", "code": "000000"}).status_code == 400
    assert c.get("/v1/admin/metrics?weeks=1", headers={"X-Admin-Token": "ops_forged"}).status_code == 403


def test_wrong_code_and_limits(ctx):
    setup(ctx)
    c = ctx.client
    assert c.post("/v1/ops-auth/start", json={"email": OWNER}).status_code == 200
    assert c.post("/v1/ops-auth/start", json={"email": OWNER}).status_code == 429  # resend after 60 s
    for _ in range(5):
        assert c.post("/v1/ops-auth/verify", json={"email": OWNER, "code": "000000"}).status_code in (400, 401)
    assert c.post("/v1/ops-auth/verify", json={"email": OWNER, "code": "000000"}).status_code == 429


def test_session_ends_when_the_address_is_removed(ctx):
    setup(ctx)
    token = sign_in(ctx)
    ctx.settings.owner_emails = "other@konsilier.com"
    assert ctx.client.get("/v1/admin/metrics?weeks=1", headers={"X-Admin-Token": token}).status_code == 403
