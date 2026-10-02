"""Verification of national-PKI ЭЦП (CMS signatures) through NCANode v3 (https://github.com/malikzh/NCANode).

NCANode checks the certificate chain to the НУЦ РК CAs and revocation (OCSP and CRL); we then read the IIN and
name from the signer certificate and make sure the signed data is exactly our one-time nonce.

When NCANode says "not valid", the reason is logged (status codes, chain and revocation results, algorithm,
validity dates and the issuing CA — never the signer's IIN, name or subject) and mapped to a code the site
explains to the person: chain, revoked, ocsp_unavailable, expired, unsupported_alg, data_mismatch.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

# OCSP first, CRL as well: NCANode counts the certificate as not revoked when either answers "good" and none
# answers "revoked", so a sign-in still works while ocsp.pki.gov.kz is unreachable but the CRL is loaded.
REVOCATION_CHECK = ["OCSP", "CRL"]

# A public certificate issued by «ҰЛТТЫҚ КУӘЛАНДЫРУШЫ ОРТАЛЫҚ (RSA) 2022» — the CA that issues today's RSA keys
# of people (the TSA certificate of tsp.pki.gov.kz, valid to 27.10.2028; no personal data). The deploy asks NCANode
# to check it: "rsa2022=ok" proves NCANode trusts the current RSA chain and reaches OCSP/CRL.
PROBE_CERT_RSA_2022 = (
    "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"
    "SwjRpIovxhFbGT51kf3fXra0LEaV5EHt"
)


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
            log.warning("ncanode %s: HTTP %s %s", path, r.status_code, _safe(r.text, 200))
            raise SignatureError("verifier_unavailable")
        try:
            return r.json()
        except ValueError as e:
            raise SignatureError("verifier_unavailable") from e

    def verify(self, cms_b64: str, expected: bytes) -> Signer:
        expected_b64 = base64.b64encode(expected).decode()
        # attached CMS (NCALayer with encapsulate: true) carries the data; a detached one needs it from us
        res = self._post("/cms/verify", {"cms": cms_b64, "revocationCheck": REVOCATION_CHECK})
        attached = True
        if not res.get("signers"):
            res = self._post("/cms/verify", {"cms": cms_b64, "data": expected_b64,
                                             "revocationCheck": REVOCATION_CHECK})
            attached = False
        if not res.get("valid"):
            code = failure_reason(res)
            log.warning("konsilier: ecp verify failed reason=%s attached=%s %s", code, attached,
                        json.dumps(failure_summary(res), ensure_ascii=False))
            raise SignatureError(code)
        if attached:
            data = self._post("/cms/extract", {"cms": cms_b64}).get("data")
            if not data or base64.b64decode(data) != expected:
                raise SignatureError("wrong_data")
        return signer_from(res)

    def _health(self) -> str:
        """NCANode's /actuator/health: UP once its CA certificates and CRLs are loaded; components ca and crl."""
        try:
            h = httpx.get(self.base_url + "/actuator/health", timeout=self.timeout).json()
        except (httpx.HTTPError, ValueError) as e:
            return e.__class__.__name__
        comps = h.get("components") or {}
        parts = ",".join(f"{k}:{(comps.get(k) or {}).get('status', '-')}" for k in ("ca", "crl") if k in comps)
        return f"{h.get('status', '?')}({parts})" if parts else str(h.get("status", "?"))

    def _version(self) -> str:
        try:
            m = re.search(r"v(\d+\.\d+\.\d+[\w.-]*)", httpx.get(self.base_url + "/", timeout=self.timeout).text)
        except httpx.HTTPError:
            return "?"
        return m.group(1) if m else "?"

    def self_check(self, wait: float = 0) -> str:
        """One line for the deploy log: NCANode's version and health, and whether it trusts the current НУЦ РК
        RSA chain and gets revocation data for it. `wait`: seconds to wait for NCANode to finish loading."""
        deadline = time.monotonic() + wait
        health = self._health()
        while not health.startswith("UP") and time.monotonic() < deadline:
            time.sleep(10)
            health = self._health()
        head = f"ncanode=v{self._version()} health={health}"
        try:
            return head + " " + self._probe()
        except SignatureError as e:
            return head + " rsa2022=" + e.code

    def _probe(self) -> str:
        res = self._post("/x509/info", {"certs": [PROBE_CERT_RSA_2022], "revocationCheck": REVOCATION_CHECK})
        certs = res.get("certificates") or res.get("signers") or []
        if not certs:
            return "rsa2022=error:" + _safe(str(res.get("message") or res.get("status")), 60).replace(" ", "_")
        c = certs[0]
        revs = ",".join(f"{r.get('by')}:{'revoked' if r.get('revoked') else (r.get('reason') or 'good')}"
                        for r in c.get("revocations") or [])
        revs = _safe(revs, 160).replace(" ", "_")
        return f"rsa2022={'ok' if c.get('valid') else 'FAIL'} rev=[{revs}]"


