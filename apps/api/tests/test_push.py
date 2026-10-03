"""Web push: the key, subscribing and unsubscribing, delivery through the Notifier, cleanup of gone devices, and the
real sender (VAPID-signed, encrypted payload) against a fake push service."""

from __future__ import annotations

import base64
import json
import os
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from konsilier.core.models import Case, LoginChallenge, Notification, PushSubscription
from konsilier.core.push import MAX_FAILURES, PushGone, WebPushSender, allowed_endpoint, payload
from konsilier.identity.senders import LogSender

from .test_auth import h, sent_code
from .test_e2e import web_user
from .test_notifications import new_case, owner_of

PUBLIC = "BExamplePublicKeyForTests"
FCM = "https://fcm.googleapis.com/fcm/send/"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class FakePush:
    """Records what would be sent; endpoints in `gone` answer 410, those in `broken` fail."""

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.gone: set[str] = set()
        self.broken: set[str] = set()

    def send(self, subscription: dict, body: str) -> None:
        endpoint = subscription["endpoint"]
        if endpoint in self.gone:
            raise PushGone("410")
        if endpoint in self.broken:
            raise RuntimeError("push service answered 500")
        assert subscription["keys"]["p256dh"] and subscription["keys"]["auth"]
        self.sent.append((endpoint, json.loads(body)))


@pytest.fixture
def push(ctx):
    ctx.container.settings.vapid_public_key = PUBLIC
    ctx.container.push_sender = FakePush()
    return ctx


def sub(endpoint: str) -> dict:
    return {"endpoint": endpoint, "keys": {"p256dh": "B" + "x" * 86, "auth": "a" * 22},
            "user_agent": "Mozilla/5.0 (Linux; Android 14)"}


def rows(ctx) -> list[PushSubscription]:
    with ctx.container.session_factory() as s:
        return list(s.query(PushSubscription).order_by(PushSubscription.id))


def notify(ctx, cid: str, kind: str, text: str) -> Notification:
    with ctx.container.session_factory() as s:
        n = ctx.container.notifier.notify(s, s.get(Case, uuid.UUID(cid)), kind, text)
        s.commit()
        s.refresh(n)
        s.expunge(n)
        return n


def test_key_is_404_while_push_is_off(ctx):
    assert ctx.container.push_sender is None
    assert ctx.client.get("/v1/push/key").status_code == 404
    api = web_user(ctx)
    assert api.post("/v1/push/subscribe", expect=404, json=sub(FCM + "a"))


def test_key_subscribe_and_unsubscribe(push):
    assert push.client.get("/v1/push/key").json() == {"key": PUBLIC}
    api, other = web_user(push), web_user(push)
    assert push.client.post("/v1/push/subscribe", json=sub(FCM + "a")).status_code == 401  # needs the token

    assert api.post("/v1/push/subscribe", json=sub(FCM + "a")) == {"ok": True}
    api.post("/v1/push/subscribe", json=sub(FCM + "a"))  # the same device again: still one row
    api.post("/v1/push/subscribe", json=sub("https://web.push.apple.com/QGx"))
    got = rows(push)
    assert [r.endpoint for r in got] == [FCM + "a", "https://web.push.apple.com/QGx"]
    assert got[0].user_agent == "Mozilla/5.0 (Linux; Android 14)" and got[0].failed_count == 0

    other.post("/v1/push/unsubscribe", json={"endpoint": FCM + "a"})  # someone else's device is never touched
    assert len(rows(push)) == 2
    api.post("/v1/push/unsubscribe", json={"endpoint": FCM + "a"})
    assert [r.endpoint for r in rows(push)] == ["https://web.push.apple.com/QGx"]

    # another account on the same device takes the subscription over
    other.post("/v1/push/subscribe", json=sub("https://web.push.apple.com/QGx"))
    (row,) = rows(push)
    assert str(row.user_id) == other.get("/v1/me").json()["id"]
    assert other.post("/v1/push/unsubscribe", json={"endpoint": "https://web.push.apple.com/QGx"}) == {"ok": True}
    assert rows(push) == []


