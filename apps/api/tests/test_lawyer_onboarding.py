"""A lawyer who applies before confirming ЭЦП is not stuck: the application follows the account, gets the
certificate identity once ЭЦП is confirmed, and the team is told about every new application."""

from __future__ import annotations

from sqlalchemy import select

from konsilier.core.models import LawyerApplication, User

from .test_e2e import web_user


class Outbox:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, text):
        self.sent.append((to, subject, text))


APP = {"full_name": "Айгерим Нурланова", "kind": "advocate", "organization": "Коллегия адвокатов г. Алматы",
       "license_number": "12345", "city": "Алматы", "contact": "aigerim@mail.kz", "message": "",
       "country": "KZ", "specializations": ["consumer"], "wants_expert": True}


def test_application_follows_account_and_gets_ecp_identity(ctx):
    outbox = Outbox()
    ctx.container.email_sender = outbox
    anon = web_user(ctx)
    out = anon.post("/v1/lawyer-applications", expect=201, json=APP)
    # the team hears about it
    assert outbox.sent and outbox.sent[0][0] == ctx.container.settings.team_email
    assert "Айгерим Нурланова" in outbox.sent[0][1] and "ещё нет" in outbox.sent[0][2]
    # the application belongs to this browser's account and shows in the cabinet at once
    me = anon.get("/v1/lawyer/me").json()
    assert me["applications"][0]["id"] == out["id"] and me["has_ecp"] is False

    # the lawyer confirms ЭЦП; the certificate already belongs to an account → sign into it, application moves
    ids = ctx.container.identities
    with ctx.container.session_factory() as s:
        existing = User(language="ru")
        s.add(existing)
        s.flush()
        ids.link_or_login(s, existing, "iin", "880101300123", "••••0123", name="НУРЛАНОВА АЙГЕРИМ")
        anon_user = s.scalar(select(User).where(User.api_token == anon.h["Authorization"].split()[1]))
        owner = ids.link_or_login(s, anon_user, "iin", "880101300123", "••••0123", name="НУРЛАНОВА АЙГЕРИМ")
        s.commit()
        token = owner.api_token
    me = ctx.client.get("/v1/lawyer/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["has_ecp"] is True and me["applications"][0]["id"] == out["id"]
    with ctx.container.session_factory() as s:
        app_row = s.get(LawyerApplication, out["id"])
        assert app_row.iin_hash and app_row.ecp_name == "НУРЛАНОВА АЙГЕРИМ"
