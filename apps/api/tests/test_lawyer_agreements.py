"""Lawyers tied to ЭЦП, case assignment, consent + engagement signed by the customer and then the lawyer."""

from __future__ import annotations

import base64

import pytest
from docx import Document

from konsilier.identity.ncanode import SignatureError, Signer

from .test_e2e import Api, web_user

CUSTOMER_IIN, LAWYER_IIN, STRANGER_IIN = "900101300123", "800202400456", "700303500789"
ADM = {"X-Admin-Token": "adm"}


class Verifier:
    """cms = base64(b'SIGNED:<iin>:' + data): lets a test choose who signs."""

    def verify(self, cms_b64: str, expected: bytes) -> Signer:
        raw = base64.b64decode(cms_b64)
        head, _, rest = raw.partition(b"|")
        if not head.startswith(b"SIGNED:") or rest != expected:
            raise SignatureError("wrong_data")
        iin, key = head[7:].decode().split(":")
        return Signer(iin=iin, name=f"Person {iin[-4:]}", key_usage=key)


def cms(iin: str, data_b64: str, key: str = "SIGN") -> str:
    return base64.b64encode(f"SIGNED:{iin}:{key}|".encode() + base64.b64decode(data_b64)).decode()


def ecp_login(ctx, api: Api, iin: str) -> None:
    ch = api.post("/v1/auth/ecp/challenge")
    r = api.post("/v1/auth/ecp/verify", json={"nonce": ch["nonce"], "cms": cms(iin, ch["nonce"], "AUTH")})
    api.h = {"Authorization": f"Bearer {r['token']}"}


@pytest.fixture
def world(ctx):
    c = ctx.container
    c.signature_verifier = Verifier()
    # the AUTH login path accepts any key usage; documents require SIGN
    customer = web_user(ctx)
    cid = customer.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине, через неделю сломался, деньги не возвращают 150000", "country": "KZ"})["case"]["id"]
    lawyer = web_user(ctx)
    ecp_login(ctx, lawyer, LAWYER_IIN)
    app = lawyer.post("/v1/lawyer-applications", expect=201, json={
        "country": "KZ", "full_name": "Адвокат Тест", "kind": "advocate", "license_number": "12345",
        "contact": "+77010000000"})
    assert app["ecp_verified"] is True
    return ctx, customer, lawyer, cid, app["id"]


def admin(ctx, method: str, url: str, **kw):
    return getattr(ctx.client, method)(url, headers=ADM, **kw)


