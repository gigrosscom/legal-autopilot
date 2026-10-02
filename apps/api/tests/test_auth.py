"""Sign-in: e-mail/SMS codes, ЭЦП (NCANode mocked at the HTTP boundary), eGov Mobile QR, account linking."""

from __future__ import annotations

import base64
import re

import httpx
import pytest

from konsilier.identity import normalize as norm
from konsilier.identity.ncanode import NcaNode, SignatureError, Signer
from konsilier.identity.senders import LogSender
from konsilier.core.models import Identity, LoginChallenge

IIN = "900101300123"


class FakeVerifier:
    """Accepts a 'cms' that is base64 of b'SIGNED:' + data, signed by `iin`."""

    def __init__(self, iin: str = IIN):
        self.iin = iin

    def verify(self, cms_b64: str, expected: bytes) -> Signer:
        raw = base64.b64decode(cms_b64)
        if raw != b"SIGNED:" + expected:
            raise SignatureError("wrong_data")
        return Signer(iin=self.iin, name="Иванов Иван", key_usage="AUTH")


def fake_cms(nonce_b64: str) -> str:
    return base64.b64encode(b"SIGNED:" + base64.b64decode(nonce_b64)).decode()


@pytest.fixture
def auth(ctx):
    c = ctx.container
    c.email_sender, c.sms_sender, c.signature_verifier = LogSender("email"), LogSender("sms"), FakeVerifier()
    c.settings.egov_org_bin = "123456789012"
    c.settings.public_api_url = "https://api.example.kz"
    return ctx


def new_token(client) -> str:
    return client.post("/v1/users", json={"language": "ru"}).json()["token"]


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sent_code(sender: LogSender) -> str:
    return re.search(r"\b(\d{6})\b", sender.sent[-1][1]).group(1)


def test_methods_reflect_configuration(ctx, auth):
    assert auth.client.get("/v1/auth/methods").json() == {"email": True, "phone": True, "ecp": True, "egov": True,
                                                         "google": False, "apple": False}
    auth.container.signature_verifier = None
    assert auth.client.get("/v1/auth/methods").json()["ecp"] is False
    assert auth.client.get("/v1/auth/methods").json()["egov"] is False


def test_email_code_links_identity_and_masks_it(auth):
    c, tok = auth.client, new_token(auth.client)
    assert c.post("/v1/auth/email/start", json={"target": " Ivan@Mail.KZ "}, headers=h(tok)).status_code == 200
    code = sent_code(auth.container.email_sender)
    r = c.post("/v1/auth/email/verify", json={"target": "ivan@mail.kz", "code": code}, headers=h(tok)).json()
    assert r["token"] == tok
    assert r["me"]["identities"] == [{"kind": "email", "display": "i•••@mail.kz",
                                      "verified_at": r["me"]["identities"][0]["verified_at"]}]
    # the code works once
    again = c.post("/v1/auth/email/verify", json={"target": "ivan@mail.kz", "code": code}, headers=h(tok))
    assert again.status_code == 400


def test_wrong_code_attempts_are_limited_and_persisted(auth):
    c, tok = auth.client, new_token(auth.client)
    c.post("/v1/auth/phone/start", json={"target": "8 701 123 45 67"}, headers=h(tok))
    code = sent_code(auth.container.sms_sender)
    assert auth.container.sms_sender.sent[-1][0] == "+77011234567"
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = c.post("/v1/auth/phone/verify", json={"target": "+77011234567", "code": wrong}, headers=h(tok))
        assert r.json()["detail"]["code"] == "wrong_code"
    r = c.post("/v1/auth/phone/verify", json={"target": "+77011234567", "code": code}, headers=h(tok))
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_attempts"


def test_resend_is_throttled(auth):
    c, tok = auth.client, new_token(auth.client)
    assert c.post("/v1/auth/email/start", json={"target": "a@b.kz"}, headers=h(tok)).status_code == 200
    r = c.post("/v1/auth/email/start", json={"target": "a@b.kz"}, headers=h(tok))
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_soon"
    assert int(r.headers["Retry-After"]) > 0


def test_invalid_targets_and_disabled_methods(auth):
    c, tok = auth.client, new_token(auth.client)
    assert c.post("/v1/auth/email/start", json={"target": "not-an-email"}, headers=h(tok)).status_code == 400
    assert c.post("/v1/auth/phone/start", json={"target": "12"}, headers=h(tok)).status_code == 400
    auth.container.sms_sender = None
    r = c.post("/v1/auth/phone/start", json={"target": "+77011234567"}, headers=h(tok))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "method_unavailable"


