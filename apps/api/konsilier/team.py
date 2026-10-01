"""The operations centre: two desks (lawyers, clients), their operators and e-mails about new items."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

Desk = Literal["lawyers", "clients"]

# owner 01.10: QA / smoke runs must not mail the team. A test account: the is_test flag (smoke checks), a test source
# (?src=team-test), or a test name or address («Тест…», «Person 0456», «Пилот Ссылкин», qa-test@…, @resend.dev)
TEST_SOURCES = frozenset({"team-test", "qa-test", "smoke", "test"})
TEST_MARK = re.compile(r"qa-test|team-test|smoke|@resend\.dev|@example\.(com|org)|^\s*(тест|test)(\b|[\s_-])|"
                       r"^\s*person\s*\d+|ссылкин", re.I)


def is_test_text(*texts: str | None) -> bool:
    return any(TEST_MARK.search(t or "") for t in texts)


def is_test_user(user: Any) -> bool:
    """A test account: never mailed about to the team, kept out of the boards unless asked for."""
    if user is None:
        return False
    return (bool(getattr(user, "is_test", False)) or (getattr(user, "source", None) or "") in TEST_SOURCES
            or is_test_text(getattr(user, "email", None), getattr(user, "display_name", None)))


def desk_emails(settings: Any, desk: Desk) -> list[str]:
    raw = settings.ops_lawyers_emails if desk == "lawyers" else settings.ops_clients_emails
    return [e.strip().lower() for e in (raw or "").split(",") if e.strip()]


def desks_of(settings: Any, email: str | None) -> list[Desk]:
    """Desks an operator may open: their verified e-mail must be listed for the desk."""
    if not email:
        return []
    e = email.strip().lower()
    return [d for d in ("lawyers", "clients") if e in desk_emails(settings, d)]


def notify_team(container: Any, subject: str, text: str, desk: Desk = "lawyers", also: str | None = None,
                test: bool = False) -> None:
    """E-mail the desk's operators (and `also`: extra comma-separated addresses that get the letter but no desk
    access). Best effort: a mail outage must never lose the item itself. Nothing is sent for a test account."""
    if test:
        return
    sender = container.email_sender
    to = desk_emails(container.settings, desk) or ([container.settings.team_email] if container.settings.team_email else [])
    to += [e.strip().lower() for e in (also or "").split(",") if e.strip() and e.strip().lower() not in to]
    if sender is None or not to:
        return
    for addr in to:
        try:
            sender.send(addr, subject, text)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("desk notification to %s failed", addr, exc_info=True)