def test_verification_requires_ecp_application(ctx):
    anon = ctx.client.post("/v1/lawyer-applications", json={
        "country": "KZ", "full_name": "Без ЭЦП", "kind": "advocate", "contact": "x@y.kz"}).json()
    assert anon["ecp_verified"] is False
    r = admin(ctx, "post", f"/v1/admin/lawyer-applications/{anon['id']}/status", json={"status": "verified"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ecp_required"


def test_full_flow_customer_then_lawyer(world):
    ctx, customer, lawyer, cid, app_id = world
    # not yet verified → cannot be assigned, no cabinet
    assert admin(ctx, "post", f"/v1/admin/cases/{cid}/assign", json={"application_id": app_id}).status_code == 409
    assert ctx.client.get("/v1/lawyer/cases", headers=lawyer.h).status_code == 403
    assert admin(ctx, "post", f"/v1/admin/lawyer-applications/{app_id}/status", json={"status": "verified"}).status_code == 200
    listed = admin(ctx, "get", "/v1/admin/lawyer-applications").json()
    assert listed[0]["ecp_verified"] is True and listed[0]["ecp_name"] == "Person 0456"

    assigned = admin(ctx, "post", f"/v1/admin/cases/{cid}/assign", json={"application_id": app_id}).json()
    kinds = {a["kind"]: a for a in assigned["agreements"]}
    assert set(kinds) == {"consent", "engagement"}
    assert all(a["status"] == "awaiting_customer" and a["template_reviewed"] is False for a in kinds.values())

    # the lawyer sees the case in the cabinet; the customer sees the lawyer and the papers
    assert [c["id"] for c in lawyer.get("/v1/lawyer/cases").json()] == [cid]
    block = customer.get(f"/v1/cases/{cid}/lawyer").json()
    assert block["lawyer"]["name"] == "Person 0456"
    ag = kinds["engagement"]["id"]

    # the document is the pack template, filled, with the "unreviewed template" note
    doc = Document(__import__("io").BytesIO(customer.get(f"/v1/agreements/{ag}/document").content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Шаблон платформы" in text and "Person 0456" in text and "не является доверенностью" in text

    # lawyer cannot sign before the customer
    r = ctx.client.post(f"/v1/agreements/{ag}/sign/start", headers=lawyer.h, json={"method": "ncalayer"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "customer_first"

    s = customer.post(f"/v1/agreements/{ag}/sign/start", json={"method": "ncalayer"})
    out = customer.post(f"/v1/agreements/{ag}/sign", json={"session_id": s["session_id"], "cms": cms(CUSTOMER_IIN, s["data"])})
    assert out["status"] == "awaiting_lawyer" and out["signature"]["role"] == "applicant"

    # the lawyer must sign with the ЭЦП they registered with
    s = lawyer.post(f"/v1/agreements/{ag}/sign/start", json={"method": "ncalayer"})
    r = ctx.client.post(f"/v1/agreements/{ag}/sign", headers=lawyer.h,
                        json={"session_id": s["session_id"], "cms": cms(STRANGER_IIN, s["data"])})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "signer_mismatch"
    s = lawyer.post(f"/v1/agreements/{ag}/sign/start", json={"method": "ncalayer"})
    out = lawyer.post(f"/v1/agreements/{ag}/sign", json={"session_id": s["session_id"], "cms": cms(LAWYER_IIN, s["data"])})
    assert out["status"] == "signed"

    final = customer.get(f"/v1/cases/{cid}/lawyer").json()["agreements"]
    eng = next(a for a in final if a["kind"] == "engagement")
    assert [x["role"] for x in eng["signatures"]] == ["applicant", "lawyer"]
    sig_id = eng["signatures"][1]["id"]
    assert customer.get(f"/v1/agreements/{ag}/signatures/{sig_id}.cms").content.startswith(b"SIGNED:")


def test_customer_with_ecp_identity_must_sign_as_themselves(world):
    ctx, customer, lawyer, cid, app_id = world
    ecp_login(ctx, customer, CUSTOMER_IIN)  # same account keeps the case (identity is new)
    admin(ctx, "post", f"/v1/admin/lawyer-applications/{app_id}/status", json={"status": "verified"})
    ag = admin(ctx, "post", f"/v1/admin/cases/{cid}/assign", json={"application_id": app_id}).json()["agreements"][0]["id"]
    s = customer.post(f"/v1/agreements/{ag}/sign/start", json={"method": "ncalayer"})
    r = ctx.client.post(f"/v1/agreements/{ag}/sign", headers=customer.h,
                        json={"session_id": s["session_id"], "cms": cms(STRANGER_IIN, s["data"])})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "signer_mismatch"


def test_strangers_cannot_see_agreements(world):
    ctx, customer, lawyer, cid, app_id = world
    admin(ctx, "post", f"/v1/admin/lawyer-applications/{app_id}/status", json={"status": "verified"})
    ag = admin(ctx, "post", f"/v1/admin/cases/{cid}/assign", json={"application_id": app_id}).json()["agreements"][0]["id"]
    other = web_user(ctx)
    assert ctx.client.get(f"/v1/agreements/{ag}/document", headers=other.h).status_code == 404
    assert ctx.client.get(f"/v1/lawyer/cases/{cid}", headers=other.h).status_code == 403
    assert lawyer.get(f"/v1/lawyer/cases/{cid}").json()["id"] == cid
