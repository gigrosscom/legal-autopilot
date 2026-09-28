"""«Обратиться»: the case is registered together with the applicant's contacts for a lawyer."""

from __future__ import annotations


def test_request_registers_case_and_contacts(ctx):
    from .test_e2e import web_user

    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Работодатель не выплатил зарплату за три месяца",
                                                  "country": "KZ"})["case"]["id"]
    body = {"lawyer_ref": "demo-1", "full_name": "Асем Серикова", "phone": "+7 (701) 234-56-78",
            "email": "asem@mail.kz", "consent": True}
    out = api.post(f"/v1/cases/{cid}/lawyer-request", expect=201, json=body)
    assert out["status"] == "new" and out["case_id"] == cid
    admin = ctx.client.get("/v1/admin/lawyer-requests", headers={"X-Admin-Token": ctx.container.settings.admin_token}).json()
    assert admin[0]["phone"] == "+77012345678" and admin[0]["lawyer_ref"] == "demo-1"
    assert ctx.client.get("/v1/admin/lawyer-requests").status_code == 403

    assert ctx.client.post(f"/v1/cases/{cid}/lawyer-request", headers=api.h, json={**body, "consent": False}).status_code == 422
    assert ctx.client.post(f"/v1/cases/{cid}/lawyer-request", headers=api.h, json={**body, "phone": "12-34-56"}).status_code == 422
    other = web_user(ctx)
    assert ctx.client.post(f"/v1/cases/{cid}/lawyer-request", headers=other.h, json=body).status_code == 404


def test_terms_acceptance_is_recorded_with_the_case(ctx):
    from sqlalchemy import select

    from konsilier.core.models import Consent

    from .test_e2e import web_user

    api = web_user(ctx)
    a = api.post("/v1/cases", expect=201, json={"text": "Не вернули деньги за товар", "country": "KZ",
                                                "accept_terms": "2026-09-28"})["case"]["id"]
    b = api.post("/v1/cases", expect=201, json={"text": "Не вернули деньги за товар", "country": "KZ",
                                                "accept_terms": True})["case"]["id"]
    c = api.post("/v1/cases", expect=201, json={"text": "Не вернули деньги за товар", "country": "KZ"})["case"]["id"]
    with ctx.container.session_factory() as s:
        kinds = {str(x.case_id): x.kind for x in s.scalars(select(Consent)).all() if x.kind.startswith("terms:")}
    assert kinds[a] == "terms:2026-09-28" and kinds[b] == f"terms:{ctx.container.settings.terms_version}"
    assert c not in kinds