def test_second_device_signs_into_existing_account_and_brings_its_cases(auth):
    c = auth.client
    first, second = new_token(c), new_token(c)
    c.post("/v1/auth/email/start", json={"target": "ivan@mail.kz"}, headers=h(first))
    c.post("/v1/auth/email/verify", json={"target": "ivan@mail.kz", "code": sent_code(auth.container.email_sender)},
           headers=h(first))
    case = c.post("/v1/cases", json={"text": "Купил телефон, сломался, магазин не возвращает деньги 150000"},
                  headers=h(second))
    assert case.status_code in (200, 201)
    # a new code for the same address must wait for the resend window: expire it in the DB
    with auth.container.session_factory() as s:
        for ch in s.query(LoginChallenge).all():
            ch.created_at = ch.created_at.replace(year=2000)
        s.commit()
    c.post("/v1/auth/email/start", json={"target": "ivan@mail.kz"}, headers=h(second))
    r = c.post("/v1/auth/email/verify", json={"target": "ivan@mail.kz",
                                              "code": sent_code(auth.container.email_sender)}, headers=h(second)).json()
    assert r["token"] == first
    mine = c.get("/v1/cases", headers=h(first)).json()
    assert len(mine) == 1


def test_ecp_sign_in_stores_no_iin(auth):
    c, tok = auth.client, new_token(auth.client)
    ch = c.post("/v1/auth/ecp/challenge", headers=h(tok)).json()
    bad = c.post("/v1/auth/ecp/verify", json={"nonce": ch["nonce"], "cms": fake_cms(base64.b64encode(b"x").decode())},
                 headers=h(tok))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "wrong_data"
    r = c.post("/v1/auth/ecp/verify", json={"nonce": ch["nonce"], "cms": fake_cms(ch["nonce"])}, headers=h(tok)).json()
    assert r["me"]["display_name"] == "Иванов Иван"
    assert r["me"]["identities"][0]["display"] == "••••••••0123"
    with auth.container.session_factory() as s:
        ident = s.query(Identity).one()
        assert IIN not in ident.subject_hash and IIN not in ident.display
        assert all(IIN not in str(x.result) for x in s.query(LoginChallenge).all())
    # the nonce is single-use
    again = c.post("/v1/auth/ecp/verify", json={"nonce": ch["nonce"], "cms": fake_cms(ch["nonce"])}, headers=h(tok))
    assert again.status_code == 400


def test_ecp_challenge_belongs_to_its_user(auth):
    c = auth.client
    a, b = new_token(c), new_token(c)
    ch = c.post("/v1/auth/ecp/challenge", headers=h(a)).json()
    r = c.post("/v1/auth/ecp/verify", json={"nonce": ch["nonce"], "cms": fake_cms(ch["nonce"])}, headers=h(b))
    assert r.status_code == 403


def test_egov_mobile_qr_flow_and_same_person_as_ecp(auth):
    c, laptop, phone = auth.client, new_token(auth.client), new_token(auth.client)
    ch = c.post("/v1/auth/ecp/challenge", headers=h(laptop)).json()
    c.post("/v1/auth/ecp/verify", json={"nonce": ch["nonce"], "cms": fake_cms(ch["nonce"])}, headers=h(laptop))

    start = c.post("/v1/auth/egov/start", headers=h(phone)).json()
    assert start["qr"] == f"mobileSign:https://api.example.kz/v1/auth/egov/mgov/{start['id']}"
    assert c.get(f"/v1/auth/egov/status/{start['id']}", headers=h(phone)).json() == {"status": "pending"}
    api1 = c.get(f"/v1/auth/egov/mgov/{start['id']}").json()
    assert api1["organisation"]["bin"] == "123456789012"
    # eGov Mobile API №1: auth_type None needs an empty auth_token; expiry with milliseconds and an offset
    assert api1["document"]["auth_type"] == "None" and api1["document"]["auth_token"] == ""
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00", api1["expiry_date"])
    doc_path = api1["document"]["uri"].replace("https://api.example.kz", "")
    api2 = c.get(doc_path).json()
    assert api2["signMethod"] == "CMS_WITH_DATA"
    doc = api2["documentsToSign"][0]
    # API №2: the data to sign is document.file.data (base64), not a ready CMS in documentCms
    assert "documentCms" not in doc and doc["document"]["file"]["mime"] == "text/plain"
    doc["document"]["file"]["data"] = fake_cms(doc["document"]["file"]["data"])
    assert c.put(doc_path, json=api2).json() == []
    done = c.get(f"/v1/auth/egov/status/{start['id']}", headers=h(phone)).json()
    assert done["status"] == "done" and done["token"] == laptop  # same IIN → same account
    assert c.get(f"/v1/auth/egov/status/{start['id']}", headers=h(phone)).json() == {"status": "used"}


