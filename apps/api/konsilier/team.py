"""E-mails to the platform team about things a person is waiting on (lawyer applications, lawyer requests)."""

from __future__ import annotations

import logging
from typing import Any


def notify_team(container: Any, subject: str, text: str) -> None:
    """Best effort: a mail outage must never lose the application or the request itself."""
    sender = container.email_sender
    if sender is None or not container.settings.team_email:
        return
    try:
        sender.send(container.settings.team_email, subject, text)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("team notification failed", exc_info=True)
