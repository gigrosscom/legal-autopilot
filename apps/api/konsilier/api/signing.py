"""ЭЦП signatures over prepared documents: claims to the other side, and customer ↔ lawyer agreements.

The person signs the file itself (PDF, or DOCX when there is no PDF) as CMS with the data inside, in NCALayer
on a computer or in eGov Mobile by QR. The verifier checks the certificate chain and revocation, and the signed
bytes must be exactly our file. Only signing keys (keyUsage SIGN) are accepted.

Who may sign what:
- a claim (action): the case owner; if the case knows the applicant's IIN, the signer must be that person;
- an agreement: first the case owner (same rule, plus their own ЭЦП identity if they have one), then the
  assigned lawyer — and only with the ЭЦП they registered with.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import (
    Action,
    Agreement,
    Case,
    DocumentSignature,
    Identity,
    LawyerApplication,
    LoginChallenge,
    User,
)
from ..identity import normalize as norm
from ..identity.ncanode import SignatureError
from .deps import current_user, get_container, get_session, load_case

router = APIRouter(prefix="/v1")

SIGN_TTL = timedelta(minutes=10)
MAX_CMS_CHARS = 30_000_000  # base64 of a signed document with the data inside
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _http(status: int, code: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": code})


def _expired(ch: LoginChallenge) -> bool:
    exp = ch.expires_at if ch.expires_at.tzinfo else ch.expires_at.replace(tzinfo=timezone.utc)
    return exp < datetime.now(timezone.utc)


def signature_view(sig: DocumentSignature) -> dict[str, Any]:
    return {"id": str(sig.id), "role": sig.role, "signer_name": sig.signer_name, "display": sig.display,
            "method": sig.method, "format": sig.file_format, "signed_at": sig.signed_at.isoformat()}


# ------------------------------------------------------------------ what is being signed
@dataclass
class Target:
    case: Case
    fmt: str
    data: bytes
    name: str
    action: Action | None = None
    agreement: Agreement | None = None


def action_file(container: Container, action: Action) -> tuple[str, bytes]:
    """The exact file that is signed: the PDF when there is one, otherwise the DOCX."""
    if action.pdf_key:
        return "pdf", container.storage.get(action.pdf_key)
    if action.docx_key:
        return "docx", container.storage.get(action.docx_key)
    raise HTTPException(404, "document not available")


def action_target(container: Container, case: Case, action: Action) -> Target:
    fmt, data = action_file(container, action)
    return Target(case, fmt, data, f"{action.sequence:02d}-{action.action_id}.{fmt}", action=action)


def agreement_target(container: Container, case: Case, agreement: Agreement) -> Target:
    return Target(case, "docx", container.storage.get(agreement.docx_key), f"{agreement.kind}.docx",
                  agreement=agreement)


def resolve_target(session: Session, container: Container, info: dict[str, Any]) -> Target:
    case = session.get(Case, uuid.UUID(info["case_id"]))
    if info.get("target") == "agreement":
        return agreement_target(container, case, session.get(Agreement, uuid.UUID(info["agreement_id"])))
    return action_target(container, case, session.get(Action, uuid.UUID(info["action_id"])))


def _user_iin_hash(session: Session, user_id: uuid.UUID) -> str | None:
    return session.scalar(select(Identity.subject_hash).where(Identity.user_id == user_id, Identity.kind == "iin"))


# ------------------------------------------------------------------ start / complete
def start_signing(session: Session, container: Container, user: User, target: Target, role: str,
                  method: str) -> dict[str, Any]:
    if not container.identity_methods()["ecp" if method == "ncalayer" else "egov"]:
        raise _http(503, "method_unavailable")
    sha = hashlib.sha256(target.data).hexdigest()
    info: dict[str, Any] = {"case_id": str(target.case.id), "sha256": sha, "method": method, "role": role}
    if target.agreement is not None:
        info.update(target="agreement", agreement_id=str(target.agreement.id))
    else:
        info.update(target="action", action_id=str(target.action.id))
    ch = LoginChallenge(kind="sign", user_id=user.id, secret_hash=container.identities.h("sign", secrets.token_hex(16)),
                        expires_at=datetime.now(timezone.utc) + SIGN_TTL, result=info)
    session.add(ch)
    session.flush()
    out: dict[str, Any] = {"session_id": str(ch.id), "format": target.fmt, "sha256": sha,
                           "expires_at": ch.expires_at.isoformat()}
    if method == "ncalayer":
        out["data"] = base64.b64encode(target.data).decode()
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


def complete_signature(session: Session, container: Container, ch: LoginChallenge, cms_b64: str,
                       method: str) -> DocumentSignature:
    """Verify `cms_b64` against the document the challenge points to and store the signature."""
    if container.signature_verifier is None:
        raise _http(503, "method_unavailable")
    if ch.consumed_at is not None or _expired(ch):
        raise _http(400, "challenge_expired")
    info = ch.result or {}
    target = resolve_target(session, container, info)
    if hashlib.sha256(target.data).hexdigest() != info["sha256"]:
        raise _http(409, "document_changed")
    try:
        signer = container.signature_verifier.verify(cms_b64, target.data)
    except SignatureError as e:
        raise _http(503 if e.code == "verifier_unavailable" else 400, e.code) from e
    if signer.key_usage != "SIGN":
        raise _http(400, "use_sign_key")
    iin = norm.iin(signer.iin)
    subject = container.identities.h("iin", iin)
    role = info.get("role", "applicant")
    case = target.case
    if role == "applicant":
        applicant_iin = (case.facts or {}).get("applicant_iin")
        own = _user_iin_hash(session, case.owner_id)
        if (applicant_iin and norm.iin(str(applicant_iin)) != iin) or (own and own != subject):
            raise _http(400, "signer_mismatch")
    else:  # lawyer: only with the ЭЦП they registered with
        app = session.get(LawyerApplication, target.agreement.lawyer_application_id)
        if app is None or app.iin_hash != subject:
            raise _http(400, "signer_mismatch")
    sig = DocumentSignature(case_id=case.id, action_id=target.action.id if target.action else None,
                            agreement_id=target.agreement.id if target.agreement else None,
                            signer_user_id=ch.user_id, role=role, subject_hash=subject, display=norm.mask_iin(iin),
                            signer_name=signer.name, method=method, file_format=target.fmt,
                            doc_sha256=info["sha256"], cms_key="")
    session.add(sig)
    session.flush()
    sig.cms_key = container.storage.put(f"cases/{case.id}/signatures/{sig.id}.cms", base64.b64decode(cms_b64),
                                        "application/pkcs7-mime")
    if target.agreement is not None:
        target.agreement.status = "awaiting_lawyer" if role == "applicant" else "signed"
    ch.consumed_at = datetime.now(timezone.utc)
    ch.result = {**info, "signature_id": str(sig.id)}
    container.engine.audit(session, case, f"user:{ch.user_id}", "document_signed", target=info.get("target"),
                           kind=target.agreement.kind if target.agreement else target.action.action_id,
                           role=role, method=method, format=target.fmt, sha256=info["sha256"], signer=sig.display)
    return sig


def _status(session: Session, ch: LoginChallenge) -> dict[str, Any]:
    if ch.consumed_at is not None:
        sid = (ch.result or {}).get("signature_id")
        found = session.get(DocumentSignature, uuid.UUID(sid)) if sid else None
        return {"status": "done", "signature": signature_view(found) if found else None}
    if (ch.result or {}).get("error"):
        return {"status": "failed", "code": ch.result["error"]}
    return {"status": "expired" if _expired(ch) else "pending"}


def _own_challenge(session: Session, session_id: uuid.UUID, user: User, key: str, value: str) -> LoginChallenge:
    ch = session.get(LoginChallenge, session_id)
    if ch is None or ch.kind != "sign" or ch.user_id != user.id or (ch.result or {}).get(key) != value:
        raise HTTPException(404, "signing session not found")
    return ch


def _cms_response(container: Container, sig: DocumentSignature, name: str) -> Response:
    return Response(container.storage.get(sig.cms_key), media_type="application/pkcs7-mime",
                    headers={"Content-Disposition": f'attachment; filename="{name}.cms"'})


class SignStart(BaseModel):
    method: Literal["ncalayer", "egov"] = "ncalayer"


class SignComplete(BaseModel):
    session_id: uuid.UUID
    cms: str = Field(max_length=MAX_CMS_CHARS)


# ------------------------------------------------------------------ claims (case actions)
def _load_action(case: Case, action_id: uuid.UUID, session: Session) -> Action:
    action = session.get(Action, action_id)
    if action is None or action.case_id != case.id or action.kind != "document":
        raise HTTPException(404, "action not found")
    return action


@router.post("/cases/{case_id}/actions/{action_id}/sign/start")
def sign_start(case_id: uuid.UUID, action_id: uuid.UUID, body: SignStart, user: User = Depends(current_user),
               session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    if action.status not in ("ready", "submitted", "responded"):
        raise _http(409, "awaiting_approval")
    return start_signing(session, container, user, action_target(container, case, action), "applicant", body.method)


@router.post("/cases/{case_id}/actions/{action_id}/sign")
def sign_complete(case_id: uuid.UUID, action_id: uuid.UUID, body: SignComplete, user: User = Depends(current_user),
                  session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    ch = _own_challenge(session, body.session_id, user, "action_id", str(action.id))
    return {"signature": signature_view(complete_signature(session, container, ch, body.cms, "ncalayer"))}


@router.get("/cases/{case_id}/actions/{action_id}/sign/status/{session_id}")
def sign_status(case_id: uuid.UUID, action_id: uuid.UUID, session_id: uuid.UUID, user: User = Depends(current_user),
                session: Session = Depends(get_session)) -> dict:
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    return _status(session, _own_challenge(session, session_id, user, "action_id", str(action.id)))


@router.get("/cases/{case_id}/actions/{action_id}/signatures/{signature_id}.cms")
def download_signed(case_id: uuid.UUID, action_id: uuid.UUID, signature_id: uuid.UUID,
                    user: User = Depends(current_user), session: Session = Depends(get_session),
                    container: Container = Depends(get_container)) -> Response:
    case = load_case(case_id, session, user)
    action = _load_action(case, action_id, session)
    sig = session.get(DocumentSignature, signature_id)
    if sig is None or sig.action_id != action.id:
        raise HTTPException(404, "signature not found")
    return _cms_response(container, sig, f"{action.sequence:02d}-{action.action_id}.{sig.file_format}")


# ------------------------------------------------------------------ customer ↔ lawyer agreements
def _agreement_for(session: Session, agreement_id: uuid.UUID, user: User) -> tuple[Agreement, Case, str]:
    """The agreement and the caller's role in it: 'applicant' (case owner) or 'lawyer' (assigned lawyer)."""
    ag = session.get(Agreement, agreement_id)
    case = session.get(Case, ag.case_id) if ag else None
    if case is not None and case.owner_id == user.id:
        return ag, case, "applicant"
    if case is not None and case.lawyer_user_id == user.id and case.lawyer_application_id == ag.lawyer_application_id:
        return ag, case, "lawyer"
    raise HTTPException(404, "agreement not found")


