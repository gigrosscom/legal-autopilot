"""Web push: notifications on the person's phone or computer, from the site or the installed app.

The browser subscribes with our VAPID public key (GET /v1/push/key) and hands us its push service endpoint and keys
(POST /v1/push/subscribe). The Notifier then sends every notification of that person to each of their devices.
Keys come from VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY (deploy/vapid_keys.py prints a pair); without them push is off.
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.parse import urlsplit

# Push services of the browsers (Chrome / Edge / Android, Firefox, Safari / iOS, Windows). Subscriptions to any other
# host are refused: the server posts to the endpoint, so it must never be an address someone picked.
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com",
              "push.services.mozilla.com", ".push.apple.com", ".notify.windows.com")
TITLE = "Konsilier"
BODY_MAX = 180
MAX_FAILURES = 10  # failures in a row after which a subscription is dropped


class PushGone(Exception):
    """The push service no longer knows the subscription (404 / 410): the device unsubscribed or reinstalled."""


class PushSender(Protocol):
    def send(self, subscription: dict[str, Any], payload: str) -> None: ...


def allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return False
    return any(host.endswith(h) if h.startswith(".") else host == h for h in PUSH_HOSTS)


def payload(text: str, case_id: Any = None) -> str:
    """What the service worker shows: title, the first ~180 characters and the page to open on a tap."""
    body = " ".join(text.split())
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX - 1].rstrip() + "…"
    return json.dumps({"title": TITLE, "body": body, "url": f"/case/{case_id}" if case_id else "/cases"},
                      ensure_ascii=False)


class WebPushSender:
    """Sends through the browser's push service, signed with our VAPID key (RFC 8292), encrypted (RFC 8291)."""

    def __init__(self, private_key: str, subject: str, ttl: int = 24 * 3600, timeout: float = 10.0):
        from py_vapid import Vapid

        self.vapid = Vapid.from_string(private_key)
        self.subject = subject
        self.ttl = ttl
        self.timeout = timeout
        self.http: Any = None  # a requests.Session to post with (tests: a fake); None → a new connection each time

    def send(self, subscription: dict[str, Any], payload: str) -> None:
        from pywebpush import WebPushException, webpush

        try:
            webpush(subscription, payload, vapid_private_key=self.vapid, vapid_claims={"sub": self.subject},
                    ttl=self.ttl, timeout=self.timeout, requests_session=self.http)
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                raise PushGone(str(status)) from e
            raise RuntimeError(f"push service answered {status}") from e


def build_push(settings: Any) -> WebPushSender | None:
    if not (settings.vapid_public_key and settings.vapid_private_key):
        return None
    return WebPushSender(settings.vapid_private_key, settings.vapid_subject)