def test_egov_mobile_cancel_is_not_a_sign_in(auth):
    c, phone = auth.client, new_token(auth.client)
    start = c.post("/v1/auth/egov/start", headers=h(phone)).json()
    doc_path = f"/v1/auth/egov/mgov/{start['id']}/document"
    api2 = c.get(doc_path).json()
    r = c.put(doc_path, json={**api2, "status": "CANCELED", "version": 1})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "canceled"
    assert c.get(f"/v1/auth/egov/status/{start['id']}", headers=h(phone)).json() == {"status": "pending"}


def test_me_requires_token(auth):
    assert auth.client.get("/v1/me").status_code == 401


# ------------------------------------------------------------------ NCANode client against a mocked HTTP API
def test_ncanode_parses_signer_and_checks_data(monkeypatch):
    nonce = b"konsilier-auth:abc"
    subject = {"iin": IIN, "commonName": "ИВАНОВ ИВАН", "surName": "ИВАНОВИЧ"}
    ok = {"status": 200, "valid": True, "signers": [{"certificates": [{"valid": True, "keyUsage": "AUTH",
                                                                         "subject": subject}]}]}
    calls = []

    def fake_post(url, json, timeout):
        calls.append(url)
        if url.endswith("/cms/verify"):
            return httpx.Response(200, json=ok)
        return httpx.Response(200, json={"status": 200, "data": base64.b64encode(nonce).decode()})

    monkeypatch.setattr(httpx, "post", fake_post)
    signer = NcaNode("http://ncanode:14579").verify("Q01T", nonce)
    assert signer == Signer(iin=IIN, name="Иванов Иван", key_usage="AUTH")
    assert calls == ["http://ncanode:14579/cms/verify", "http://ncanode:14579/cms/extract"]

    def other_data(url, json, timeout):
        if url.endswith("/cms/verify"):
            return httpx.Response(200, json=ok)
        return httpx.Response(200, json={"data": base64.b64encode(b"other").decode()})

    monkeypatch.setattr(httpx, "post", other_data)
    with pytest.raises(SignatureError, match="wrong_data"):
        NcaNode("http://ncanode:14579").verify("Q01T", nonce)

    def invalid(url, json, timeout):
        return httpx.Response(200, json={**ok, "valid": False})

    monkeypatch.setattr(httpx, "post", invalid)
    with pytest.raises(SignatureError, match="invalid_signature"):
        NcaNode("http://ncanode:14579").verify("Q01T", nonce)

    def down(url, json, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", down)
    with pytest.raises(SignatureError, match="verifier_unavailable"):
        NcaNode("http://ncanode:14579").verify("Q01T", nonce)


# NCANode 3.5 answers recorded per failure mode (shapes from its CmsVerificationResponse); the subject is fake.
def _nca(valid, status="VALID", sub=None, revocations=None, not_after="2027-03-01T00:00:00.000+00:00", cert_valid=None):
    cert = {"valid": valid if cert_valid is None else cert_valid, "keyUsage": "AUTH",
            "notBefore": "2026-03-01T00:00:00.000+00:00", "notAfter": not_after,
            "signAlg": "SHA256withRSA", "issuer": {"commonName": "ҰЛТТЫҚ КУӘЛАНДЫРУШЫ ОРТАЛЫҚ (RSA) 2022"},
            "subject": {"iin": IIN, "commonName": "ИВАНОВ ИВАН"},
            "revocations": revocations if revocations is not None else [{"revoked": False, "by": "OCSP", "reason": "OK"}]}
    signer = {"certificates": [cert], "status": status, "adesLevel": "T", "tsp": {"genTime": "2026-10-01"}}
    if sub:
        signer |= {"subIndication": sub, "message": "details"}
    return {"status": 200, "message": "OK", "valid": valid, "signers": [signer]}


NO_ROOT = [{"revoked": False, "by": "OCSP",
            "reason": "Cannot find root certificate in NCANode. Try add it using NCANODE_CA_URL variable."},
           {"revoked": False, "by": "CRL", "reason": None}]


@pytest.mark.parametrize("answer, code", [
    (_nca(False, "INDETERMINATE", "CHAIN_INCOMPLETE", NO_ROOT), "chain"),  # 01.10: RSA 2022 key, CA not in NCANode
    (_nca(False, "INVALID", "CERT_REVOKED", [{"revoked": True, "by": "OCSP", "reason": "revoked"}]), "revoked"),
    (_nca(False, "INDETERMINATE", "REVOCATION_DATA_MISSING",
          [{"revoked": False, "by": "OCSP", "reason": "Connect timed out"}]), "ocsp_unavailable"),
    (_nca(False, "INDETERMINATE", "OUT_OF_BOUNDS_NO_POE", not_after="2025-01-01T00:00:00.000+00:00"), "expired"),
    (_nca(False, "INVALID", "SIG_CRYPTO_FAILURE"), "data_mismatch"),
    ({**_nca(False, "INDETERMINATE", None, NO_ROOT), "signers": [{"certificates": [
        {"valid": False, "revocations": NO_ROOT, "subject": {"iin": IIN}}]}]}, "chain"),  # NCANode before 3.5
    ({"status": 400, "message": "NoSuchAlgorithmException: unknown algorithm 1.2.398.3.10.1.1.2.3.2"},
     "unsupported_alg"),
])
def test_ncanode_failure_reasons_are_mapped_and_logged_without_personal_data(monkeypatch, caplog, answer, code):
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: httpx.Response(200, json=answer))
    with caplog.at_level("WARNING"), pytest.raises(SignatureError) as e:
        NcaNode("http://ncanode:14579").verify("Q01T", b"nonce")
    assert e.value.code == code
    line = caplog.text
    assert "ecp verify failed reason=" + code in line
    assert IIN not in line and "ИВАНОВ" not in line  # no IIN, no name, no subject in the log
    if answer.get("signers") and answer["signers"][0].get("status"):
        assert "(RSA) 2022" in line and "notAfter" in line  # the issuing CA and dates are there for diagnosis


