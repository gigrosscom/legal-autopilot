"""«Войти через Google» / «Войти через Apple»: ID tokens signed by a test RSA key served as a fake JWKS."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from konsilier.core.models import Identity
from konsilier.identity import oidc

GOOGLE_ID = "123-test.apps.googleusercontent.com"
APPLE_ID = "com.konsilier.web"
KID = "test-key"


@pytest.fixture
def keys(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid=KID, alg="RS256", use="sig")
    fetched: list[str] = []

    def fake_fetch(url: str) -> dict:
        fetched.append(url)
        return {"keys": [jwk]}

    oidc.clear_cache()
    monkeypatch.setattr(oidc, "fetch_jwks", fake_fetch)
    yield key, fetched
    oidc.clear_cache()


@pytest.fixture
def oidc_ctx(ctx):
    ctx.settings.google_client_id = GOOGLE_ID
    ctx.settings.apple_services_id = APPLE_ID
    ctx.settings.public_site_url = "https://konsilier.com"
    return ctx


def new_token(client) -> str:
    return client.post("/v1/users", json={"language": "ru"}).json()["token"]


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sign(key, kid: str = KID, **claims) -> str:
    now = int(time.time())
    body = {"iat": now, "exp": now + 600, **claims}
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": kid})


def google_claims(raw_nonce: str, **over) -> dict:
    return {"iss": "https://accounts.google.com", "aud": GOOGLE_ID, "sub": "g-1001", "email": "Ivan@Gmail.com",
            "email_verified": True, "name": "Иван Петров", "nonce": raw_nonce, **over}


def apple_claims(raw_nonce: str, **over) -> dict:
    return {"iss": "https://appleid.apple.com", "aud": APPLE_ID, "sub": "001234.abc.0999",
            "email": "x7k2@privaterelay.appleid.com", "email_verified": "true", "is_private_email": "true",
            "nonce": oidc.sha256_hex(raw_nonce), **over}


def google_login(client, key, tok: str, **over):
    nonce = client.post("/v1/auth/google/start", headers=h(tok)).json()["nonce"]
    cred = sign(key, **google_claims(nonce, **over))
    return client.post("/v1/auth/google/verify", json={"credential": cred, "nonce": nonce}, headers=h(tok))


def test_methods_hidden_when_not_configured(ctx):
    m = ctx.client.get("/v1/auth/methods").json()
    assert m["google"] is False and m["apple"] is False
    tok = new_token(ctx.client)
    for kind in ("google", "apple"):
        r = ctx.client.post(f"/v1/auth/{kind}/start", headers=h(tok))
        assert r.status_code == 503 and r.json()["detail"]["code"] == "method_unavailable"


def test_methods_shown_when_configured(oidc_ctx):
    m = oidc_ctx.client.get("/v1/auth/methods").json()
    assert m["google"] is True and m["apple"] is True


def test_google_login_creates_identity_and_signs_in(oidc_ctx, keys):
    key, fetched = keys
    c, tok = oidc_ctx.client, new_token(oidc_ctx.client)
    start = c.post("/v1/auth/google/start", headers=h(tok)).json()
    assert start["client_id"] == GOOGLE_ID
    cred = sign(key, **google_claims(start["nonce"]))
    r = c.post("/v1/auth/google/verify", json={"credential": cred, "nonce": start["nonce"]}, headers=h(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"] == tok
    assert body["me"]["display_name"] == "Иван Петров"
    assert [(i["kind"], i["display"]) for i in body["me"]["identities"]] == [("google", "i•••@gmail.com")]
    # the nonce works once
    again = c.post("/v1/auth/google/verify", json={"credential": cred, "nonce": start["nonce"]}, headers=h(tok))
    assert again.status_code == 400 and again.json()["detail"]["code"] == "challenge_expired"
    # keys are cached: one download for both calls
    assert fetched == [oidc.GOOGLE_JWKS]


def test_second_google_login_with_same_sub_returns_same_user(oidc_ctx, keys):
    key, _ = keys
    c = oidc_ctx.client
    first = new_token(c)
    assert google_login(c, key, first).status_code == 200
    # another device, another anonymous visitor, a case started before signing in
    second = new_token(c)
    case = c.post("/v1/cases", json={"text": "Купил телефон, сломался, магазин не возвращает деньги 150000"},
                  headers=h(second))
    assert case.status_code in (200, 201)
    r = google_login(c, key, second, email="other@gmail.com")
    assert r.status_code == 200
    assert r.json()["token"] == first
    with oidc_ctx.container.session_factory() as s:
        assert s.query(Identity).filter_by(kind="google").count() == 1
    assert len(c.get("/v1/cases", headers=h(first)).json()) == 1  # the case moved to the account


@pytest.mark.parametrize("over, code", [
    ({"aud": "someone-else.apps.googleusercontent.com"}, "invalid_token"),
    ({"iss": "https://evil.example.com"}, "invalid_token"),
    ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}, "token_expired"),
    ({"nonce": "not-our-nonce"}, "wrong_nonce"),
    ({"email_verified": False}, "email_not_verified"),
])
def test_google_bad_tokens_are_rejected(oidc_ctx, keys, over, code):
    key, _ = keys
    tok = new_token(oidc_ctx.client)
    r = google_login(oidc_ctx.client, key, tok, **over)
    assert r.status_code == 400 and r.json()["detail"]["code"] == code
    with oidc_ctx.container.session_factory() as s:
        assert s.query(Identity).count() == 0


def test_google_token_signed_by_another_key_is_rejected(oidc_ctx, keys):
    c, tok = oidc_ctx.client, new_token(oidc_ctx.client)
    nonce = c.post("/v1/auth/google/start", headers=h(tok)).json()["nonce"]
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cred = sign(stranger, **google_claims(nonce))
    r = c.post("/v1/auth/google/verify", json={"credential": cred, "nonce": nonce}, headers=h(tok))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_token"
    cred = sign(stranger, kid="unknown", **google_claims(nonce))
    r = c.post("/v1/auth/google/verify", json={"credential": cred, "nonce": nonce}, headers=h(tok))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_token"


def test_nonce_of_another_visitor_is_refused(oidc_ctx, keys):
    key, _ = keys
    c = oidc_ctx.client
    victim, attacker = new_token(c), new_token(c)
    nonce = c.post("/v1/auth/google/start", headers=h(victim)).json()["nonce"]
    cred = sign(key, **google_claims(nonce))
    r = c.post("/v1/auth/google/verify", json={"credential": cred, "nonce": nonce}, headers=h(attacker))
    assert r.status_code == 403


def test_apple_login_with_hashed_nonce(oidc_ctx, keys):
    key, _ = keys
    c, tok = oidc_ctx.client, new_token(oidc_ctx.client)
    start = c.post("/v1/auth/apple/start", headers=h(tok)).json()
    assert start["client_id"] == APPLE_ID and start["redirect_uri"] == "https://konsilier.com/account"
    assert start["nonce_sha256"] == oidc.sha256_hex(start["nonce"])
    token = sign(key, **apple_claims(start["nonce"]))
    r = c.post("/v1/auth/apple/verify", json={"id_token": token, "nonce": start["nonce"], "name": "Анна Сергеевна"},
               headers=h(tok))
    assert r.status_code == 200, r.text
    me = r.json()["me"]
    assert me["display_name"] == "Анна Сергеевна"
    assert [(i["kind"], i["display"]) for i in me["identities"]] == [("apple", "x•••@privaterelay.appleid.com")]
    # a second sign-in (Apple sends no e-mail and no name then) finds the same account
    other = new_token(c)
    start = c.post("/v1/auth/apple/start", headers=h(other)).json()
    token = sign(key, **apple_claims(start["nonce"], email=None))
    r = c.post("/v1/auth/apple/verify", json={"id_token": token, "nonce": start["nonce"]}, headers=h(other))
    assert r.status_code == 200 and r.json()["token"] == tok


@pytest.mark.parametrize("over, code", [
    ({"aud": "com.other.app"}, "invalid_token"),
    ({"iss": "https://accounts.google.com"}, "invalid_token"),
    ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}, "token_expired"),
    ({"nonce": "raw"}, "wrong_nonce"),
])
def test_apple_bad_tokens_are_rejected(oidc_ctx, keys, over, code):
    key, _ = keys
    c, tok = oidc_ctx.client, new_token(oidc_ctx.client)
    nonce = c.post("/v1/auth/apple/start", headers=h(tok)).json()["nonce"]
    claims = apple_claims(nonce, **over)
    if over.get("nonce") == "raw":
        claims["nonce"] = nonce  # the raw nonce instead of its hash
    r = c.post("/v1/auth/apple/verify", json={"id_token": sign(key, **claims), "nonce": nonce}, headers=h(tok))
    assert r.status_code == 400 and r.json()["detail"]["code"] == code


def test_provider_keys_unreachable(oidc_ctx, monkeypatch):
    import httpx

    def down(url: str) -> dict:
        raise httpx.ConnectError("down")

    oidc.clear_cache()
    monkeypatch.setattr(oidc, "fetch_jwks", down)
    c, tok = oidc_ctx.client, new_token(oidc_ctx.client)
    nonce = c.post("/v1/auth/google/start", headers=h(tok)).json()["nonce"]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    r = c.post("/v1/auth/google/verify", json={"credential": sign(key, **google_claims(nonce)), "nonce": nonce},
               headers=h(tok))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "provider_unavailable"
