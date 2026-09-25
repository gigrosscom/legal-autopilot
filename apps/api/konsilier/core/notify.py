"""Notifier: writes to the outbox and delivers through the user's channel adapter."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .adapters.channels import ChannelAdapter
from .models import Case, Notification, User

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, channels: dict[str, ChannelAdapter]):
        self.channels = channels

    def notify(self, session: Session, case: Case, kind: str, text: str) -> Notification:
        user = session.get(User, case.owner_id)
        channel = self.channels.get(user.channel) or self.channels["web"]
        n = Notification(user_id=user.id, case_id=case.id, channel=channel.name, kind=kind, text=text)
        try:
            channel.send(user.external_id, text)
            n.delivered = True
        except Exception as e:  # delivery failures must not break the case flow
            log.warning("delivery via %s failed: %s", channel.name, e)
            n.error = str(e)
        session.add(n)
        return n