@pytest.mark.parametrize("endpoint", ["http://fcm.googleapis.com/x", "https://169.254.169.254/latest",
                                      "https://evil.example/fcm.googleapis.com", "https://googleapis.com.evil.kz/x",
                                      "https://localhost:8000/v1"])
def test_only_browser_push_services(push, endpoint):
    assert not allowed_endpoint(endpoint)
    web_user(push).post("/v1/push/subscribe", expect=422, json=sub(endpoint))


def test_known_push_services_accepted():
    for e in (FCM + "x", "https://updates.push.services.mozilla.com/wpush/v2/x", "https://web.push.apple.com/Q",
              "https://wns2-par02p.notify.windows.com/w/?token=x"):
        assert allowed_endpoint(e), e


def test_payload_is_short_and_links_the_case():
    p = json.loads(payload("Документ   готов.\n" + "а" * 400, "abc"))
    assert p["title"] == "Konsilier" and p["url"] == "/case/abc"
    assert len(p["body"]) == 180 and p["body"].startswith("Документ готов. ") and p["body"].endswith("…")
    assert json.loads(payload("Бонус начислен"))["url"] == "/cases"


def test_every_notification_goes_to_every_device(push):
    api = web_user(push)
    cid = new_case(api)
    api.post("/v1/push/subscribe", json=sub(FCM + "phone"))
    api.post("/v1/push/subscribe", json=sub(FCM + "laptop"))
    stranger = web_user(push)
    stranger.post("/v1/push/subscribe", json=sub(FCM + "stranger"))
    fake = push.container.push_sender

    n = notify(push, cid, "report_update", "Отчёт по делу: следующий шаг — подать претензию.")
    assert n.sent_via == "web,push" and n.error is None
    assert [e for e, _ in fake.sent] == [FCM + "phone", FCM + "laptop"]
    assert fake.sent[0][1] == {"title": "Konsilier", "body": "Отчёт по делу: следующий шаг — подать претензию.",
                               "url": f"/case/{cid}"}
    assert all(r.last_ok_at is not None for r in rows(push) if r.endpoint != FCM + "stranger")

    # a message about the account, not a case: push too, to the list of cases
    with push.container.session_factory() as s:
        n = push.container.notifier.notify_user(s, owner_of(s, cid), "referral_bonus", "Бонус начислен")
        s.commit()
        assert n.sent_via == "web,push"
    assert fake.sent[-1][1]["url"] == "/cases"


def test_no_subscriptions_no_push(push):
    api = web_user(push)
    assert notify(push, new_case(api), "document", "Документ готов").sent_via == "web"
    assert push.container.push_sender.sent == []


def test_gone_devices_are_removed(push):
    api = web_user(push)
    cid = new_case(api)
    for name in ("old", "new"):
        api.post("/v1/push/subscribe", json=sub(FCM + name))
    push.container.push_sender.gone.add(FCM + "old")
    n = notify(push, cid, "document", "Документ готов")
    assert n.sent_via == "web,push" and n.error is None
    assert [r.endpoint for r in rows(push)] == [FCM + "new"]

    push.container.push_sender.gone.add(FCM + "new")  # the last device gone: nothing delivered, nothing to report
    n = notify(push, cid, "document", "Документ готов")
    assert n.sent_via == "web" and n.error is None and rows(push) == []


