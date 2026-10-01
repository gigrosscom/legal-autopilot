"""Smoke: a test user's e-mail confirmed only for Resend test sinks (the sending wizard's production check)."""


def test_smoke_email_only_for_test_users_and_resend_sinks(ctx, monkeypatch):
    ctx.container.settings.smoke_token = "s3cret"
    h = {"X-Smoke-Token": "s3cret"}
    tok = ctx.client.post("/v1/smoke/user", headers=h).json()["token"]
    auth = {**h, "Authorization": f"Bearer {tok}"}
    assert ctx.client.post("/v1/smoke/email", headers=auth, json={"email": "boss@konsilier.com"}).status_code == 404
    r = ctx.client.post("/v1/smoke/email", headers=auth, json={"email": "delivered@resend.dev"})
    assert r.status_code == 200 and r.json()["email"] == "delivered@resend.dev"
    assert ctx.client.post("/v1/smoke/email", headers={"Authorization": f"Bearer {tok}"},
                           json={"email": "delivered@resend.dev"}).status_code == 404
