from __future__ import annotations

import hmac
import uuid
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import Case, User


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_session(container: Container = Depends(get_container)) -> Iterator[Session]:
    session = container.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_user(authorization: str | None = Header(default=None),
                 session: Session = Depends(get_session)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = session.scalar(select(User).where(User.api_token == token))
    if user is None:
        raise HTTPException(401, "invalid token")
    return user


def optional_user(authorization: str | None = Header(default=None),
                  session: Session = Depends(get_session)) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return session.scalar(select(User).where(User.api_token == authorization.split(" ", 1)[1].strip()))


def require_admin(x_admin_token: str | None = Header(default=None),
                  container: Container = Depends(get_container)) -> str:
    """The ADMIN_TOKEN key, or a «Konsiliér Ops» session from the e-mail code sign-in (api/ops_login.py)."""
    if x_admin_token and hmac.compare_digest(x_admin_token, container.settings.admin_token):
        return "admin"
    if x_admin_token and x_admin_token.startswith(OPS_SESSION_PREFIX):
        from .ops_login import session_owner

        with container.session_factory() as session:
            email = session_owner(session, container, x_admin_token)
        if email:
            return "admin"
    raise HTTPException(403, "admin token required")


OPS_SESSION_PREFIX = "ops_"


def require_bot(x_bot_secret: str | None = Header(default=None),
                container: Container = Depends(get_container)) -> None:
    if not x_bot_secret or not hmac.compare_digest(x_bot_secret, container.settings.bot_api_secret):
        raise HTTPException(403, "bot secret required")


def load_case(case_id: uuid.UUID, session: Session, user: User) -> Case:
    case = session.get(Case, case_id)
    if case is None or case.owner_id != user.id:
        raise HTTPException(404, "case not found")
    return case