def test_failures_are_recorded_not_raised(push):
    api = web_user(push)
    cid = new_case(api)
    api.post("/v1/push/subscribe", json=sub(FCM + "flaky"))
    fake = push.container.push_sender
    fake.broken.add(FCM + "flaky")
    n = notify(push, cid, "document", "Документ готов")
    assert n.sent_via == "web" and n.error == "push: push service answered 500"
    assert rows(push)[0].failed_count == 1

    fake.broken.clear()  # it recovers: the count starts over
    assert notify(push, cid, "document", "Документ готов").sent_via == "web,push"
    assert rows(push)[0].failed_count == 0

    fake.broken.add(FCM + "flaky")  # failing again and again: dropped in the end
    for _ in range(MAX_FAILURES):
        notify(push, cid, "document", "Документ готов")
    assert rows(push) == []


class Down:
    def send(self, subscription: dict, body: str) -> None:
        raise RuntimeError("gateway down")


def test_push_failure_never_stops_email(push):
    from .test_lawyer_onboarding import Outbox
    from .test_notifications import verify

    push.container.email_sender = Outbox()
    api = web_user(push)
    cid = new_case(api)
    verify(push, cid, email="client@mail.kz")
    api.post("/v1/push/subscribe", json=sub(FCM + "a"))
    push.container.push_sender = Down()
    n = notify(push, cid, "document", "Документ готов")
    assert n.sent_via == "web,email" and "push: gateway down" in n.error


def test_sign_in_moves_the_device_to_the_account(push):
    """A new phone subscribes while still anonymous; signing in to an existing account takes the device along."""
    c, client = push.container, push.client
    c.email_sender = LogSender("email")

    def sign_in(token: str) -> str:
        with c.session_factory() as s:  # no waiting a minute before the second code
            s.query(LoginChallenge).delete()
            s.commit()
        client.post("/v1/auth/email/start", json={"target": "a@mail.kz"}, headers=h(token))
        return client.post("/v1/auth/email/verify", json={"target": "a@mail.kz", "code": sent_code(c.email_sender)},
                           headers=h(token)).json()["token"]

    account = sign_in(client.post("/v1/users", json={"language": "ru"}).json()["token"])
    device = client.post("/v1/users", json={"language": "ru"}).json()["token"]
    assert client.post("/v1/push/subscribe", json=sub(FCM + "phone"), headers=h(device)).status_code == 200
    assert sign_in(device) == account
    (row,) = rows(push)
    assert str(row.user_id) == client.get("/v1/me", headers=h(account)).json()["id"]


# ---- the real sender: what reaches the push service --------------------------------------------------------------
class FakeService:
    def __init__(self, status: int = 201):
        self.status = status
        self.posts: list[dict] = []

    def post(self, endpoint, timeout=None, data=None, headers=None, **kw):
        self.posts.append({"endpoint": endpoint, "data": data, "headers": headers})
        return type("R", (), {"status_code": self.status, "reason": "", "text": "", "headers": {}})()


def device_keys():
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    return key, {"endpoint": FCM + "real", "keys": {"p256dh": b64url(public), "auth": b64url(auth)}}, auth


def test_web_push_sender_signs_and_encrypts():
    import http_ece

    server = ec.generate_private_key(ec.SECP256R1())
    sender = WebPushSender(b64url(server.private_numbers().private_value.to_bytes(32, "big")),
                           "mailto:support@konsilier.com")
    sender.http = FakeService()
    key, subscription, auth = device_keys()
    sender.send(subscription, payload("Документ готов", "abc"))

    (sent,) = sender.http.posts
    assert sent["endpoint"] == FCM + "real"
    assert sent["headers"]["content-encoding"] == "aes128gcm" and int(sent["headers"]["ttl"]) == 24 * 3600
    assert sent["headers"]["authorization"].startswith("vapid t=")
    plain = http_ece.decrypt(sent["data"], private_key=key, auth_secret=auth, version="aes128gcm")
    assert json.loads(plain) == {"title": "Konsilier", "body": "Документ готов", "url": "/case/abc"}

    for status, error in ((410, PushGone), (404, PushGone), (500, RuntimeError)):
        sender.http = FakeService(status)
        with pytest.raises(error):
            sender.send(subscription, "{}")