def test_ncanode_accepts_crl_when_ocsp_is_unreachable(monkeypatch):
    """OCSP and CRL are both asked for; NCANode grades the signer VALID when CRL says good and OCSP did not answer,
    while the certificate's own flag (it wants every source) stays false — the signer's grade decides."""
    answer = _nca(True, revocations=[{"revoked": False, "by": "OCSP", "reason": "Connect timed out"},
                                     {"revoked": False, "by": "CRL", "reason": None}], cert_valid=False)
    bodies = []

    def fake_post(url, json, timeout):
        bodies.append(json)
        if url.endswith("/cms/verify"):
            return httpx.Response(200, json=answer)
        return httpx.Response(200, json={"data": base64.b64encode(b"nonce").decode()})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert NcaNode("http://ncanode:14579").verify("Q01T", b"nonce").iin == IIN
    assert bodies[0]["revocationCheck"] == ["OCSP", "CRL"]


def test_ncanode_detached_signature_is_checked_with_our_data(monkeypatch):
    bodies = []

    def fake_post(url, json, timeout):
        bodies.append((url, json))
        if "data" not in json:  # detached CMS without the data: NCANode cannot check it
            return httpx.Response(400, json={"status": 400, "message": "CMS has no content"})
        return httpx.Response(200, json=_nca(True))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert NcaNode("http://ncanode:14579").verify("Q01T", b"nonce").key_usage == "AUTH"
    assert bodies[1][1]["data"] == base64.b64encode(b"nonce").decode()
    assert [u for u, _ in bodies] == ["http://ncanode:14579/cms/verify"] * 2  # no /cms/extract for detached


def test_ncanode_self_check_line(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen["url"], seen["body"] = url, json
        return httpx.Response(200, json={"valid": True, "signers": [{"valid": True, "revocations": [
            {"revoked": False, "by": "OCSP", "reason": "OK"}, {"revoked": False, "by": "CRL", "reason": None}]}]})

    def fake_get(url, timeout):
        if url.endswith("/actuator/health"):
            return httpx.Response(200, json={"status": "UP", "components": {"ca": {"status": "UP"},
                                                                            "crl": {"status": "UP"}}})
        return httpx.Response(200, text="<title>NCANode v3.5.0</title>")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    assert NcaNode("http://ncanode:14579").self_check() == (
        "ncanode=v3.5.0 health=UP(ca:UP,crl:UP) rsa2022=ok rev=[OCSP:OK,CRL:good]")
    assert seen["url"].endswith("/x509/info") and seen["body"]["revocationCheck"] == ["OCSP", "CRL"]
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: httpx.Response(200, json={
        "valid": False, "signers": [{"valid": False, "revocations": NO_ROOT[:1]}]}))
    assert "rsa2022=FAIL rev=[OCSP:Cannot_find_root" in NcaNode("http://ncanode:14579").self_check()


def test_normalizers():
    assert norm.phone("8 (701) 123-45-67") == "+77011234567"
    assert norm.phone("7011234567") == "+77011234567"
    assert norm.phone("+90 532 123 45 67") == "+905321234567"
    assert norm.mask_phone("+77011234567") == "+7•••••4567"
    assert norm.email(" A@B.kz ") == "a@b.kz"
    with pytest.raises(norm.InvalidIdentifier):
        norm.iin("123")
