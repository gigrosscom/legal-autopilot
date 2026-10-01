"""«Konsiliér Ops» sign-in by a code to e-mail (owner 01.10): the e-mail field → the code from the letter (the same
one-time codes and limits as the clients' sign-in) → a server session with the rights of ADMIN_TOKEN for /v1/admin/*,
30 days, revoked by «Выйти». Only the addresses in OWNER_EMAILS; the key itself never reaches the browser. Sessions
are LoginChallenge rows (kind ops_session): only the HMAC of the token is stored."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import LoginChallenge, utcnow
from ..identity import normalize as norm
from ..identity.senders import SendError
from ..identity.service import AuthError
from .auth import _err, _ip
from .deps import OPS_SESSION_PREFIX, get_container, get_session

router = APIRouter(prefix="/v1/ops-auth")

CODE_KIND = "ops_email"
SESSION_KIND = "ops_session"
SESSION_TTL = timedelta(days=30)
LETTER = ("Код входа в Konsiliér Ops: {code}. Никому его не сообщайте. Действует 10 минут.", "Код входа в Konsiliér Ops")


def owners(container: Container) -> set[str]:
    out = set()
    for raw in container.settings.owner_emails.split(","):
        try:
            out.add(norm.email(raw))
        except ValueError:
            continue
    return out


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def session_owner(session: Session, container: Container, token: str) -> str | None:
    """The owner's e-mail of a live «Konsiliér Ops» session, else None (expired, signed out, or the address was taken
    off OWNER_EMAILS since)."""
    ids = container.identities
    row = session.scalar(select(LoginChallenge).where(LoginChallenge.kind == SESSION_KIND,
                                                      LoginChallenge.secret_hash == ids.h("ops", token)))
    if row is None or row.consumed_at is not None or _aware(row.expires_at) < utcnow():
        return None
    email = (row.result or {}).get("email")
    return email if email in owners(container) else None


class StartIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)


class VerifyIn(StartIn):
    code: str = Field(min_length=4, max_length=12)


@router.get("/methods")
def methods(container: Container = Depends(get_container)) -> dict[str, bool]:
    return {"email": bool(owners(container)) and container.email_sender is not None}


@router.post("/start")
def start(body: StartIn, request: Request, session: Session = Depends(get_session),
          container: Container = Depends(get_container)) -> dict[str, Any]:
    """Sends the code — only to an owner's address; any other address gets the same answer and no letter."""
    allowed = owners(container)
    if not allowed or container.email_sender is None:
        raise HTTPException(404, {"code": "method_unavailable", "message": "method_unavailable"})
    try:
        email = norm.email(body.email)
    except ValueError as e:
        raise HTTPException(400, {"code": "invalid_email", "message": "invalid_email"}) from e
    out: dict[str, Any] = {"sent": True}
    if email not in allowed:
        return out
    try:
        code, _ = container.identities.issue_code(session, None, CODE_KIND, email, _ip(request))
    except AuthError as e:
        raise _err(e) from e
    session.commit()  # the code counts towards the limits even if sending fails
    try:
        container.email_sender.send(email, LETTER[1], LETTER[0].format(code=code))
    except SendError as e:
        raise HTTPException(502, {"code": "send_failed", "message": "send_failed"}) from e
    if container.settings.dev_show_codes:
        out["dev_code"] = code
    return out


@router.post("/verify")
def verify(body: VerifyIn, session: Session = Depends(get_session),
           container: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        email = norm.email(body.email)
    except ValueError as e:
        raise HTTPException(400, {"code": "invalid_email", "message": "invalid_email"}) from e
    if email not in owners(container):
        raise HTTPException(400, {"code": "wrong_code", "message": "wrong_code"})
    try:
        container.identities.check_code(session, CODE_KIND, email, body.code)
    except AuthError as e:
        raise _err(e) from e
    token = OPS_SESSION_PREFIX + secrets.token_urlsafe(32)
    expires = utcnow() + SESSION_TTL
    session.add(LoginChallenge(kind=SESSION_KIND, secret_hash=container.identities.h("ops", token),
                               expires_at=expires, result={"email": email}))
    return {"token": token, "email": email, "expires_at": expires.isoformat()}


@router.post("/logout")
def logout(x_admin_token: str | None = Header(default=None), session: Session = Depends(get_session),
           container: Container = Depends(get_container)) -> dict[str, bool]:
    """«Выйти»: the session stops working at once (the key, if that is what signed in, stays as it is)."""
    if x_admin_token and x_admin_token.startswith(OPS_SESSION_PREFIX):
        row = session.scalar(select(LoginChallenge).where(
            LoginChallenge.kind == SESSION_KIND, LoginChallenge.secret_hash == container.identities.h("ops", x_admin_token)))
        if row is not None and row.consumed_at is None:
            row.consumed_at = utcnow()
    return {"ok": True}
