"""The operations centre: two desks (lawyers, clients), their operators and e-mails about new items."""

from __future__ import annotations

import logging
from typing import Any, Literal

Desk = Literal["lawyers", "clients"]


def desk_emails(settings: Any, desk: Desk) -> list[str]:
    raw = settings.ops_lawyers_emails if desk == "lawyers" else settings.ops_clients_emails
    return [e.strip().lower() for e in (raw or "").split(",") if e.strip()]


def desks_of(settings: Any, email: str | None) -> list[Desk]:
    """Desks an operator may open: their verified e-mail must be listed for the desk."""
    if not email:
        return []
    e = email.strip().lower()
    return [d for d in ("lawyers", "clients") if e in desk_emails(settings, d)]


def notify_team(container: Any, subject: str, text: str, desk: Desk = "lawyers") -> None:
    """E-mail the desk's operators. Best effort: a mail outage must never lose the item itself."""
    sender = container.email_sender
    to = desk_emails(container.settings, desk) or ([container.settings.team_email] if container.settings.team_email else [])
    if sender is None or not to:
        return
    for addr in to:
        try:
            sender.send(addr, subject, text)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("desk notification to %s failed", addr, exc_info=True)
