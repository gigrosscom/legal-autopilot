"""One-time codes, nonces and account linking. Pure logic over the session; transport lives in api/auth.py."""

from __future__ import annotations

import base64
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.models import Base, Identity, LoginChallenge, User
from . import normalize as norm

CODE_TTL = timedelta(minutes=10)
NONCE_TTL = timedelta(minutes=5)
EGOV_TTL = timedelta(minutes=5)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=60)
PER_TARGET_PER_HOUR = 5
PER_IP_PER_HOUR = 20


class AuthError(Exception):
    def __init__(self, code: str, status: int = 400, retry_after: int | None = None):
        super().__init__(code)
        self.code, self.status, self.retry_after = code, status, retry_after


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:  # SQLite returns naive datetimes
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Identities:
    secret: str

    def h(self, kind: str, value: str) -> str:
        return norm.keyed_hash(self.secret, kind, value)

    # ------------------------------------------------------------ one-time codes (email / phone)
    def issue_code(self, session: Session, user: User, kind: str, target: str, ip: str | None) -> tuple[str, LoginChallenge]:
        now = _now()
        target_hash = self.h(kind, target)
        ip_hash = self.h("ip", ip) if ip else None
        hour_ago = now - timedelta(hours=1)
        last = session.scalar(select(LoginChallenge).where(LoginChallenge.kind == kind,
                                                           LoginChallenge.target_hash == target_hash)
                              .order_by(LoginChallenge.created_at.desc()).limit(1))
        if last and _aware(last.created_at) > now - RESEND_AFTER:
            wait = int((RESEND_AFTER - (now - _aware(last.created_at))).total_seconds()) + 1
            raise AuthError("too_soon", 429, retry_after=wait)
        n_target = session.scalar(select(func.count()).select_from(LoginChallenge).where(
            LoginChallenge.target_hash == target_hash, LoginChallenge.created_at > hour_ago)) or 0
        n_ip = session.scalar(select(func.count()).select_from(LoginChallenge).where(
            LoginChallenge.ip_hash == ip_hash, LoginChallenge.created_at > hour_ago)) or 0 if ip_hash else 0
        if n_target >= PER_TARGET_PER_HOUR or n_ip >= PER_IP_PER_HOUR:
            raise AuthError("rate_limited", 429, retry_after=3600)
        code = f"{secrets.randbelow(1_000_000):06d}"
        ch = LoginChallenge(kind=kind, user_id=user.id, target_hash=target_hash, ip_hash=ip_hash,
                            secret_hash=self.h("code", f"{target_hash}:{code}"), expires_at=now + CODE_TTL)
        session.add(ch)
        session.flush()
        return code, ch

    def check_code(self, session: Session, kind: str, target: str, code: str) -> None:
        target_hash = self.h(kind, target)
        ch = session.scalar(select(LoginChallenge).where(
            LoginChallenge.kind == kind, LoginChallenge.target_hash == target_hash,
            LoginChallenge.consumed_at.is_(None)).order_by(LoginChallenge.created_at.desc()).limit(1))
        if ch is None or _aware(ch.expires_at) < _now():
            raise AuthError("code_expired")
        if ch.attempts >= MAX_ATTEMPTS:
            raise AuthError("too_many_attempts", 429)
        ch.attempts += 1
        expected = self.h("code", f"{target_hash}:{(code or '').strip()}")
        if not hmac.compare_digest(expected, ch.secret_hash):
            # the failed attempt must be persisted even though the request fails
            session.commit()
            raise AuthError("wrong_code")
        ch.consumed_at = _now()

    # ------------------------------------------------------------ nonces to sign (ЭЦП / eGov Mobile)
    def issue_nonce(self, session: Session, kind: str, user: User | None, ttl: timedelta = NONCE_TTL) -> tuple[bytes, LoginChallenge]:
        nonce = f"konsilier-auth:{secrets.token_urlsafe(24)}:{int(_now().timestamp())}".encode()
        ch = LoginChallenge(kind=kind, user_id=user.id if user else None,
                            secret_hash=self.h("nonce", base64.b64encode(nonce).decode()),
                            expires_at=_now() + ttl, result={"nonce": base64.b64encode(nonce).decode()})
        session.add(ch)
        session.flush()
        return nonce, ch

    def take_nonce(self, session: Session, kind: str, nonce_b64: str) -> LoginChallenge:
        ch = session.scalar(select(LoginChallenge).where(
            LoginChallenge.kind == kind, LoginChallenge.secret_hash == self.h("nonce", nonce_b64)))
        if ch is None or ch.consumed_at is not None or _aware(ch.expires_at) < _now():
            raise AuthError("challenge_expired")
        return ch

    # ------------------------------------------------------------ linking
    def link_or_login(self, session: Session, user: User, kind: str, value: str | None, display: str,
                      name: str | None = None, subject_hash: str | None = None) -> User:
        """Attach the verified identifier to `user`, or sign `user` into the account that already owns it.

        kind: email | phone | iin (ЭЦП and eGov Mobile both identify a person by IIN → one identity)
              | google | apple (the provider's stable `sub`; `display` is the masked e-mail).
        """
        subject = subject_hash or self.h(kind, value or "")
        ident = session.scalar(select(Identity).where(Identity.kind == kind, Identity.subject_hash == subject))
        owner = user
        if ident is None:
            session.add(Identity(user_id=user.id, kind=kind, subject_hash=subject, display=display))
        elif ident.user_id != user.id:
            owner = session.get(User, ident.user_id)
            # the person proved this identifier now: this device's account joins the one that owns it — its cases,
            # applications, push, bills and its other sign-in ways (owner 01.10: one person, one account)
            merge_users(session, user, owner)
            ident.verified_at = _now()
        else:
            ident.verified_at = _now()
        if kind == "email":
            owner.email = value
        elif kind == "phone":
            owner.phone = value
        if name and (kind == "iin" or (kind in ("google", "apple") and not owner.display_name)):
            owner.display_name = name
        session.flush()
        return owner


def merge_users(session: Session, src: User, dst: User) -> None:
    """Everything that belongs to `src` moves to `dst`: every row pointing at the user (cases, identities, bills,
    notifications, push, applications…), unused bonus documents and contacts `dst` lacks. `src` stays, empty."""
    if src.id == dst.id:
        return
    session.flush()
    for table in Base.metadata.sorted_tables:
        if table.name in (User.__tablename__, LoginChallenge.__tablename__):
            continue  # who invited whom stays as it was; a sign-in in progress stays with its device
        for col in table.columns:
            if any(fk.column.table.name == User.__tablename__ for fk in col.foreign_keys):
                session.execute(table.update().where(col == src.id).values({col.name: dst.id}))
    dst.bonus_documents += src.bonus_documents
    src.bonus_documents = 0
    dst.email, dst.phone = dst.email or src.email, dst.phone or src.phone
    dst.display_name = dst.display_name or src.display_name
    session.flush()
    session.expire_all()  # rows moved behind the ORM's back: read them again


def me_view(user: User) -> dict:
    return {"id": str(user.id), "display_name": user.display_name, "language": user.language,
            "notify_email": user.notify_email, "bonus_documents": user.bonus_documents,
            "identities": [{"kind": i.kind, "display": i.display, "verified_at": i.verified_at.isoformat()}
                           for i in sorted(user.identities, key=lambda i: i.verified_at)]}
