"""ЭЦП signatures over prepared documents (claims to the other side, later consents and powers of attorney).

The person signs the document file itself (PDF, or DOCX when there is no PDF) as CMS with the data inside,
in NCALayer on a computer or in eGov Mobile by QR. The verifier checks the certificate chain and revocation,
and the signed bytes must be exactly our file. Only signing keys (keyUsage SIGN) are accepted.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import Action, Case, DocumentSignature, LoginChallenge, User
from ..identity import normalize as norm
from ..identity.ncanode import SignatureError
from .deps import current_user, get_container, get_session, load_case

router = APIRouter(prefix="/v1")

SIGN_TTL = timedelta(minutes=10)
MAX_CMS_CHARS = 30_000_000  # base64 of a signed document with the data inside


def _unavailable() -> HTTPException:
    return HTTPException(503, {"code": "method_unavailable", "message": "method_unavailable"})


def _load_action(case: Case, action_id: uuid.UUID, session: Session) -> Action:
    action = session.get(Action, action_id)
    if action is None or action.case_id != case.id or action.kind != "document":
        raise HTTPException(404, "action not found")
    return action


def document_file(container: Container, action: Action) -> tuple[str, bytes]:
    """The exact file that is signed: the PDF when there is one, otherwise the DOCX."""
    if action.pdf_key:
        return "pdf", container.storage.get(action.pdf_key)
    if action.docx_key:
        return "docx", container.storage.get(action.docx_key)
    raise HTTPException(404, "document not available")


def signature_view(sig: DocumentSignature) -> dict[str, Any]:
    return {"id": str(sig.id), "role": sig.role, "signer_name": sig.signer_name, "display": sig.display,
            "method": sig.method, "format": sig.file_format, "signed_at": sig.signed_at.isoformat()}


def _expired(ch: LoginChallenge) -> bool:
    exp = ch.expires_at if ch.expires_at.tzinfo else ch.expires_at.replace(tzinfo=timezone.utc)
    return exp < datetime.now(timezone.utc)


def complete_signature(session: Session, container: Container, ch: LoginChallenge, cms_b64: str,
                       method: str) -> DocumentSignature:
    """Verify `cms_b64` against the document the challenge points to and store the signature."""
    if container.signature_verifier is None:
        raise _unavailable()
    if ch.consumed_at is not None or _expired(ch):
        raise HTTPException(400, {"code": "challenge_expired", "message": "challenge_expired"})
    info = ch.result or {}
    case = session.get(Case, uuid.UUID(info["case_id"]))
    action = session.get(Action, uuid.UUID(info["action_id"]))
    fmt, data = document_file(container, action)
    if hashlib.sha256(data).hexdigest() != info["sha256"]:
        raise HTTPException(409, {"code": "document_changed", "message": "document_changed"})
    try:
        signer = container.signature_verifier.verify(cms_b64, data)
    except SignatureError as e:
        status = 503 if e.code == "verifier_unavailable" else 400
        raise HTTPException(status, {"code": e.code, "message": e.code}) from e
    if signer.key_usage != "SIGN":
        raise HTTPException(400, {"code": "use_sign_key", "message": "use_sign_key"})
    iin = norm.iin(signer.iin)
    applicant_iin = (case.facts or {}).get("applicant_iin")
    if applicant_iin and norm.iin(str(applicant_iin)) != iin:
        raise HTTPException(400, {"code": "signer_mismatch", "message": "signer_mismatch"})
    sig = DocumentSignature(case_id=case.id, action_id=action.id, signer_user_id=ch.user_id, role="applicant",
                            subject_hash=container.identities.h("iin", iin), display=norm.mask_iin(iin),
                            signer_name=signer.name, method=method, file_format=fmt,
                            doc_sha256=info["sha256"], cms_key="")
    session.add(sig)
    session.flush()
    sig.cms_key = container.storage.put(f"cases/{case.id}/signatures/{sig.id}.cms", base64.b64decode(cms_b64),
                                        "application/pkcs7-mime")
    ch.consumed_at = datetime.now(timezone.utc)
    ch.result = {**info, "signature_id": str(sig.id)}
    container.engine.audit(session, case, f"user:{ch.user_id}", "document_signed", action=action.action_id,
                           method=method, format=fmt, sha256=info["sha256"], signer=sig.display)
    return sig


class SignStart(BaseModel):
    method: Literal["ncalayer", "egov"] = "ncalayer"


@router.post("/cases/{case_id}/actions/{action_id}/sign/start")
def sign_start(case_id: uuid.UUID, action_id: uuid.UUID, body: SignStart, user: User = Depends(current_user),
               session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    methods = container.identity_methods()
    if not methods["ecp" if body.method == "ncalayer" else "egov"]:
        raise _unavailable()
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    if action.status not in ("ready", "submitted", "responded"):
        raise HTTPException(409, {"code": "awaiting_approval", "message": "document is awaiting lawyer approval"})
    fmt, data = document_file(container, action)
    sha = hashlib.sha256(data).hexdigest()
    ch = LoginChallenge(kind="sign", user_id=user.id, secret_hash=container.identities.h("sign", secrets.token_hex(16)),
                        expires_at=datetime.now(timezone.utc) + SIGN_TTL,
                        result={"case_id": str(case.id), "action_id": str(action.id), "sha256": sha,
                                "method": body.method})
    session.add(ch)
    session.flush()
    out: dict[str, Any] = {"session_id": str(ch.id), "format": fmt, "sha256": sha,
                           "expires_at": ch.expires_at.isoformat()}
    if body.method == "ncalayer":
        out["data"] = base64.b64encode(data).decode()
    else:
        service_url = f"{container.settings.public_api_url.rstrip('/')}/v1/auth/egov/mgov/{ch.id}"
        out["qr"] = f"mobileSign:{service_url}"
        out["links"] = {
            "egov_mobile": f"https://mgovsign.page.link/?link={service_url}"
                           "&isi=1476128386&ibi=kz.egov.mobile&apn=kz.mobile.mgov",
            "egov_business": f"https://egovbusiness.page.link/?link={service_url}"
                             "&isi=1597880144&ibi=kz.mobile.mgov.business&apn=kz.mobile.mgov.business",
        }
    return out


class SignComplete(BaseModel):
    session_id: uuid.UUID
    cms: str = Field(max_length=MAX_CMS_CHARS)


def _own_sign_challenge(session: Session, session_id: uuid.UUID, user: User, case: Case, action: Action) -> LoginChallenge:
    ch = session.get(LoginChallenge, session_id)
    info = (ch.result or {}) if ch else {}
    if ch is None or ch.kind != "sign" or ch.user_id != user.id or info.get("action_id") != str(action.id) \
            or info.get("case_id") != str(case.id):
        raise HTTPException(404, "signing session not found")
    return ch


@router.post("/cases/{case_id}/actions/{action_id}/sign")
def sign_complete(case_id: uuid.UUID, action_id: uuid.UUID, body: SignComplete, user: User = Depends(current_user),
                  session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    ch = _own_sign_challenge(session, body.session_id, user, case, action)
    return {"signature": signature_view(complete_signature(session, container, ch, body.cms, "ncalayer"))}


@router.get("/cases/{case_id}/actions/{action_id}/sign/status/{session_id}")
def sign_status(case_id: uuid.UUID, action_id: uuid.UUID, session_id: uuid.UUID, user: User = Depends(current_user),
                session: Session = Depends(get_session)) -> dict:
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    ch = _own_sign_challenge(session, session_id, user, case, action)
    if ch.consumed_at is not None:
        sig = (ch.result or {}).get("signature_id")
        found = session.get(DocumentSignature, uuid.UUID(sig)) if sig else None
        return {"status": "done", "signature": signature_view(found) if found else None}
    if (ch.result or {}).get("error"):
        return {"status": "failed", "code": ch.result["error"]}
    return {"status": "expired" if _expired(ch) else "pending"}


@router.get("/cases/{case_id}/actions/{action_id}/signatures/{signature_id}.cms")
def download_signed(case_id: uuid.UUID, action_id: uuid.UUID, signature_id: uuid.UUID,
                    user: User = Depends(current_user), session: Session = Depends(get_session),
                    container: Container = Depends(get_container)) -> Response:
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    sig = session.get(DocumentSignature, signature_id)
    if sig is None or sig.action_id != action.id:
        raise HTTPException(404, "signature not found")
    name = f"{action.sequence:02d}-{action.action_id}.{sig.file_format}.cms"
    return Response(container.storage.get(sig.cms_key), media_type="application/pkcs7-mime",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