def agreement_view(pack: Any, ag: Agreement, lang: str) -> dict[str, Any]:
    tpl = pack.agreements.templates.get(ag.kind) if pack.agreements else None
    return {"id": str(ag.id), "kind": ag.kind, "title": pack.localized(tpl.title, lang) if tpl else ag.kind,
            "status": ag.status, "template_reviewed": ag.template_reviewed,
            "signatures": [signature_view(s) for s in ag.signatures]}


@router.get("/agreements/{agreement_id}/document")
def agreement_document(agreement_id: uuid.UUID, user: User = Depends(current_user),
                       session: Session = Depends(get_session), container: Container = Depends(get_container)) -> Response:
    ag, _, _ = _agreement_for(session, agreement_id, user)
    return Response(container.storage.get(ag.docx_key), media_type=DOCX,
                    headers={"Content-Disposition": f'attachment; filename="{ag.kind}.docx"'})


@router.post("/agreements/{agreement_id}/sign/start")
def agreement_sign_start(agreement_id: uuid.UUID, body: SignStart, user: User = Depends(current_user),
                         session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    ag, case, role = _agreement_for(session, agreement_id, user)
    expected = "awaiting_customer" if role == "applicant" else "awaiting_lawyer"
    if ag.status != expected:
        raise _http(409, "customer_first" if role == "lawyer" and ag.status == "awaiting_customer" else "already_signed")
    return start_signing(session, container, user, agreement_target(container, case, ag), role, body.method)


@router.post("/agreements/{agreement_id}/sign")
def agreement_sign(agreement_id: uuid.UUID, body: SignComplete, user: User = Depends(current_user),
                   session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    ag, _, _ = _agreement_for(session, agreement_id, user)
    ch = _own_challenge(session, body.session_id, user, "agreement_id", str(ag.id))
    return {"signature": signature_view(complete_signature(session, container, ch, body.cms, "ncalayer")),
            "status": ag.status}


@router.get("/agreements/{agreement_id}/sign/status/{session_id}")
def agreement_sign_status(agreement_id: uuid.UUID, session_id: uuid.UUID, user: User = Depends(current_user),
                          session: Session = Depends(get_session)) -> dict:
    ag, _, _ = _agreement_for(session, agreement_id, user)
    return _status(session, _own_challenge(session, session_id, user, "agreement_id", str(ag.id)))


@router.get("/agreements/{agreement_id}/signatures/{signature_id}.cms")
def agreement_signed_file(agreement_id: uuid.UUID, signature_id: uuid.UUID, user: User = Depends(current_user),
                          session: Session = Depends(get_session), container: Container = Depends(get_container)) -> Response:
    ag, _, _ = _agreement_for(session, agreement_id, user)
    sig = session.get(DocumentSignature, signature_id)
    if sig is None or sig.agreement_id != ag.id:
        raise HTTPException(404, "signature not found")
    return _cms_response(container, sig, f"{ag.kind}.{sig.role}.docx")
