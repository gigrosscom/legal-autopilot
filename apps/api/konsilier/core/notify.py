"""Notifier: writes to the outbox and delivers through the user's channel adapter.

Every notification lands in the site inbox (the bell) and goes out through the user's channel (web or Telegram).
Key events also go further:
- e-mail, for `EMAIL_KINDS`, to a verified address while the person keeps e-mail on;
- SMS, only when the caller marks the event critical (document ready, payment confirmed, the response deadline
  due today or expired), to a verified phone, and never at night in the pack's local time (`QUIET_HOURS`).
Every notification also goes as a web push to each device the person turned notifications on for (see core/push);
a device the push service reports gone is forgotten.
A failed delivery never breaks the case flow: it is logged and written to the row.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters.channels import ChannelAdapter
from .models import Case, Identity, Notification, PushSubscription, User, utcnow
from .push import MAX_FAILURES, PushGone, payload

log = logging.getLogger(__name__)
_deferred = threading.local()  # Notifier.deferred: the sending collected while a fast request runs

# kinds worth an e-mail besides the inbox (case reports mail themselves, see konsilier.reports)
EMAIL_KINDS = frozenset({"payment", "document", "approval", "deadline_reminder", "deadline_expired", "handoff",
                         "lawyer"})
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
        # what e-mail, SMS and push go through: the container (email_sender, sms_sender, push_sender, settings), set
        # once it is built;
        # read on every send, so tests can swap the senders
        self.outbound: Any = None
        self.clock: Callable[[], datetime] | None = None  # tests: fixed "now" for quiet hours

    def notify(self, session: Session, case: Case, kind: str, text: str, *, sms: str | None = None) -> Notification:
        """`sms`: the pack text (`notify.sms.<sms>`) for a critical event that also goes out by SMS."""
        return self.notify_user(session, session.get(User, case.owner_id), kind, text, case=case, sms=sms)

    def notify_user(self, session: Session, user: User, kind: str, text: str, case: Case | None = None, *,
                    sms: str | None = None) -> Notification:
        """A message to a person, about one of their cases or about the account (e.g. a referral bonus). E-mail and
        SMS go out only for a case (their texts and link come from its pack); push goes out for every message."""
        channel = self.channels.get(user.channel) or self.channels["web"]
        n = Notification(user_id=user.id, case_id=case.id if case is not None else None, channel=channel.name,
                         kind=kind, text=text)
        later = getattr(_deferred, "jobs", None)
        if later is not None:  # the inbox row now, the sending after the commit (see deferred)
            session.add(n)
            session.flush()
            nid, uid, cid = n.id, user.id, case.id if case is not None else None

            def deliver(s: Session) -> None:
                row = s.get(Notification, nid)
                self._deliver(s, row, s.get(User, uid), s.get(Case, cid) if cid is not None else None,
                              kind, text, sms)
            later.append(deliver)
            return n
        self._deliver(session, n, user, case, kind, text, sms)
        session.add(n)
        return n

    @contextmanager
    def deferred(self) -> Iterator[list[Callable[[Session], None]]]:
        """Within the block a notification is written at once (the inbox row: the chat and the bell show it) and
        its sending — the channel, e-mail, SMS, push — is collected in the yielded list, to run after the commit
        with a new session. For a request that must answer fast (the Kaspi Pay push: konsilier/kaspi_parse.py)."""
        prev = getattr(_deferred, "jobs", None)
        jobs: list[Callable[[Session], None]] = []
        _deferred.jobs = jobs
        try:
            yield jobs
        finally:
            _deferred.jobs = prev

    def _deliver(self, session: Session, n: Notification, user: User, case: Case | None, kind: str, text: str,
                 sms: str | None) -> None:
        channel = self.channels.get(user.channel) or self.channels["web"]
        via: list[str] = []
        errors: list[str] = []
        try:
            channel.send(user.external_id, text)
            n.delivered = True
            via.append(channel.name)
        except Exception as e:  # delivery failures must not break the case flow
            log.warning("delivery via %s failed: %s", channel.name, e)
            errors.append(str(e))
        for name, send in (("email", self._email), ("sms", self._sms)) if case is not None else ():
            try:
                if send(session, case, user, kind, text, sms):
                    via.append(name)
            except Exception as e:  # noqa: BLE001 — same: logged and kept on the row
                log.warning("notification %s via %s failed: %s", kind, name, e)
                errors.append(f"{name}: {e}")
        try:
            if self._push(session, user, text, case):
                via.append("push")
        except Exception as e:  # noqa: BLE001 — same
            log.warning("notification %s via push failed: %s", kind, e)
            errors.append(f"push: {e}")
        n.sent_via = ",".join(via) or None
        n.error = "; ".join(errors) or None

    # ---- web push -----------------------------------------------------
    def _push(self, session: Session, user: User, text: str, case: Case | None) -> bool:
        """Sends to every device of the person; True when at least one push service took it. Devices the service
        reports gone, or failing MAX_FAILURES times in a row, are dropped; other failures raise after the loop."""
        sender = getattr(self.outbound, "push_sender", None)
        if sender is None:
            return False
        subs = session.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)).all()
        body = payload(text, case.id if case is not None else None)
        sent, failures = False, []
        for sub in subs:
            try:
                sender.send({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, body)
            except PushGone:
                session.delete(sub)
                continue
            except Exception as e:  # noqa: BLE001 — one device failing never stops the others
                sub.failed_count = (sub.failed_count or 0) + 1
                if sub.failed_count >= MAX_FAILURES:
                    session.delete(sub)
                failures.append(str(e))
                continue
            sub.last_ok_at, sub.failed_count = utcnow(), 0
            sent = True
        if failures and not sent:
            raise RuntimeError(failures[-1])
        return sent

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
        subject = pack.t(lang, f"notify.subject.{kind}", default="Konsilier AI")
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
