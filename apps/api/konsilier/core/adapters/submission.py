"""SubmissionAdapter: how a prepared document reaches the addressee.

The applicant is always the user. ``user_submits`` only produces instructions;
``email`` sends the document on the user's explicit request, from the user's name.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


@dataclass
class SubmissionResult:
    via: str
    reference: str | None = None


class SubmissionAdapter(Protocol):
    name: str

    def submit(self, *, to_email: str | None, subject: str, body: str, reply_to: str | None,
               attachments: list[tuple[str, bytes, str]]) -> SubmissionResult: ...


class UserSubmits:
    name = "user_submits"

    def submit(self, **_: object) -> SubmissionResult:
        return SubmissionResult(via=self.name)


class EmailSubmission:
    name = "email"

    def __init__(self, host: str | None, port: int, sender: str):
        self.host, self.port, self.sender = host, port, sender

    def submit(self, *, to_email: str | None, subject: str, body: str, reply_to: str | None,
               attachments: list[tuple[str, bytes, str]]) -> SubmissionResult:
        if not self.host:
            raise RuntimeError("SMTP is not configured")
        if not to_email:
            raise ValueError("addressee e-mail is unknown")
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to
        msg["Subject"] = subject
        msg.set_content(body)
        for filename, data, ctype in attachments:
            maintype, subtype = ctype.split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            smtp.send_message(msg)
        return SubmissionResult(via=self.name, reference=msg.get("Message-ID"))
