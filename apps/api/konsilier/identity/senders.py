"""Delivery of one-time codes. Providers are chosen by settings; none configured → the method is off."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class SendError(RuntimeError):
    pass


class Sender(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class ResendEmail:
    def __init__(self, api_key: str, sender: str):
        self.api_key, self.sender = api_key, sender

    def send(self, to: str, subject: str, text: str) -> None:
        r = httpx.post("https://api.resend.com/emails", timeout=15,
                       headers={"Authorization": f"Bearer {self.api_key}"},
                       json={"from": self.sender, "to": [to], "subject": subject, "text": text})
        if r.status_code >= 300:
            raise SendError(f"resend {r.status_code}")


class SmtpEmail:
    def __init__(self, host: str, port: int, sender: str):
        self.host, self.port, self.sender = host, port, sender

    def send(self, to: str, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(text)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as s:
                s.send_message(msg)
        except OSError as e:
            raise SendError(f"smtp {e.__class__.__name__}") from e


class MobizonSms:
    """Mobizon SMS gateway. https://mobizon.kz/help/api-docs"""

    def __init__(self, api_key: str, sender: str | None):
        self.api_key, self.sender = api_key, sender

    def send(self, to: str, subject: str, text: str) -> None:
        params = {"recipient": to.lstrip("+"), "text": text, "apiKey": self.api_key, "output": "json"}
        if self.sender:
            params["from"] = self.sender
        r = httpx.get("https://api.mobizon.kz/service/message/sendsmsmessage", params=params, timeout=15)
        if r.status_code >= 300 or r.json().get("code") not in (0, "0"):
            raise SendError(f"mobizon {r.status_code}")


class SmscSms:
    """SMSC.kz. https://smsc.kz/api/http/"""

    def __init__(self, login: str, password: str, sender: str | None):
        self.login, self.password, self.sender = login, password, sender

    def send(self, to: str, subject: str, text: str) -> None:
        params = {"login": self.login, "psw": self.password, "phones": to.lstrip("+"), "mes": text,
                  "fmt": 3, "charset": "utf-8"}
        if self.sender:
            params["sender"] = self.sender
        r = httpx.get("https://smsc.kz/sys/send.php", params=params, timeout=15)
        if r.status_code >= 300 or "error" in r.json():
            raise SendError(f"smsc {r.status_code}")


class LogSender:
    """Development only: writes that a code was sent, never the code itself."""

    def __init__(self, channel: str):
        self.channel = channel
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, text))
        log.info("%s code issued (log sender, not delivered)", self.channel)


def build_email(settings) -> Sender | None:
    if settings.resend_api_key:
        return ResendEmail(settings.resend_api_key, settings.email_from)
    if settings.smtp_host:
        return SmtpEmail(settings.smtp_host, settings.smtp_port, settings.email_from)
    if settings.dev_show_codes:
        return LogSender("email")
    return None


def build_sms(settings) -> Sender | None:
    p = (settings.sms_provider or "").lower()
    if p == "mobizon" and settings.sms_api_key:
        return MobizonSms(settings.sms_api_key, settings.sms_sender)
    if p == "smsc" and settings.smsc_login and settings.smsc_password:
        return SmscSms(settings.smsc_login, settings.smsc_password, settings.sms_sender)
    if p == "log":
        return LogSender("sms")
    return None