# ---------------------------------------------------------------- why NCANode said "not valid"
def _safe(text: str, limit: int) -> str:
    """NCANode messages are technical, but never let an IIN/BIN through to the log."""
    return re.sub(r"\d{12}", "<12d>", text or "")[:limit]


def _date(v) -> datetime | None:
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000, timezone.utc)
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return None


def _first(res: dict) -> tuple[dict, dict]:
    signers = res.get("signers") or []
    s = signers[0] if signers and isinstance(signers[0], dict) else {}
    certs = s.get("certificates") or []
    return s, (certs[0] if certs and isinstance(certs[0], dict) else {})


def failure_reason(res: dict) -> str:
    """Map NCANode's verdict to one of our codes. NCANode ≥3.5 grades each signer (status + subIndication);
    older versions only give certificate fields, so those are read as well."""
    s, c = _first(res)
    if not s:
        msg = str(res.get("message") or "").lower()
        if any(w in msg for w in ("algorithm", "алгоритм", "nosuchalgorithm", "not supported", "unsupported")):
            return "unsupported_alg"
        return "invalid_signature"
    sub = s.get("subIndication") or ""
    revs = c.get("revocations") or []
    if sub in ("CERT_REVOKED", "REVOKED_NO_POE") or any(r.get("revoked") for r in revs):
        return "revoked"
    now = datetime.now(timezone.utc)
    nb, na = _date(c.get("notBefore")), _date(c.get("notAfter"))
    if sub == "OUT_OF_BOUNDS_NO_POE" or (na and na < now) or (nb and nb > now):
        return "expired"
    reasons = " ".join(str(r.get("reason") or "") for r in revs).lower()
    if sub in ("CHAIN_INCOMPLETE", "NO_SIGNING_CERTIFICATE_FOUND") or "root certificate" in reasons:
        return "chain"
    if sub == "REVOCATION_DATA_MISSING":
        return "ocsp_unavailable"
    if sub in ("SIG_CRYPTO_FAILURE", "CERT_HASH_MISMATCH"):
        return "data_mismatch"
    if not sub and revs and not any(r.get("revoked") for r in revs) and c.get("valid") is False:
        return "ocsp_unavailable"  # older NCANode: chain fine, but no revocation source said "good"
    return "invalid_signature"


def failure_summary(res: dict) -> dict:
    """What NCANode said, without personal data: status codes, chain and revocation results, algorithm,
    certificate validity dates, key usage and the issuing CA's name (a CA, not a person)."""
    out: dict = {"status": res.get("status"), "valid": res.get("valid")}
    if res.get("message") and not res.get("signers"):
        out["message"] = _safe(str(res["message"]), 200)
    signers = []
    for s in res.get("signers") or []:
        if not isinstance(s, dict):
            continue
        item = {k: s.get(k) for k in ("status", "subIndication", "adesLevel", "bestSignatureTime") if s.get(k)}
        if s.get("message"):
            item["message"] = _safe(str(s["message"]), 160)
        item["tsp"] = bool(s.get("tsp"))
        certs = []
        for c in s.get("certificates") or []:
            issuer = c.get("issuer") or {}
            certs.append({
                "valid": c.get("valid"), "notBefore": c.get("notBefore"), "notAfter": c.get("notAfter"),
                "keyUsage": c.get("keyUsage"), "signAlg": c.get("signAlg"),
                "issuerCN": issuer.get("commonName"),
                "revocations": [{"by": r.get("by"), "revoked": r.get("revoked"),
                                 "reason": _safe(str(r.get("reason") or ""), 120)}
                                for r in c.get("revocations") or []],
            })
        item["certificates"] = certs
        signers.append(item)
    out["signers"] = signers
    return out


def signer_from(res: dict) -> Signer:
    signers = res.get("signers") or []
    if len(signers) != 1:
        raise SignatureError("one_signer_expected")
    certs = signers[0].get("certificates") or []
    if not certs:
        raise SignatureError("no_certificate")
    cert = certs[0]  # the signer's own certificate comes first, then the chain
    # NCANode ≥3.5 grades the signer itself (chain + dates + revocation by OCSP or CRL): its "VALID" is the verdict.
    # The certificate's own "valid" there demands every requested revocation source, so it is false while OCSP is
    # unreachable even though the CRL said "good". Older versions have no status: then the certificate decides.
    status = signers[0].get("status")
    if (status != "VALID") if status else not cert.get("valid", False):
        raise SignatureError("certificate_invalid")
    subject = cert.get("subject") or {}
    iin = subject.get("iin") or ""
    if not iin:
        raise SignatureError("no_iin")
    name = subject.get("commonName") or " ".join(x for x in (subject.get("surName"), subject.get("lastName")) if x)
    return Signer(iin=iin, name=(name or "").strip().title(), key_usage=cert.get("keyUsage") or "UNKNOWN")
