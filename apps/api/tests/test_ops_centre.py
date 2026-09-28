"""Operations centre: the lawyers desk sees lawyer applications, the clients desk sees client questions,
complaints, suggestions and lawyer requests; only operators with a verified desk e-mail get in."""

from __future__ import annotations

from sqlalchemy import select

from konsilier.core.models import User

from .test_e2e import web_user
from .test_lawyer_onboarding import APP, Outbox


def operator(ctx, email: str):
    api = web_user(ctx)
    with ctx.container.session_factory() as s:
        u = s.scalar(select(User).where(User.api_token == api.h["Authorization"].split()[1]))
        ctx.container.identities.link_or_login(s, u, "email", email, email)
        s.commit()
    return api


def test_two_desks(ctx):
    st = ctx.container.settings
    st.ops_lawyers_emails, st.ops_clients_emails = "lawyers@konsilier.com", "support@konsilier.com"
    outbox = Outbox()
    ctx.container.email_sender = outbox

    # a lawyer applies → the lawyers desk is e-mailed
    lawyer = web_user(ctx)
    app_id = lawyer.post("/v1/lawyer-applications", expect=201, json=APP)["id"]
    assert outbox.sent[-1][0] == "lawyers@konsilier.com"

    # a client writes a complaint → the clients desk is e-mailed
    client = web_user(ctx)
    t = client.post("/v1/support", expect=201, json={"kind": "complaint", "text": "Документ не скачивается",
                                                     "email": "client@mail.kz"})
    assert outbox.sent[-1][0] == "support@konsilier.com" and "Жалоба" in outbox.sent[-1][1]
    assert ctx.client.post("/v1/support", headers=client.h, json={"kind": "question", "text": "без контакта"}).status_code == 422

    lw = operator(ctx, "lawyers@konsilier.com")
    cl = operator(ctx, "support@konsilier.com")
    assert lw.get("/v1/ops/me").json()["desks"] == ["lawyers"]
    assert cl.get("/v1/ops/me").json() == {"email": "support@konsilier.com", "desks": ["clients"], "new": {"clients": 1}}
    # each desk only its own inbox; ordinary users none
    assert ctx.client.get("/v1/ops/clients/tickets", headers=lw.h).status_code == 403
    assert ctx.client.get("/v1/ops/lawyers/applications", headers=client.h).status_code == 403

    apps = lw.get("/v1/ops/lawyers/applications?status=new").json()
    assert apps[0]["id"] == app_id and apps[0]["ecp_verified"] is False
    # cannot verify without ЭЦП; a note and a rejection work
    assert ctx.client.post(f"/v1/ops/lawyers/applications/{app_id}", headers=lw.h, json={"status": "verified"}).status_code == 409
    out = lw.post(f"/v1/ops/lawyers/applications/{app_id}", json={"note": "Позвонили, ждём ЭЦП"})
    assert out["note"] == "Позвонили, ждём ЭЦП"

    # the clients desk answers; the client gets it by e-mail and on the site
    ans = cl.post(f"/v1/ops/clients/tickets/{t['id']}/reply", json={"text": "Исправили, попробуйте ещё раз."})
    assert ans["status"] == "in_progress" and ans["messages"][-1]["author"] == "desk"
    assert outbox.sent[-1][0] == "client@mail.kz" and "Исправили" in outbox.sent[-1][2]
    mine = client.get("/v1/support").json()
    assert mine[0]["messages"][-1]["text"] == "Исправили, попробуйте ещё раз."
    assert any("Исправили" in n["text"] for n in client.get("/v1/notifications").json())
    client.post(f"/v1/support/{t['id']}/messages", expect=201, json={"text": "Спасибо, работает"})
    assert cl.post(f"/v1/ops/clients/tickets/{t['id']}/status", json={"status": "done"})["status"] == "done"
