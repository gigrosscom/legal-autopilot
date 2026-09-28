"""Referral programme: every person has an invite link; new people who come by it are counted to the inviter.

Only attribution and counts live here. A reward for inviting is a pricing decision and is added separately.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.models import Case, User
from .deps import current_user, get_session

router = APIRouter(prefix="/v1")

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alikes (l/1, o/0, i)
SITE = "https://konsilier.com"
_SRC = re.compile(r"[^a-z0-9_.-]")


def clean_source(src: str | None) -> str | None:
    value = _SRC.sub("", (src or "").strip().lower())[:40]
    return value or None


def attribute(session: Session, user: User, ref: str | None, src: str | None) -> None:
    """Record who invited a new person and the channel they came from."""
    inviter = None
    code = (ref or "").strip().lower()
    if code:
        inviter = session.scalar(select(User).where(User.ref_code == code[:12]))
    if inviter is not None:
        user.referred_by = inviter.id
    user.source = clean_source(src) or ("referral" if inviter is not None else None)


def ensure_code(session: Session, user: User) -> str:
    while not user.ref_code:
        code = "".join(secrets.choice(ALPHABET) for _ in range(7))
        if session.scalar(select(User.id).where(User.ref_code == code)) is None:
            user.ref_code = code
            session.flush()
    return user.ref_code


@router.get("/referral")
def my_referral(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    code = ensure_code(session, user)
    invited = session.scalar(select(func.count()).select_from(User).where(User.referred_by == user.id)) or 0
    active = session.scalar(select(func.count(func.distinct(Case.owner_id))).join(User, User.id == Case.owner_id)
                            .where(User.referred_by == user.id)) or 0
    return {"code": code, "link": f"{SITE}/?ref={code}", "invited": invited, "active": active}


def referral_metrics(session: Session) -> dict[str, Any]:
    """K-factor inputs for the team: how many people came by invitation and from which channels."""
    users = session.scalar(select(func.count()).select_from(User)) or 0
    referred = session.scalar(select(func.count()).select_from(User).where(User.referred_by.is_not(None))) or 0
    inviters = session.scalar(select(func.count(func.distinct(User.referred_by)))
                              .where(User.referred_by.is_not(None))) or 0
    sharing = session.scalar(select(func.count()).select_from(User).where(User.ref_code.is_not(None))) or 0
    # group by the plain column (PostgreSQL rejects a GROUP BY on a separately bound coalesce expression)
    sources = {src or "direct": n for src, n in session.execute(
        select(User.source, func.count()).group_by(User.source)).all()}
    return {
        "users": users, "referred_users": referred, "inviters": inviters, "users_with_link": sharing,
        # invited people per existing user: the viral coefficient the team tracks
        "k_factor": round(referred / (users - referred), 3) if users > referred else None,
        "sources": sources,
    }
