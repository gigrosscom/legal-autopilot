"""WhatsApp bot support in the API: its accounts, the one-time sign-in link, notifications through the bot's relay
(the 24-hour window), the interview cap and payment without a contact code, transcription limits for the bot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from konsilier.core.adapters.channels import WhatsAppChannel
from konsilier.core.models import LoginChallenge, User
from konsilier.transcribe import SlidingLimiter

from .test_e2e import Api
from .test_transcribe import FakeTranscriber, _post

BOT = {"X-Bot-Secret": "bot"}


def wa_user(ctx, wa_id: str = "77010001122") -> Api:
    r = ctx.client.post("/v1/users/whatsapp", json={"wa_id": wa_id}, headers=BOT)
    assert r.status_code == 200, r.text
    return Api(ctx, r.json()["token"])


def test_whatsapp_accounts_one_per_number_and_only_for_the_bot(ctx):
    assert ctx.client.post("/v1/users/whatsapp", json={"wa_id": "77010001122"}).status_code == 403
    assert ctx.client.post("/v1/users/whatsapp", json={"wa_id": "+7 701"}, headers=BOT).status_code == 422
    a, b = wa_user(ctx), wa_user(ctx)
    assert a.h == b.h and wa_user(ctx, "77010009999").h != a.h
    with ctx.container.session_factory() as s:
        user = s.query(User).filter_by(external_id="77010001122").one()
        assert user.channel == "whatsapp" and user.source == "whatsapp"


def test_sign_in_link_opens_the_same_account_once(ctx):
    api = wa_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": "Купил телефон, сломался через неделю, магазин не берёт"})
    # only the bot asks for a link, for its own person
    assert ctx.client.post("/v1/auth/link", headers=api.h).status_code == 403
    code = ctx.client.post("/v1/auth/link", headers={**api.h, **BOT}).json()["code"]
    signed = ctx.client.post("/v1/auth/link/redeem", json={"code": code})
    assert signed.status_code == 200
    token = signed.json()["token"]
    assert ctx.client.get(f"/v1/cases/{case['case']['id']}",
                          headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert ctx.client.post("/v1/auth/link/redeem", json={"code": code}).status_code == 410
    assert ctx.client.post("/v1/auth/link/redeem", json={"code": "x" * 32}).status_code == 410
    # an hour later the link is dead
    code = ctx.client.post("/v1/auth/link", headers={**api.h, **BOT}).json()["code"]
    with ctx.container.session_factory() as s:
        for ch in s.query(LoginChallenge).filter_by(kind="link", consumed_at=None):
            ch.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.commit()
    assert ctx.client.post("/v1/auth/link/redeem", json={"code": code}).status_code == 410


def test_whatsapp_case_keeps_the_bot_interview_and_pays_without_a_contact_code(ctx):
    ctx.container.engine.config.intake_max_questions = -1  # the site's «3 клика»: no questions on the site
    api = wa_user(ctx)
    out = api.post("/v1/cases", expect=201, json={
        "text": "Займ в МФО оформили мошенники 01.09.2026 на 50000, я не брал"})
    assert out["case"]["status"] == "intake" and out["reply"]["question"]  # the bot asks (up to four questions)
    from konsilier.api.routes import contact_to_confirm
    with ctx.container.session_factory() as s:
        owner = s.query(User).filter_by(channel="whatsapp").one()
        assert contact_to_confirm(ctx.container, owner) == []


class _Resp:
    def __init__(self, status: int):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=httpx.Request("POST", "http://x"),
                                        response=httpx.Response(self.status_code))


def test_whatsapp_channel_relays_through_the_bot(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return _Resp(200 if json["to"] == "770" else 409)

    monkeypatch.setattr(httpx, "post", fake_post)
    ch = WhatsAppChannel("http://whatsapp:8080/whatsapp/notify", "bot")
    ch.send("770", "Документ готов")
    assert calls == [("http://whatsapp:8080/whatsapp/notify", {"to": "770", "text": "Документ готов"},
                      {"X-Bot-Secret": "bot"})]
    with pytest.raises(RuntimeError, match="24-hour window"):
        ch.send("771", "x")
    with pytest.raises(RuntimeError, match="not configured"):
        WhatsAppChannel(None, "bot").send("770", "x")


def test_transcription_from_the_bot_is_not_bounded_by_its_one_address(ctx):
    ctx.container.transcriber = FakeTranscriber()
    ctx.container.transcribe_limits = (SlidingLimiter(5), SlidingLimiter(2))
    people = [wa_user(ctx, f"7701000000{i}") for i in range(4)]
    codes = [_post(ctx.client, p.h["Authorization"][7:], headers=BOT).status_code for p in people]
    assert codes == [200, 200, 200, 200]
    # without the bot secret the address limit applies as before
    assert _post(ctx.client, people[0].h["Authorization"][7:]).status_code == 200
    assert _post(ctx.client, people[1].h["Authorization"][7:]).status_code == 200
    assert _post(ctx.client, people[2].h["Authorization"][7:]).status_code == 429
