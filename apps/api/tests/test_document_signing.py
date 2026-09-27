"""ЭЦП signatures over prepared documents: NCALayer and eGov Mobile, key usage, signer match, e-mail attachment."""

from __future__ import annotations

import base64
import hashlib

import pytest

from konsilier.core.models import DocumentSignature
from konsilier.identity.ncanode import SignatureError, Signer

from .test_e2e import web_user

IIN = "900101300123"


class FakeVerifier:
    """cms = base64(b'SIGNED:' + data); key usage and IIN configurable."""

    def __init__(self, iin: str = IIN, key_usage: str = "SIGN"):
        self.iin, self.key_usage = iin, key_usage

    def verify(self, cms_b64: str, expected: bytes) -> Signer:
        if base64.b64decode(cms_b64) != b"SIGNED:" + expected:
            raise SignatureError("wrong_data")
        return Signer(iin=self.iin, name="Иванов Иван", key_usage=self.key_usage)


def sign(data_b64: str) -> str:
    return base64.b64encode(b"SIGNED:" + base64.b64decode(data_b64)).decode()


@pytest.fixture
def ready(ctx):
    """A case in the test pack with its first document ready."""
    c = ctx.container
    c.engine.config.approval_required_first_n = 0
    c.signature_verifier = FakeVerifier()
    c.settings.egov_org_bin = "123456789012"
    c.settings.public_api_url = "https://api.example.kz"
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "My dummy widget was never delivered", "country": "XX",
                                                  "language": "en"})["case"]["id"]
    api.answer(cid, "Widget Corp")
    api.answer(cid, "1200")
    action = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert action["status"] == "ready"
    return ctx, api, cid, action["id"]


def test_ncalayer_signature_is_verified_stored_and_downloadable(ready):
    ctx, api, cid, aid = ready
    start = api.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", json={"method": "ncalayer"})
    data = base64.b64decode(start["data"])
    assert hashlib.sha256(data).hexdigest() == start["sha256"]
    out = api.post(f"/v1/cases/{cid}/actions/{aid}/sign", json={"session_id": start["session_id"],
                                                               "cms": sign(start["data"])})
    sig = out["signature"]
    assert sig["signer_name"] == "Иванов Иван" and sig["display"] == "••••••••0123" and sig["method"] == "ncalayer"
    view = api.get(f"/v1/cases/{cid}").json()
    assert view["actions"][0]["signatures"][0]["id"] == sig["id"]
    cms = api.get(f"/v1/cases/{cid}/actions/{aid}/signatures/{sig['id']}.cms")
    assert cms.content == b"SIGNED:" + data
    assert ".cms" in cms.headers["content-disposition"]
    with ctx.container.session_factory() as s:
        row = s.query(DocumentSignature).one()
        assert IIN not in row.display and IIN not in row.subject_hash
    # the signing session is single-use
    again = ctx.client.post(f"/v1/cases/{cid}/actions/{aid}/sign", headers=api.h,
                            json={"session_id": start["session_id"], "cms": sign(start["data"])})
    assert again.status_code == 400


def test_auth_key_is_rejected_for_documents(ready):
    ctx, api, cid, aid = ready
    ctx.container.signature_verifier = FakeVerifier(key_usage="AUTH")
    start = api.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", json={"method": "ncalayer"})
    r = ctx.client.post(f"/v1/cases/{cid}/actions/{aid}/sign", headers=api.h,
                        json={"session_id": start["session_id"], "cms": sign(start["data"])})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "use_sign_key"


def test_signer_must_be_the_applicant_when_iin_is_known(ready):
    ctx, api, cid, aid = ready
    from konsilier.core.models import Case
    with ctx.container.session_factory() as s:
        case = s.get(Case, __import__("uuid").UUID(cid))
        case.facts = {**case.facts, "applicant_iin": "850202400456"}
        s.commit()
    start = api.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", json={"method": "ncalayer"})
    r = ctx.client.post(f"/v1/cases/{cid}/actions/{aid}/sign", headers=api.h,
                        json={"session_id": start["session_id"], "cms": sign(start["data"])})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "signer_mismatch"


def test_other_users_cannot_use_the_session(ready):
    ctx_, api, cid, aid = ready
    start = api.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", json={"method": "ncalayer"})
    other = web_user(ctx_)
    r = ctx_.client.post(f"/v1/cases/{cid}/actions/{aid}/sign", headers=other.h,
                         json={"session_id": start["session_id"], "cms": sign(start["data"])})
    assert r.status_code == 404


def test_egov_mobile_signs_the_document(ready):
    ctx, api, cid, aid = ready
    start = api.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", json={"method": "egov"})
    sid = start["session_id"]
    assert start["qr"] == f"mobileSign:https://api.example.kz/v1/auth/egov/mgov/{sid}"
    status = f"/v1/cases/{cid}/actions/{aid}/sign/status/{sid}"
    assert api.get(status).json() == {"status": "pending"}
    api1 = ctx.client.get(f"/v1/auth/egov/mgov/{sid}").json()
    assert "Подписание" in api1["description"]
    doc_path = api1["document"]["uri"].replace("https://api.example.kz", "")
    api2 = ctx.client.get(doc_path).json()
    doc = api2["documentsToSign"][0]
    assert doc["meta"][0]["value"] == start["sha256"]
    doc["documentCms"] = sign(doc["documentCms"])
    assert ctx.client.put(doc_path, json=api2).json() == []
    done = api.get(status).json()
    assert done["status"] == "done" and done["signature"]["method"] == "egov"


def test_egov_failure_is_reported_to_the_page(ready):
    ctx, api, cid, aid = ready
    ctx.container.signature_verifier = FakeVerifier(key_usage="AUTH")
    start = api.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", json={"method": "egov"})
    sid = start["session_id"]
    doc_path = f"/v1/auth/egov/mgov/{sid}/document"
    api2 = ctx.client.get(doc_path).json()
    api2["documentsToSign"][0]["documentCms"] = sign(api2["documentsToSign"][0]["documentCms"])
    assert ctx.client.put(doc_path, json=api2).status_code == 400
    assert api.get(f"/v1/cases/{cid}/actions/{aid}/sign/status/{sid}").json() == {"status": "failed",
                                                                                 "code": "use_sign_key"}


def test_signing_is_off_without_a_verifier(ready):
    ctx, api, cid, aid = ready
    ctx.container.signature_verifier = None
    r = ctx.client.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", headers=api.h, json={"method": "ncalayer"})
    assert r.status_code == 503


def test_signed_file_goes_with_the_email(ready):
    ctx, api, cid, aid = ready
    sent = []

    class Mail:
        name = "email"

        def submit(self, **kw):
            sent.append(kw)
            from konsilier.core.adapters.submission import SubmissionResult
            return SubmissionResult(via="email")

    ctx.container.engine.submissions["email"] = Mail()
    spec = ctx.container.packs.scenario("xx.test.dummy").actions[0]
    object.__setattr__(spec, "channel", "email_or_user_submits")  # the fixture scenario is user_submits only
    start = api.post(f"/v1/cases/{cid}/actions/{aid}/sign/start", json={"method": "ncalayer"})
    api.post(f"/v1/cases/{cid}/actions/{aid}/sign", json={"session_id": start["session_id"], "cms": sign(start["data"])})
    r = ctx.client.post(f"/v1/cases/{cid}/actions/{aid}/submitted", headers=api.h, json={"via": "email"})
    assert r.status_code == 200, r.text
    names = [a[0] for a in sent[0]["attachments"]]
    assert any(n.endswith(".cms") for n in names)
