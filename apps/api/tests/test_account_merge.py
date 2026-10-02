"""Owner 01.10: signing in never loses a case. Google with a verified address that already has an account → that
account; any sign-in brings this device's anonymous cases along; two accounts of one person become one."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from konsilier.core.models import Case, Identity, LoginChallenge, User

from .test_auth_google_apple import google_login, h, keys, new_token, oidc_ctx  # noqa: F401 — fixtures

STORY = "Купил телефон, сломался, магазин не возвращает деньги 150000"


def email_account(c, ctx, address: str) -> str:
    """An account made by the e-mail code sign-in, with one case."""
    ctx.settings.dev_show_codes = True
    from .test_lawyer_onboarding import Outbox
    ctx.container.email_sender = Outbox()
    tok = new_token(c)
    c.post("/v1/cases", json={"text": STORY}, headers=h(tok))
    code = c.post("/v1/auth/email/start", json={"target": address}, headers=h(tok)).json()["dev_code"]
    r = c.post("/v1/auth/email/verify", json={"target": address, "code": code}, headers=h(tok))
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_google_with_the_same_email_opens_the_email_account(oidc_ctx, keys):  # noqa: F811
    key, _ = keys
    c = oidc_ctx.client
    owner = email_account(c, oidc_ctx, "ivan@gmail.com")
    device = new_token(c)  # another device: an anonymous visitor with a case
    c.post("/v1/cases", json={"text": STORY}, headers=h(device))
    r = google_login(c, key, device)  # Google says Ivan@Gmail.com, verified
    assert r.status_code == 200 and r.json()["token"] == owner
    assert len(c.get("/v1/cases", headers=h(owner)).json()) == 2  # nothing lost
    kinds = sorted(i["kind"] for i in r.json()["me"]["identities"])
    assert kinds == ["email", "google"]


def test_two_accounts_of_one_person_become_one(oidc_ctx, keys):  # noqa: F811
    """Before this fix Google made its own account (no e-mail identity) next to the e-mail one: the next Google
    sign-in joins them — the cases, bills and both sign-in ways end up in the account with the e-mail."""
    key, _ = keys
    c = oidc_ctx.client
    email_tok = email_account(c, oidc_ctx, "ivan@gmail.com")
    google_tok = new_token(c)
    c.post("/v1/cases", json={"text": STORY}, headers=h(google_tok))
    with oidc_ctx.container.session_factory() as s:  # the old state: a Google-only account
        u = s.scalar(select(User).where(User.api_token == google_tok))
        s.add(Identity(user_id=u.id, kind="google", subject_hash=oidc_ctx.container.identities.h("google", "g-1001"),
                       display="i•••@gmail.com"))
        s.commit()
    r = google_login(c, key, new_token(c))
    assert r.status_code == 200 and r.json()["token"] == email_tok
    assert len(c.get("/v1/cases", headers=h(email_tok)).json()) == 2
    with oidc_ctx.container.session_factory() as s:
        owner = s.scalar(select(User).where(User.api_token == email_tok))
        assert {i.kind for i in owner.identities} == {"email", "google"}
        old = s.scalar(select(User).where(User.api_token == google_tok))
        assert s.scalar(select(Case.id).where(Case.owner_id == old.id)) is None


def test_email_sign_in_brings_the_device_cases_and_other_ways(ctx):
    c = ctx.client
    owner = email_account(c, ctx, "aigerim@mail.kz")
    device = new_token(c)
    c.post("/v1/cases", json={"text": STORY}, headers=h(device))
    with ctx.container.session_factory() as s:  # this device had confirmed a phone before
        u = s.scalar(select(User).where(User.api_token == device))
        s.add(Identity(user_id=u.id, kind="phone", subject_hash=ctx.container.identities.h("phone", "+77015550000"),
                       display="+7 ••• 00 00"))
        s.commit()
    with ctx.container.session_factory() as s:  # the first code was asked for long ago (no «wait a minute»)
        for ch in s.scalars(select(LoginChallenge)):
            ch.created_at = ch.created_at - timedelta(minutes=5)
        s.commit()
    code = c.post("/v1/auth/email/start", json={"target": "aigerim@mail.kz"}, headers=h(device)).json()["dev_code"]
    r = c.post("/v1/auth/email/verify", json={"target": "aigerim@mail.kz", "code": code}, headers=h(device))
    assert r.json()["token"] == owner
    assert len(c.get("/v1/cases", headers=h(owner)).json()) == 2
    assert sorted(i["kind"] for i in r.json()["me"]["identities"]) == ["email", "phone"]


def test_smoke_email_returns_the_account_it_signed_into(ctx):
    ctx.settings.smoke_token = "smk"
    c = ctx.client
    first = c.post("/v1/smoke/user", headers={"X-Smoke-Token": "smk"}).json()["token"]
    a = c.post("/v1/smoke/email", json={"email": "qa@resend.dev"}, headers={**h(first), "X-Smoke-Token": "smk"}).json()
    assert a["token"] == first
    second = c.post("/v1/smoke/user", headers={"X-Smoke-Token": "smk"}).json()["token"]
    b = c.post("/v1/smoke/email", json={"email": "qa@resend.dev"}, headers={**h(second), "X-Smoke-Token": "smk"}).json()
    assert b["token"] == first  # the address belongs to the first account: switch to its token


def test_paid_document_shows_paid(ctx):
    """QA 01.10: after the paid document is given, the case says so — the document «Оплачено» and the last paid bill
    (payment.status stays about the NEXT document)."""
    from .test_payment import confirm, qualified_case
    from .test_lawyer_onboarding import Outbox
    ctx.container.email_sender = Outbox()
    api, cid = qualified_case(ctx)
    confirm(api, "email", "buyer@mail.kz")
    api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})  # stub: paid at once
    case = api.post(f"/v1/cases/{cid}/actions/next")["case"]
    assert case["actions"][0]["paid"] is True
    assert case["payment"]["last_paid"]["code"] and case["payment"]["last_paid"]["purpose"] == "document"
