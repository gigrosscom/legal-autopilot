"""Sign-in and identity verification: e-mail and SMS codes, ЭЦП via NCALayer, eGov Mobile QR (mgovSign),
«Sign in with Google» and «Sign in with Apple» (ID tokens from a popup, verified against the providers' keys).

All methods start from the anonymous bearer token the web app already has and end in `link_or_login`,
which returns the (possibly different) account token the client must switch to.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..container import Container
from ..identity import normalize as norm
from ..identity import oidc
from ..identity.ncanode import SignatureError
from ..identity.service import AuthError, EGOV_TTL, me_view
from ..identity.senders import SendError
from ..core.models import LoginChallenge, User
from .deps import current_user, get_container, get_session

router = APIRouter(prefix="/v1")

MESSAGES = {
    "ru": ("Код входа Konsiliér AI: {code}. Никому его не сообщайте. Действует 10 минут.",
           "Код входа в Konsiliér AI"),
    "kk": ("Konsiliér AI кіру коды: {code}. Ешкімге айтпаңыз. 10 минут жарамды.", "Konsiliér AI кіру коды"),
    "en": ("Your Konsiliér AI sign-in code: {code}. Do not share it. Valid for 10 minutes.",
           "Your Konsiliér AI sign-in code"),
    "ar": ("رمز الدخول إلى Konsiliér AI: {code}. لا تشاركه مع أحد. صالح لمدة 10 دقائق.",
           "رمز الدخول إلى Konsiliér AI"),
    "tr": ("Konsiliér AI giriş kodunuz: {code}. Kimseyle paylaşmayın. 10 dakika geçerlidir.",
           "Konsiliér AI giriş kodu"),
}


def _err(e: AuthError) -> HTTPException:
    headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
    return HTTPException(e.status, {"code": e.code, "message": e.code, "retry_after": e.retry_after}, headers=headers)


def _ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def _signed_in(owner: User) -> dict[str, Any]:
    return {"token": owner.api_token, "me": me_view(owner)}


@router.get("/auth/methods")
def methods(container: Container = Depends(get_container)) -> dict[str, bool]:
    return container.identity_methods()


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return me_view(user)


class MeIn(BaseModel):
    notify_email: bool | None = None


@router.patch("/me")
def update_me(body: MeIn, user: User = Depends(current_user)) -> dict[str, Any]:
    if body.notify_email is not None:
        user.notify_email = body.notify_email
    return me_view(user)


# ------------------------------------------------------------------ e-mail / phone codes
class CodeStart(BaseModel):
    target: str = Field(max_length=200)
    language: str | None = None


class CodeCheck(BaseModel):
    target: str = Field(max_length=200)
    code: str = Field(max_length=12)


def _normalize(kind: str, value: str, cc: str) -> str:
    try:
        return norm.email(value) if kind == "email" else norm.phone(value, cc)
    except norm.InvalidIdentifier as e:
        raise HTTPException(400, {"code": f"invalid_{kind}", "message": f"invalid_{kind}"}) from e


def code_start(kind: str, body: CodeStart, request: Request, user: User = Depends(current_user),
               session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    sender = container.email_sender if kind == "email" else container.sms_sender
    if sender is None:
        raise HTTPException(503, {"code": "method_unavailable", "message": "method_unavailable"})
    target = _normalize(kind, body.target, container.settings.phone_default_country_code)
    try:
        code, _ = container.identities.issue_code(session, user, kind, target, _ip(request))
    except AuthError as e:
        raise _err(e) from e
    text, subject = MESSAGES.get(body.language or user.language, MESSAGES["ru"])
    try:
        sender.send(target, subject, text.format(code=code))
    except SendError as e:
        container.send_failed_at[kind] = datetime.now(timezone.utc)  # payment stops asking for this channel for a while
        raise HTTPException(502, {"code": "send_failed", "message": "send_failed"}) from e
    out: dict[str, Any] = {"sent": True, "resend_after": 60}
    if container.settings.dev_show_codes:
        out["dev_code"] = code
    return out


def code_verify(kind: str, body: CodeCheck, user: User = Depends(current_user),
                session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    target = _normalize(kind, body.target, container.settings.phone_default_country_code)
    try:
        container.identities.check_code(session, kind, target, body.code)
    except AuthError as e:
        raise _err(e) from e
    display = norm.mask_email(target) if kind == "email" else norm.mask_phone(target)
    return _signed_in(container.identities.link_or_login(session, user, kind, target, display))


def _bind(kind: str):
    def start(body: CodeStart, request: Request, user: User = Depends(current_user),
              session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
        return code_start(kind, body, request, user, session, container)

    def verify(body: CodeCheck, user: User = Depends(current_user), session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> dict:
        return code_verify(kind, body, user, session, container)

    router.add_api_route(f"/auth/{kind}/start", start, methods=["POST"], name=f"{kind}_start")
    router.add_api_route(f"/auth/{kind}/verify", verify, methods=["POST"], name=f"{kind}_verify")


for _kind in ("email", "phone"):
    _bind(_kind)


# ------------------------------------------------------------------ ЭЦП through NCALayer
@router.post("/auth/ecp/challenge")
def ecp_challenge(user: User = Depends(current_user), session: Session = Depends(get_session),
                  container: Container = Depends(get_container)) -> dict:
    if container.signature_verifier is None:
        raise HTTPException(503, {"code": "method_unavailable", "message": "method_unavailable"})
    nonce, ch = container.identities.issue_nonce(session, "ecp", user)
    return {"nonce": base64.b64encode(nonce).decode(), "expires_at": ch.expires_at.isoformat()}


class EcpVerify(BaseModel):
    nonce: str = Field(max_length=200)
    cms: str = Field(max_length=200_000)


def _check_signature(container: Container, cms: str, nonce_b64: str):
    try:
        return container.signature_verifier.verify(cms, base64.b64decode(nonce_b64))
    except SignatureError as e:
        status = 503 if e.code == "verifier_unavailable" else 400
        raise HTTPException(status, {"code": e.code, "message": e.code}) from e


@router.post("/auth/ecp/verify")
def ecp_verify(body: EcpVerify, user: User = Depends(current_user), session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> dict:
    if container.signature_verifier is None:
        raise HTTPException(503, {"code": "method_unavailable", "message": "method_unavailable"})
    try:
        ch = container.identities.take_nonce(session, "ecp", body.nonce)
    except AuthError as e:
        raise _err(e) from e
    if ch.user_id != user.id:
        raise HTTPException(403, {"code": "foreign_challenge", "message": "foreign_challenge"})
    signer = _check_signature(container, body.cms, body.nonce)
    ch.consumed_at = datetime.now(timezone.utc)
    iin = norm.iin(signer.iin)
    return _signed_in(container.identities.link_or_login(session, user, "iin", iin, norm.mask_iin(iin), signer.name))


# ------------------------------------------------------------------ eGov Mobile (QR / mgovSign)
def _egov_enabled(container: Container) -> bool:
    return container.identity_methods()["egov"]


@router.post("/auth/egov/start")
def egov_start(user: User = Depends(current_user), session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> dict:
    if not _egov_enabled(container):
        raise HTTPException(503, {"code": "method_unavailable", "message": "method_unavailable"})
    _, ch = container.identities.issue_nonce(session, "egov", user, ttl=EGOV_TTL)
    service_url = f"{container.settings.public_api_url.rstrip('/')}/v1/auth/egov/mgov/{ch.id}"
    return {"id": str(ch.id), "qr": f"mobileSign:{service_url}", "expires_at": ch.expires_at.isoformat(),
            "links": {
                "egov_mobile": f"https://mgovsign.page.link/?link={service_url}"
                               "&isi=1476128386&ibi=kz.egov.mobile&apn=kz.mobile.mgov",
                "egov_business": f"https://egovbusiness.page.link/?link={service_url}"
                                 "&isi=1597880144&ibi=kz.mobile.mgov.business&apn=kz.mobile.mgov.business",
            }}


def _egov_challenge(session: Session, challenge_id: uuid.UUID) -> LoginChallenge:
    ch = session.get(LoginChallenge, challenge_id)
    if ch is None or ch.kind not in ("egov", "sign") or _expired(ch):
        raise HTTPException(404, "not found")
    return ch


def _expired(ch: LoginChallenge) -> bool:
    exp = ch.expires_at if ch.expires_at.tzinfo else ch.expires_at.replace(tzinfo=timezone.utc)
    return exp < datetime.now(timezone.utc)


@router.get("/auth/egov/mgov/{challenge_id}")
def egov_service(challenge_id: uuid.UUID, session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> dict:
    """API №1 for eGov Mobile: who asks and where to fetch the document to sign."""
    ch = _egov_challenge(session, challenge_id)
    s = container.settings
    return {
        "description": "Вход в Konsiliér AI / Konsiliér AI жүйесіне кіру" if ch.kind == "egov"
        else "Подписание документа в Konsiliér AI / Konsiliér AI құжатына қол қою",
        "expiry_date": _mgov_date(ch.expires_at),
        "organisation": {"nameRu": s.egov_org_name, "nameKz": s.egov_org_name, "nameEn": s.egov_org_name,
                         "bin": s.egov_org_bin},
        # the one-time unguessable link is the protection, so no token: auth_type None with an empty auth_token
        "document": {"uri": f"{s.public_api_url.rstrip('/')}/v1/auth/egov/mgov/{ch.id}/document",
                     "auth_type": "None", "auth_token": ""},
    }


def _mgov_date(dt: datetime) -> str:
    """ISO 8601 with milliseconds and an explicit offset, e.g. 2026-10-01T18:44:00.000+00:00."""
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _mgov_doc(names: tuple[str, str, str], meta: list[dict], data: bytes, mime: str) -> dict:
    """One entry of documentsToSign for CMS_WITH_DATA: the data itself goes in document.file.data as base64
    (eGov Mobile wraps it into the CMS); mime "@file/pdf" lets the app show a PDF."""
    return {"id": 1, "nameRu": names[0], "nameKz": names[1], "nameEn": names[2], "meta": meta,
            "document": {"file": {"mime": mime, "data": base64.b64encode(data).decode()}}}


def _mgov_signed_cms(payload: dict) -> str | None:
    """The CMS eGov Mobile sends back in document.file.data (documentCms kept for older app builds)."""
    docs = payload.get("documentsToSign") or []
    doc = docs[0] if docs and isinstance(docs[0], dict) else {}
    file = (doc.get("document") or {}).get("file") if isinstance(doc.get("document"), dict) else None
    return (file or {}).get("data") or doc.get("documentCms")


@router.get("/auth/egov/mgov/{challenge_id}/document")
def egov_document(challenge_id: uuid.UUID, session: Session = Depends(get_session),
                  container: Container = Depends(get_container)) -> dict:
    """API №2: the data to sign — our one-time nonce, or the prepared document itself."""
    ch = _egov_challenge(session, challenge_id)
    if ch.kind == "sign":
        from .signing import resolve_target

        target = resolve_target(session, container, ch.result or {})
        mime = "@file/pdf" if target.fmt == "pdf" else \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return {"signMethod": "CMS_WITH_DATA", "documentsToSign": [_mgov_doc(
            (target.name,) * 3, [{"name": "SHA-256", "value": (ch.result or {}).get("sha256", "")}],
            target.data, mime)]}
    nonce = base64.b64decode((ch.result or {}).get("nonce", ""))
    return {"signMethod": "CMS_WITH_DATA", "documentsToSign": [_mgov_doc(
        ("Вход в Konsiliér AI", "Konsiliér AI жүйесіне кіру", "Sign in to Konsiliér AI"),
        [{"name": "Назначение", "value": "Подтверждение личности для входа"}], nonce, "text/plain")]}


@router.api_route("/auth/egov/mgov/{challenge_id}/document", methods=["PUT", "POST"])
def egov_signed(challenge_id: uuid.UUID, payload: dict = Body(...), session: Session = Depends(get_session),
                container: Container = Depends(get_container)) -> list:
    """eGov Mobile sends back the same structure with document.file.data replaced by the signed CMS, or with
    status CANCELED and the unsigned original when the person declined."""
    ch = _egov_challenge(session, challenge_id)
    if ch.consumed_at is not None or (ch.result or {}).get("subject_hash"):
        raise HTTPException(409, "already signed")
    if str(payload.get("status") or "").upper() == "CANCELED":
        if ch.kind == "sign":
            ch.result = {**(ch.result or {}), "error": "canceled"}
            session.commit()
        raise HTTPException(400, {"code": "canceled", "message": "canceled"})
    cms = _mgov_signed_cms(payload)
    if not cms:
        raise HTTPException(400, {"code": "no_signature", "message": "no_signature"})
    if ch.kind == "sign":
        from .signing import complete_signature

        try:
            complete_signature(session, container, ch, cms, "egov")
        except HTTPException as e:
            # tell the waiting web page why, then answer eGov Mobile with the error
            code = e.detail.get("code") if isinstance(e.detail, dict) else "failed"
            ch.result = {**(ch.result or {}), "error": code}
            session.commit()
            raise
        return []
    nonce_b64 = (ch.result or {}).get("nonce", "")
    signer = _check_signature(container, cms, nonce_b64)
    iin = norm.iin(signer.iin)
    # keep only what is needed to finish the sign-in, never the IIN itself
    ch.result = {"nonce": nonce_b64, "subject_hash": container.identities.h("iin", iin),
                 "display": norm.mask_iin(iin), "name": signer.name}
    return []


@router.get("/auth/egov/status/{challenge_id}")
def egov_status(challenge_id: uuid.UUID, user: User = Depends(current_user),
                session: Session = Depends(get_session), container: Container = Depends(get_container)) -> dict:
    ch = session.get(LoginChallenge, challenge_id)
    if ch is None or ch.kind != "egov" or ch.user_id != user.id:
        raise HTTPException(404, "not found")
    res = ch.result or {}
    if ch.consumed_at is not None:
        return {"status": "used"}
    if not res.get("subject_hash"):
        return {"status": "expired" if _expired(ch) else "pending"}
    ch.consumed_at = datetime.now(timezone.utc)
    owner = container.identities.link_or_login(session, user, "iin", None, res["display"], res.get("name"),
                                               subject_hash=res["subject_hash"])
    return {"status": "done", **_signed_in(owner)}


# ------------------------------------------------------------------ Google / Apple (ID token from a popup)
# The page asks for a nonce when it shows the button (start), hands it to the provider's script, and posts the ID
# token it gets back together with the same nonce (verify). The nonce is one-time and belongs to this device's
# account, so a token caught elsewhere cannot sign anyone in here.
OIDC_NONCE_TTL = timedelta(minutes=30)  # the button is prepared when the page opens; the person may read first


def _oidc_audience(container: Container, kind: str) -> str:
    s = container.settings
    aud = s.google_client_id if kind == "google" else s.apple_services_id
    if not aud:
        raise HTTPException(503, {"code": "method_unavailable", "message": "method_unavailable"})
    return aud


def _oidc_start(kind: str, user: User, session: Session, container: Container) -> tuple[str, LoginChallenge]:
    _oidc_audience(container, kind)
    nonce, ch = container.identities.issue_nonce(session, kind, user, ttl=OIDC_NONCE_TTL)
    return base64.b64encode(nonce).decode(), ch


def _oidc_signed_in(kind: str, token: str, nonce: str, name: str | None, user: User, session: Session,
                    container: Container) -> dict:
    audience = _oidc_audience(container, kind)
    try:
        ch = container.identities.take_nonce(session, kind, nonce)
    except AuthError as e:
        raise _err(e) from e
    if ch.user_id != user.id:
        raise HTTPException(403, {"code": "foreign_challenge", "message": "foreign_challenge"})
    if kind == "google":
        # Google Identity Services puts the nonce into the token exactly as given
        provider, expected = oidc.GOOGLE, nonce
    else:
        # Sign in with Apple JS is given SHA-256 (hex) of our nonce and echoes that value in the token's nonce
        # claim; the raw nonce stays with this device's session, so only its holder can match the hash
        provider, expected = oidc.APPLE, oidc.sha256_hex(nonce)
    try:
        claims = oidc.verify_id_token(provider, token, audience, lambda claim: claim == expected)
    except oidc.TokenError as e:
        raise HTTPException(e.status, {"code": e.code, "message": e.code}) from e
    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    if kind == "google":
        if not email or not oidc.verified_flag(claims.get("email_verified")):
            raise HTTPException(400, {"code": "email_not_verified", "message": "email_not_verified"})
        name = claims.get("name") if isinstance(claims.get("name"), str) else None
    ch.consumed_at = datetime.now(timezone.utc)
    display = norm.mask_email(email.strip().lower())[:120] if email else ("Google" if kind == "google" else "Apple ID")
    owner = container.identities.link_or_login(session, user, kind, str(claims["sub"]), display,
                                               (name or "").strip()[:100] or None)
    return _signed_in(owner)


@router.post("/auth/google/start")
def google_start(user: User = Depends(current_user), session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> dict:
    nonce, ch = _oidc_start("google", user, session, container)
    return {"nonce": nonce, "client_id": container.settings.google_client_id,
            "expires_at": ch.expires_at.isoformat()}


class GoogleVerify(BaseModel):
    credential: str = Field(max_length=8000)
    nonce: str = Field(max_length=200)


@router.post("/auth/google/verify")
def google_verify(body: GoogleVerify, user: User = Depends(current_user), session: Session = Depends(get_session),
                  container: Container = Depends(get_container)) -> dict:
    return _oidc_signed_in("google", body.credential, body.nonce, None, user, session, container)


@router.post("/auth/apple/start")
def apple_start(user: User = Depends(current_user), session: Session = Depends(get_session),
                container: Container = Depends(get_container)) -> dict:
    nonce, ch = _oidc_start("apple", user, session, container)
    s = container.settings
    return {"nonce": nonce, "nonce_sha256": oidc.sha256_hex(nonce), "client_id": s.apple_services_id,
            "redirect_uri": s.apple_return_url, "expires_at": ch.expires_at.isoformat()}


class AppleVerify(BaseModel):
    id_token: str = Field(max_length=8000)
    nonce: str = Field(max_length=200)
    name: str | None = Field(default=None, max_length=200)  # Apple gives the name to the page once, on first sign-in


@router.post("/auth/apple/verify")
def apple_verify(body: AppleVerify, user: User = Depends(current_user), session: Session = Depends(get_session),
                 container: Container = Depends(get_container)) -> dict:
    return _oidc_signed_in("apple", body.id_token, body.nonce, body.name, user, session, container)
