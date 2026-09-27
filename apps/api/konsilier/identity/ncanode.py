"""Verification of national-PKI ЭЦП (CMS signatures) through NCANode v3 (https://github.com/ncanode-kz/NCANode).

NCANode checks the certificate chain to the НУЦ РК roots and revocation (OCSP); we then read the IIN and
name from the signer certificate and make sure the signed data is exactly our one-time nonce.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

import httpx


class SignatureError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Signer:
    iin: str
    name: str
    key_usage: str  # AUTH | SIGN | UNKNOWN


class SignatureVerifier(Protocol):
    def verify(self, cms_b64: str, expected: bytes) -> Signer: ...


class NcaNode:
    def __init__(self, base_url: str, timeout: float = 20):
        self.base_url, self.timeout = base_url.rstrip("/"), timeout

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = httpx.post(self.base_url + path, json=body, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise SignatureError("verifier_unavailable") from e
        if r.status_code >= 500:
            raise SignatureError("verifier_unavailable")
        return r.json()

    def verify(self, cms_b64: str, expected: bytes) -> Signer:
        expected_b64 = base64.b64encode(expected).decode()
        res = self._post("/cms/verify", {"cms": cms_b64, "revocationCheck": ["OCSP"]})
        attached = True
        if not res.get("signers"):
            # detached signature: NCANode needs the data to check it
            res = self._post("/cms/verify", {"cms": cms_b64, "data": expected_b64, "revocationCheck": ["OCSP"]})
            attached = False
        if not res.get("valid"):
            raise SignatureError("invalid_signature")
        if attached:
            data = self._post("/cms/extract", {"cms": cms_b64}).get("data")
            if not data or base64.b64decode(data) != expected:
                raise SignatureError("wrong_data")
        return signer_from(res)


def signer_from(res: dict) -> Signer:
    signers = res.get("signers") or []
    if len(signers) != 1:
        raise SignatureError("one_signer_expected")
    certs = signers[0].get("certificates") or []
    if not certs:
        raise SignatureError("no_certificate")
    cert = certs[0]  # the signer's own certificate comes first, then the chain
    if not cert.get("valid", False):
        raise SignatureError("certificate_invalid")
    subject = cert.get("subject") or {}
    iin = subject.get("iin") or ""
    if not iin:
        raise SignatureError("no_iin")
    name = subject.get("commonName") or " ".join(x for x in (subject.get("surName"), subject.get("lastName")) if x)
    return Signer(iin=iin, name=(name or "").strip().title(), key_usage=cert.get("keyUsage") or "UNKNOWN")
