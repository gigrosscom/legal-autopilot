"""ChannelAdapter: how we reach the user (web inbox, Telegram, WhatsApp, ...)."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

# accounts made by a messenger bot: they answer the interview there (no draft screen) and their contact is known
MESSENGERS = frozenset({"telegram", "whatsapp"})


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


class WhatsAppChannel:
    """Through the WhatsApp bot (apps/bot, konsilier_bot.whatsapp): it alone holds the Cloud API token and knows
    whether the person wrote within the last 24 hours — WhatsApp lets a business write only then (no templates are
    used). Outside that window the bot refuses (HTTP 409) and the notification stays in the site inbox."""

    name = "whatsapp"

    def __init__(self, relay_url: str | None, secret: str):
        self.relay_url = relay_url
        self.secret = secret

    def send(self, external_id: str | None, text: str) -> None:
        if not self.relay_url or not external_id:
            raise RuntimeError("whatsapp channel not configured")
        r = httpx.post(self.relay_url, json={"to": external_id, "text": text},
                       headers={"X-Bot-Secret": self.secret}, timeout=15)
        if r.status_code == 409:
            raise RuntimeError("whatsapp: outside the 24-hour window")
        r.raise_for_status()


class RecordingChannel:
    """Test helper: remembers everything it was asked to send."""

    def __init__(self, name: str):
        self.name = name
        self.sent: list[tuple[str | None, str]] = []

    def send(self, external_id: str | None, text: str) -> None:
        self.sent.append((external_id, text))
