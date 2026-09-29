"""Notifier: writes to the outbox and delivers through the user's channel adapter.

Every notification lands in the site inbox (the bell) and goes out through the user's channel (web or Telegram).
Key events also go further:
- e-mail, for `EMAIL_KINDS`, to a verified address while the person keeps e-mail on;
- SMS, only when the caller marks the event critical (document ready, payment confirmed, the response deadline
  due today or expired), to a verified phone, and never at night in the pack's local time (`QUIET_HOURS`).
A failed delivery never breaks the case flow: it is logged and written to the row.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters.channels import ChannelAdapter
from .models import Case, Identity, Notification, User

log = logging.getLogger(__name__)

# kinds worth an e-mail besides the inbox (case reports mail themselves, see konsilier.reports)
EMAIL_KINDS = frozenset({"payment", "document", "approval", "deadline_reminder", "deadline_expired", "handoff"})
# no SMS from 22:00 to 08:00 local time; the inbox and e-mail still get it
QUIET_HOURS = (22, 8)


def verified_email(session: Session, user: User) -> str | None:
    """The person's address, when it is verified (an e-mail identity) and e-mail is on."""
    if not user.email or not user.notify_email:
        return None
    has = session.scalar(select(Identity.id).where(Identity.user_id == user.id, Identity.kind == "email"))
    return user.email if has else None


def verified_phone(session: Session, user: User) -> str | None:
    if not user.phone:
        return None
    has = session.scalar(select(Identity.id).where(Identity.user_id == user.id, Identity.kind == "phone"))
    return user.phone if has else None


def quiet(local: datetime) -> bool:
    start, end = QUIET_HOURS
    return local.hour >= start or local.hour < end


class Notifier:
    def __init__(self, channels: dict[str, ChannelAdapter], packs: Any = None):
        self.channels = channels
        self.packs = packs
        # what e-mail and SMS go through: the container (email_sender, sms_sender, settings), set once it is built;
        # read on every send, so tests can swap the senders
        self.outbound: Any = None
        self.clock: Callable[[], datetime] | None = None  # tests: fixed "now" for quiet hours

    def notify(self, session: Session, case: Case, kind: str, text: str, *, sms: str | None = None) -> Notification:
        """`sms`: the pack text (`notify.sms.<sms>`) for a critical event that also goes out by SMS."""
        user = session.get(User, case.owner_id)
        channel = self.channels.get(user.channel) or self.channels["web"]
        n = Notification(user_id=user.id, case_id=case.id, channel=channel.name, kind=kind, text=text)
        via: list[str] = []
        errors: list[str] = []
        try:
            channel.send(user.external_id, text)
            n.delivered = True
            via.append(channel.name)
        except Exception as e:  # delivery failures must not break the case flow
            log.warning("delivery via %s failed: %s", channel.name, e)
            errors.append(str(e))
        for name, send in (("email", self._email), ("sms", self._sms)):
            try:
                if send(session, case, user, kind, text, sms):
                    via.append(name)
            except Exception as e:  # noqa: BLE001 — same: logged and kept on the row
                log.warning("notification %s via %s failed: %s", kind, name, e)
                errors.append(f"{name}: {e}")
        n.sent_via = ",".join(via) or None
        n.error = "; ".join(errors) or None
        session.add(n)
        return n

    # ---- e-mail and SMS ---------------------------------------------
    def _pack(self, case: Case) -> Any:
        if self.packs is None or not case.jurisdiction:
            return None
        try:
            return self.packs.pack(case.jurisdiction)
        except KeyError:
            return None

    def _site(self) -> str:
        site = getattr(getattr(self.outbound, "settings", None), "public_site_url", None) or "https://konsilier.com"
        return site.rstrip("/")

    def _link(self, case: Case) -> str:
        return f"{self._site()}/case/{case.id}"

    def _email(self, session: Session, case: Case, user: User, kind: str, text: str, sms: str | None) -> bool:
        sender = getattr(self.outbound, "email_sender", None)
        if kind not in EMAIL_KINDS or sender is None:
            return False
        to = verified_email(session, user)
        pack = self._pack(case)
        if not to or pack is None:
            return False
        lang = pack.lang(case.language)
        subject = pack.t(lang, f"notify.subject.{kind}", default="Konsiliér AI")
        body = "\n\n".join([text, pack.t(lang, "notify.open_case", link=self._link(case)),
                            pack.t(lang, "notify.footer", link=f"{self._site()}/account")])
        sender.send(to, subject, body)
        return True

    def _sms(self, session: Session, case: Case, user: User, kind: str, text: str, sms: str | None) -> bool:
        sender = getattr(self.outbound, "sms_sender", None)
        if not sms or sender is None:
            return False
        to = verified_phone(session, user)
        pack = self._pack(case)
        if not to or pack is None:
            return False
        local = self.clock().astimezone(pack.tz) if self.clock else pack.local_now()
        if quiet(local):
            log.info("notification %s: SMS skipped at night (%s local)", kind, local.strftime("%H:%M"))
            return False
        sender.send(to, "", pack.t(pack.lang(case.language), f"notify.sms.{sms}", link=self._link(case)))
        return True
