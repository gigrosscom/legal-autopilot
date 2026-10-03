"""ChannelAdapter: how we reach the user (web inbox, Telegram, ...)."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class ChannelAdapter(Protocol):
    name: str

    def send(self, external_id: str | None, text: str) -> None:
        """Deliver ``text``; raise on failure. Web delivery is the DB inbox itself."""


class WebChannel:
    name = "web"

    def send(self, external_id: str | None, text: str) -> None:
        return None  # the Notification row *is* the web inbox


class TelegramChannel:
    name = "telegram"

    def __init__(self, bot_token: str | None):
        self.bot_token = bot_token

    def send(self, external_id: str | None, text: str) -> None:
        if not self.bot_token or not external_id:
            raise RuntimeError("telegram channel not configured")
        r = httpx.post(f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                       json={"chat_id": external_id, "text": text}, timeout=10)
        r.raise_for_status()


class RecordingChannel:
    """Test helper: remembers everything it was asked to send."""

    def __init__(self, name: str):
        self.name = name
        self.sent: list[tuple[str | None, str]] = []

    def send(self, external_id: str | None, text: str) -> None:
        self.sent.append((external_id, text))
