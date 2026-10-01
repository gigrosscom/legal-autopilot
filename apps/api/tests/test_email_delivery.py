"""«Мастер отправки»: e-mail through Resend (attachments, Reply-To, copy, limits, Svix webhook) and messenger proofs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from konsilier.api.delivery import followups, verify_svix
from konsilier.contacts import find_in_text
from konsilier.core.models import Action, Case, Deadline, Evidence, Filing, Identity, Notification, User
from konsilier.identity.senders import SendError

from .test_document_signing import FakeVerifier, sign
from .test_e2e import web_user

CLIENT = "client@mail.kz"
SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


class FakeMailer:
    def __init__(self, fail: bool = False):
        self.sent: list[dict] = []
        self.fail = fail

    def send_letter(self, **kw):
        if self.fail:
            raise SendError("resend 500")
        self.sent.append(kw)
        return f"re_{len(self.sent)}"


@pytest.fixture
def case(ctx):
    """A ready document of a case whose owner has a confirmed e-mail; paid unless the test says otherwise."""
    c = ctx.container
    c.engine.config.approval_required_first_n = 0
    c.signature_verifier = FakeVerifier()
    c.claims_mailer = FakeMailer()
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "My dummy widget was never delivered", "country": "XX",
                                                  "language": "en"})["case"]["id"]
    api.answer(cid, "Widget Corp")
    api.answer(cid, "1200")
    aid = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]["id"]
    with c.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        user = s.get(User, case.owner_id)
        user.email, user.display_name = CLIENT, "Ivan Ivanov"
        s.add(Identity(user_id=user.id, kind="email", subject_hash="h-" + cid, display="c•••@mail.kz"))
        s.get(Action, uuid.UUID(aid)).unlocked_by = "credit"
        s.commit()
    return ctx, api, cid, aid


def url(cid, aid, tail=""):
    return f"/v1/cases/{cid}/actions/{aid}{tail}"


def test_send_happy_path_with_attachments_reply_to_copy_and_deadline(case):
    ctx, api, cid, aid = case
    start = api.post(url(cid, aid, "/sign/start"), json={"method": "ncalayer"})
    api.post(url(cid, aid, "/sign"), json={"session_id": start["session_id"], "cms": sign(start["data"])})
    pre = api.post(url(cid, aid, "/email/preview"), json={"to": "Shop@Example.kz"})
    assert pre["to"] == "shop@example.kz" and pre["reply_to"] == CLIENT and pre["cc"] == CLIENT
    assert "Konsiliér AI" in pre["from"] and "claims@konsilier.com" in pre["from"]
    assert "Sent via the Konsiliér AI service on behalf of the sender." in pre["text"]
    assert "Ivan" in pre["text"] or "Иванов" in pre["text"]
    assert ctx.container.claims_mailer.sent == []  # a preview sends nothing

    r = ctx.client.post(url(cid, aid, "/email"), headers=api.h, json={"to": "shop@example.kz"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "confirm_required"
    out = api.post(url(cid, aid, "/email"), json={"to": "shop@example.kz", "confirm": True})
    sent = ctx.container.claims_mailer.sent[0]
    assert sent["to"] == "shop@example.kz" and sent["reply_to"] == CLIENT and sent["cc"] == [CLIENT]
    names = [n for n, _ in sent["attachments"]]
    assert len(names) == 2 and names[1].endswith(".cms")
    doc = sent["attachments"][0][1]
    assert out["filing"]["status"] == "sent" and out["filing"]["doc_sha256"] == hashlib.sha256(doc).hexdigest()
    assert out["filing"]["recipient"] == "shop@example.kz"

    a = out["case"]["actions"][0]
    assert a["status"] == "submitted" and a["submitted_via"] == "email" and a["submitted_at"]
    assert a["filings"][0]["id"] == out["filing"]["id"]
    assert out["case"]["status"] == "awaiting_response"
    with ctx.container.session_factory() as s:
        f = s.query(Filing).one()
        assert f.external_id == "re_1" and f.consent_text_version == "email-v1" and f.signature_id is not None
        assert [e["type"] for e in f.events] == ["confirmed", "sent"]
        dl = s.query(Deadline).one()  # the response deadline counts from the sending
        assert dl.status == "active" and dl.created_at is not None
    assert a["deadline"] and a["deadline"]["due_date"] > a["submitted_at"][:10]


def test_unpaid_document_is_refused(case):
    ctx, api, cid, aid = case
    with ctx.container.session_factory() as s:
        s.get(Action, uuid.UUID(aid)).unlocked_by = "free"
        s.commit()
    r = ctx.client.post(url(cid, aid, "/email"), headers=api.h, json={"to": "shop@example.kz", "confirm": True})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "payment_required"
    view = api.get(f"/v1/cases/{cid}").json()
    assert view["actions"][0]["email_send"] == {"available": False, "reason": "payment_required", "left": 3}
    assert ctx.container.claims_mailer.sent == []


def test_confirmed_email_is_required(case):
    ctx, api, cid, aid = case
    with ctx.container.session_factory() as s:
        s.query(Identity).delete()
        s.commit()
    r = ctx.client.post(url(cid, aid, "/email/preview"), headers=api.h, json={"to": "shop@example.kz"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "email_required"


@pytest.mark.parametrize("bad", ["a@b.kz, c@d.kz", "a@b.kz;c@d.kz", "a b@c.kz", "no-at-sign.kz", "x@nodot",
                                 "Name <a@b.kz>", "a@@b.kz", "a..b@c.kz"])
def test_one_valid_recipient_only(case, bad):
    ctx, api, cid, aid = case
    r = ctx.client.post(url(cid, aid, "/email"), headers=api.h, json={"to": bad, "confirm": True})
    assert r.status_code == 422, bad


def test_limits_per_document_and_per_case_day(case):
    ctx, api, cid, aid = case
    for i in range(3):
        api.post(url(cid, aid, "/email"), json={"to": f"shop{i}@example.kz", "confirm": True})
    r = ctx.client.post(url(cid, aid, "/email"), headers=api.h, json={"to": "x@example.kz", "confirm": True})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "limit_document"
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["email_send"]["reason"] == "limit_document"
    ctx.settings.email_send_per_document = 10
    ctx.settings.email_send_per_case_day = 4
    api.post(url(cid, aid, "/email"), json={"to": "y@example.kz", "confirm": True})
    r = ctx.client.post(url(cid, aid, "/email"), headers=api.h, json={"to": "z@example.kz", "confirm": True})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "limit_case_day"
    # a day later the case may send again
    with ctx.container.session_factory() as s:
        for f in s.query(Filing).all():
            f.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        s.commit()
    api.post(url(cid, aid, "/email"), json={"to": "z@example.kz", "confirm": True})


def test_rate_limit_per_user_counts_failed_attempts(case):
    ctx, api, cid, aid = case
    ctx.container.claims_mailer = FakeMailer(fail=True)
    ctx.settings.email_send_per_user_hour = 2
    for _ in range(2):
        r = ctx.client.post(url(cid, aid, "/email"), headers=api.h, json={"to": "s@example.kz", "confirm": True})
        assert r.status_code == 502 and r.json()["detail"]["code"] == "send_failed"
    r = ctx.client.post(url(cid, aid, "/email"), headers=api.h, json={"to": "s@example.kz", "confirm": True})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many"
    view = api.get(f"/v1/cases/{cid}").json()
    a = view["actions"][0]
    assert a["status"] == "ready" and [f["status"] for f in a["filings"]] == ["failed", "failed"]


def test_off_without_resend(case):
    ctx, api, cid, aid = case
    ctx.container.claims_mailer = None
    r = ctx.client.post(url(cid, aid, "/email/preview"), headers=api.h, json={"to": "s@example.kz"})
    assert r.status_code == 503
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["email_send"]["reason"] == "unavailable"


def test_other_people_cannot_send(case):
    ctx, api, cid, aid = case
    other = web_user(ctx)
    r = ctx.client.post(url(cid, aid, "/email"), headers=other.h, json={"to": "s@example.kz", "confirm": True})
    assert r.status_code in (403, 404)


# ------------------------------------------------------------------ Resend webhook (Svix signature)
def svix_headers(raw: bytes, secret: str = SECRET, ts: int | None = None, msg_id: str = "msg_1") -> dict[str, str]:
    ts = ts if ts is not None else int(time.time())
    key = base64.b64decode(secret.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + raw, hashlib.sha256).digest()).decode()
    return {"svix-id": msg_id, "svix-timestamp": str(ts), "svix-signature": f"v1,{sig}",
            "content-type": "application/json"}


def event(kind: str, email_id: str = "re_1") -> bytes:
    return json.dumps({"type": kind, "created_at": "2026-10-01T10:00:00Z",
                       "data": {"email_id": email_id, "to": ["shop@example.kz"]}}).encode()


def test_webhook_is_off_without_secret(case):
    ctx, *_ = case
    raw = event("email.delivered")
    assert ctx.client.post("/v1/webhooks/resend", content=raw, headers=svix_headers(raw)).status_code == 404


def test_webhook_signature_and_statuses(case):
    ctx, api, cid, aid = case
    ctx.settings.resend_webhook_secret = SECRET
    api.post(url(cid, aid, "/email"), json={"to": "shop@example.kz", "confirm": True})
    raw = event("email.delivered")
    bad = svix_headers(raw, secret="whsec_" + base64.b64encode(b"another-secret-another-secret!!").decode())
    assert ctx.client.post("/v1/webhooks/resend", content=raw, headers=bad).status_code == 401
    old = svix_headers(raw, ts=int(time.time()) - 3600)
    assert ctx.client.post("/v1/webhooks/resend", content=raw, headers=old).status_code == 401
    assert ctx.client.post("/v1/webhooks/resend", content=raw, headers={}).status_code == 401
    r = ctx.client.post("/v1/webhooks/resend", content=raw, headers=svix_headers(raw))
    assert r.status_code == 200 and r.json() == {"ok": True, "matched": True, "status": "delivered"}
    f = api.get(f"/v1/cases/{cid}").json()["actions"][0]["filings"][0]
    assert f["status"] == "delivered" and f["delivered_at"] and f["events"][-1]["type"] == "delivered"
    # an unknown id (a sign-in code) is accepted and ignored
    other = event("email.delivered", "re_999")
    assert ctx.client.post("/v1/webhooks/resend", content=other,
                           headers=svix_headers(other)).json()["matched"] is False
    # a bounce wins and the client is told
    raw = event("email.bounced")
    assert ctx.client.post("/v1/webhooks/resend", content=raw, headers=svix_headers(raw)).json()["status"] == "bounced"
    with ctx.container.session_factory() as s:
        texts = [n.text for n in s.query(Notification).filter(Notification.kind == "delivery")]
    assert any("not delivered" in t for t in texts)


def test_verify_svix_accepts_one_of_several_signatures():
    raw = b'{"a":1}'
    h = svix_headers(raw, ts=1_700_000_000)
    h["svix-signature"] = "v1,AAAA " + h["svix-signature"]
    assert verify_svix(SECRET, h, raw, now=1_700_000_100)
    assert not verify_svix(SECRET, h, raw + b" ", now=1_700_000_100)


# ------------------------------------------------------------------ the wizard: contacts and messenger proofs
def test_contacts_found_in_documents_and_story_with_sources(case):
    ctx, api, cid, aid = case
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        s.add(Evidence(case_id=c.id, kind="receipt", filename="check.pdf", content_type="application/pdf",
                       text="ТОО «Мебель» BIN 123456789012 тел. 8 (701) 555-44-33 info@mebel.kz www.mebel.kz",
                       extracted_facts={}))
        c.initial_text = "Магазин в инстаграме: instagram @mebel_kz, мой номер +7 777 000 11 22"
        s.get(User, c.owner_id).phone = "+77770001122"
        s.commit()
    plan = api.get(url(cid, aid, "/send")).json()
    found = {(x["kind"], x["value"]): x["sources"] for x in plan["contacts"]}
    assert found[("phone", "+77015554433")][0]["type"] == "evidence"
    assert found[("phone", "+77015554433")][0]["kind"] == "receipt"
    assert ("email", "info@mebel.kz") in found and ("website", "mebel.kz") in found
    assert ("bin", "123456789012") in found
    assert found[("instagram", "mebel_kz")][0]["type"] == "story"
    assert ("phone", "+77770001122") not in found  # the client's own number
    assert len(plan["message"].splitlines()) <= 5 and "PDF" in plan["message"]
    assert plan["reply_to"] == CLIENT and plan["email"]["available"] is True


def test_messenger_proof_starts_the_deadline_and_keeps_the_screenshot(case):
    ctx, api, cid, aid = case
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = ctx.client.post(url(cid, aid, "/send/proof"), headers=api.h,
                        data={"channel": "whatsapp", "recipient": "+77015554433"},
                        files={"file": ("shot.png", png, "image/png")})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["filing"]["channel"] == "whatsapp" and out["filing"]["has_receipt"]
    a = out["case"]["actions"][0]
    assert a["status"] == "submitted" and a["submitted_via"] == "whatsapp"
    fid = out["filing"]["id"]
    got = api.get(f"/v1/cases/{cid}/filings/{fid}/receipt")
    assert got.content == png
    # a later screenshot «прочитано»
    r = ctx.client.post(f"/v1/cases/{cid}/filings/{fid}/receipt", headers=api.h,
                        files={"file": ("read.png", png + b"1", "image/png")})
    assert r.status_code == 200 and r.json()["filing"]["events"][-1]["type"] == "receipt"
    bad = ctx.client.post(url(cid, aid, "/send/proof"), headers=api.h, data={"channel": "pigeon"})
    assert bad.status_code == 422


def test_messenger_proofs_do_not_use_up_email_letters(case):
    ctx, api, cid, aid = case
    for _ in range(3):
        ctx.client.post(url(cid, aid, "/send/proof"), headers=api.h, data={"channel": "whatsapp"})
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["email_send"] == {"available": True, "reason": None,
                                                                             "left": 3}


def test_followup_a_day_later_once(case):
    ctx, api, cid, aid = case
    ctx.client.post(url(cid, aid, "/send/proof"), headers=api.h, data={"channel": "telegram"})
    job = followups(ctx.container)
    with ctx.container.session_factory() as s:
        assert job(s, datetime.now(timezone.utc)) == 0  # not yet
        assert job(s, datetime.now(timezone.utc) + timedelta(hours=25)) == 1
        assert job(s, datetime.now(timezone.utc) + timedelta(hours=50)) == 0
        s.commit()
        assert s.query(Notification).filter(Notification.kind == "delivery").count() == 1


def test_resend_payload_has_attachments_reply_to_and_copy(monkeypatch):
    from konsilier.identity import senders

    seen = {}

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "re_abc"}

    def post(url, **kw):
        seen.update(kw, url=url)
        return R()

    monkeypatch.setattr(senders.httpx, "post", post)
    mailer = senders.ResendEmail("key", "Konsiliér AI <claims@konsilier.com>")
    rid = mailer.send_letter(to="shop@example.kz", subject="Claim", text="Hello", reply_to=CLIENT, cc=[CLIENT],
                             attachments=[("a.pdf", b"%PDF"), ("a.pdf.cms", b"CMS")], idempotency_key="filing-1")
    assert rid == "re_abc" and seen["url"] == "https://api.resend.com/emails"
    body = seen["json"]
    assert body["to"] == ["shop@example.kz"] and body["reply_to"] == [CLIENT] and body["cc"] == [CLIENT]
    assert body["attachments"] == [{"filename": "a.pdf", "content": base64.b64encode(b"%PDF").decode()},
                                   {"filename": "a.pdf.cms", "content": base64.b64encode(b"CMS").decode()}]
    assert seen["headers"]["Idempotency-Key"] == "filing-1"


def test_find_in_text_ignores_our_and_public_sites():
    found = find_in_text("see konsilier.com and egov.kz, write to a@konsilier.com; shop: best-shop.kz")
    assert found == [("website", "best-shop.kz")]
