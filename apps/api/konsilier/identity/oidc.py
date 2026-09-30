"""Verification of ID tokens from «Sign in with Google» and «Sign in with Apple».

The browser gets a signed JWT straight from the provider (Google Identity Services / Sign in with Apple JS in a popup)
and posts it to us; we check the signature against the provider's published keys (JWKS, cached for an hour), the
issuer, the audience (our public client id), the expiry and the one-time nonce bound to this device's session.
No client secret or private key is involved: an ID token alone proves who signed in.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
APPLE_JWKS = "https://appleid.apple.com/auth/keys"
APPLE_ISSUERS = ("https://appleid.apple.com",)

JWKS_TTL = 3600.0  # seconds
REFETCH_AFTER = 60.0  # an unknown key id triggers a refetch at most once a minute (keys rotate)
LEEWAY = 60  # seconds of clock skew allowed for exp / iat


class TokenError(Exception):
    """`code` is the reason shown to the person (account.errors.<code>)."""

    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def fetch_jwks(url: str) -> dict[str, Any]:
    """Download a JWKS document. Tests replace this function."""
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


_cache: dict[str, tuple[float, dict[str, Any]]] = {}  # url → (fetched at, {kid: jwk})
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _keys(url: str, force: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(url)
        fresh = hit is not None and now - hit[0] < (REFETCH_AFTER if force else JWKS_TTL)
        if fresh:
            return hit[1]
    try:
        doc = fetch_jwks(url)
    except (httpx.HTTPError, ValueError) as e:
        if hit is not None:  # the provider is briefly unreachable: keep using the keys we have
            return hit[1]
        raise TokenError("provider_unavailable", 503) from e
    keys = {k["kid"]: k for k in doc.get("keys", []) if isinstance(k, dict) and k.get("kid")}
    with _lock:
        _cache[url] = (now, keys)
    return keys


def _signing_key(url: str, kid: str | None) -> Any:
    if not kid:
        raise TokenError("invalid_token")
    jwk = _keys(url).get(kid) or _keys(url, force=True).get(kid)
    if jwk is None:
        raise TokenError("invalid_token")
    if jwk.get("kty") != "RSA":
        raise TokenError("invalid_token")
    return RSAAlgorithm.from_jwk(json.dumps(jwk))


@dataclass(frozen=True)
class Provider:
    name: str
    jwks_url: str
    issuers: tuple[str, ...]


GOOGLE = Provider("google", GOOGLE_JWKS, GOOGLE_ISSUERS)
APPLE = Provider("apple", APPLE_JWKS, APPLE_ISSUERS)


def verify_id_token(provider: Provider, token: str, audience: str, nonce_ok: Callable[[str | None], bool]) -> dict:
    """The verified claims of `token`, or TokenError. `nonce_ok` gets the token's nonce claim."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise TokenError("invalid_token") from e
    if header.get("alg") != "RS256":
        raise TokenError("invalid_token")
    key = _signing_key(provider.jwks_url, header.get("kid"))
    try:
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=audience, leeway=LEEWAY,
                            options={"require": ["iss", "aud", "exp", "iat", "sub"]})
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token_expired") from e
    except jwt.PyJWTError as e:
        raise TokenError("invalid_token") from e
    if claims.get("iss") not in provider.issuers:  # checked here: older PyJWT accepts a single issuer only
        raise TokenError("invalid_token")
    if not nonce_ok(claims.get("nonce")):
        raise TokenError("wrong_nonce")
    return claims


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verified_flag(value: Any) -> bool:
    """Google sends email_verified as a boolean; Apple sometimes as the string "true"."""
    return value is True or (isinstance(value, str) and value.lower() == "true")
