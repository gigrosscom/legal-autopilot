"""WhatsApp bot: formatting, the webhook's checks, and a whole conversation against the real API (in-process) with a
fake Graph API (no network)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import httpx
import pytest
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "bot"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from konsilier_bot.api import KonsilierApi  # noqa: E402
from konsilier_bot.whatsapp.bot import WINDOW_S, WhatsAppBot  # noqa: E402
from konsilier_bot.whatsapp.graph import Graph  # noqa: E402
from konsilier_bot.whatsapp.server import Config, build_app, signature_ok  # noqa: E402
from konsilier_bot.whatsapp.text import split, to_whatsapp  # noqa: E402

PHONE_ID = "1065403522"
WA = "77010001122"
SECRET = "app-secret"
FRAUD = "Займ в МФО оформили мошенники 01.09.2026 на 50000, я не брал"


# ------------------------------------------------------------------ text
def test_markdown_becomes_whatsapp_formatting():
    md = ("## Что делать\n**Коротко:** вам *должны* вернуть деньги.\n[[MORE]]\n- шаг один\n* шаг два\n"
          "~~старое~~ см. [закон](https://adilet.zan.kz/rus/docs/K1500000414)\n\n\n\nКонец")
    out = to_whatsapp(md)
    assert out.startswith("*Что делать*\n*Коротко:* вам _должны_ вернуть деньги.")
    assert "[[MORE]]" not in out and "• шаг один\n• шаг два" in out
    assert "~старое~" in out and "закон (https://adilet.zan.kz/rus/docs/K1500000414)" in out
    assert "\n\n\n" not in out and out.endswith("Конец")


def test_split_cuts_only_when_needed_and_at_paragraphs():
    assert split("коротко") == ["коротко"]
    text = "\n\n".join(["абзац " + "слово " * 150] * 8)  # ~7 200 characters
    parts = split(text)
    assert len(parts) == 2 and all(len(p) <= 4096 for p in parts)
    assert all(p.startswith("абзац") for p in parts)
    assert "".join(p.replace("\n", "").replace(" ", "") for p in parts) == text.replace("\n", "").replace(" ", "")


def test_signature_check():
    body = b'{"entry":[]}'
    good = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert signature_ok(body, good, SECRET)
    assert not signature_ok(body + b" ", good, SECRET)
    assert not signature_ok(body, good, "other")
    assert not signature_ok(body, None, SECRET) and not signature_ok(body, good[7:], SECRET)


# ------------------------------------------------------------------ fakes
class FakeGraph:
    """Meta's Graph API as an httpx transport: records what the bot sends, serves media the person sent."""

    def __init__(self):
        self.sent: list[dict] = []
        self.uploads: list[str] = []
        self.read: list[str] = []
        self.media = {"voice1": (b"OggS-voice", "audio/ogg; codecs=opus"), "img1": (PNG, "image/png")}

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer wa-token"
        path = request.url.path
        if path == f"/v25.0/{PHONE_ID}/messages":
            body = json.loads(request.content)
            if body.get("status") == "read":
                self.read.append(body["message_id"])
                return httpx.Response(200, json={"success": True})
            self.sent.append(body)
            return httpx.Response(200, json={"messages": [{"id": f"wamid.out{len(self.sent)}"}]})
        if path == f"/v25.0/{PHONE_ID}/media":
            self.uploads.append(request.headers["content-type"])
            return httpx.Response(200, json={"id": f"media{len(self.uploads)}"})
        if path.startswith("/v25.0/") and path.split("/")[-1] in self.media:
            mid = path.split("/")[-1]
            return httpx.Response(200, json={"url": f"https://lookaside.example/{mid}", "id": mid,
                                             "mime_type": self.media[mid][1], "file_size": len(self.media[mid][0])})
        if request.url.host == "lookaside.example":
            data, ctype = self.media[path.strip("/")]
            return httpx.Response(200, content=data, headers={"content-type": ctype})
        return httpx.Response(404, json={"error": {"message": "unknown", "code": 100}})

    def texts(self) -> list[str]:
        out = []
        for m in self.sent:
            if m["type"] == "text":
                out.append(m["text"]["body"])
            elif m["type"] == "interactive":
                out.append(m["interactive"]["body"]["text"])
        return out

    def buttons(self, i: int = -1) -> list[tuple[str, str]]:
        it = self.sent[i]["interactive"]
        if it["type"] == "button":
            return [(b["reply"]["title"], b["reply"]["id"]) for b in it["action"]["buttons"]]
        return [(r["title"], r["id"]) for r in it["action"]["sections"][0]["rows"]]


PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4520000000049454e44ae426082")


class ChatStub:
    """The chat agent: a fixed answer offering the document, with a Markdown heading and the «Подробнее» cut."""

    portal_domain = "adilet.zan.kz"
    client = None

    def stream(self, turns, **kw):
        text = "## Коротко\nЗаём на вас **оформили мошенники** — его можно оспорить.\n[[MORE]]\n- заявление в МФО"
        yield {"type": "text", "text": text}
        yield {"type": "done", "result": NS(text=text, offer_document=True, norms=[], sources=[], unchecked=False,
                                            tool_calls=[], usage={}, timing={})}


class TranscriberStub:
    def transcribe(self, audio, mime, lang):
        assert audio == b"OggS-voice" and mime == "audio/ogg"
        return "Ещё у меня есть скриншот кредитной истории"


@pytest.fixture
def api_app(tmp_path):
    from konsilier.config import Settings
    from konsilier.container import build_container
    from konsilier.core.documents import NullPdfConverter
    from konsilier.core.llm.mock import HeuristicMockProvider
    from konsilier.core.models import Base
    from konsilier.main import create_app

    settings = Settings(database_url=f"sqlite:///{tmp_path}/wa.db", packs_dir=ROOT / "packs",
                        storage_local_dir=tmp_path / "files", bot_api_secret="s", approval_required_first_n=0,
                        soffice_bin="", payment_mode="stub", background_jobs="inline")
    container = build_container(settings, llm=HeuristicMockProvider(), pdf=NullPdfConverter())
    container.chat_agent = ChatStub()
    container.transcriber = TranscriberStub()
    Base.metadata.create_all(container.engine_db)
    return create_app(settings, container, start_scheduler=False)


def make_bot(api_app, fake: FakeGraph) -> WhatsAppBot:
    api = KonsilierApi("http://api", "s", transport=httpx.ASGITransport(app=api_app), channel="whatsapp")
    graph = Graph("wa-token", PHONE_ID, transport=httpx.MockTransport(fake.handler))
    return WhatsAppBot(api, graph, site_url="https://konsilier.com")


_n = 0


def inbound(kind: str, body: dict, *, wa: str = WA, ts: float | None = None) -> dict:
    global _n
    _n += 1
    return {"from": wa, "id": f"wamid.in{_n}", "timestamp": str(int(ts or time.time())), "type": kind, kind: body}


def delivery(*messages: dict, phone_id: str = PHONE_ID) -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"display_phone_number": "77000000000",
                                                      "phone_number_id": phone_id},
        "contacts": [{"profile": {"name": "Айгерим"}, "wa_id": WA}], "messages": list(messages)}}]}]}


async def feed(bot: WhatsAppBot, *messages: dict) -> None:
    for msg, contact in bot.accept(delivery(*messages), PHONE_ID):
        await bot.handle(msg, contact)


def press(bid: str) -> dict:
    return inbound("interactive", {"type": "button_reply", "button_reply": {"id": bid, "title": "x"}})


# ------------------------------------------------------------------ the whole conversation
def test_conversation_terms_chat_document_voice_photo_and_site_link(api_app):
    async def scenario():
        fake = FakeGraph()
        bot = make_bot(api_app, fake)
        # 1. the first message: the terms are shown before the description is taken
        await feed(bot, inbound("text", {"body": FRAUD}))
        assert "konsilier.com/terms" in fake.texts()[-1]
        assert fake.buttons() == [("Продолжить", "go")]
        assert fake.read == ["wamid.in" + str(_n)]
        # 2. «Продолжить»: the case opens and the chat answers, formatted for WhatsApp; the document is not offered
        # in the very first answer (owner 30.09), the next one offers «Составить документ»
        await feed(bot, press("go"))
        answer = fake.texts()[-1]
        assert answer.startswith("*Коротко*\nЗаём на вас *оформили мошенники*") and "• заявление в МФО" in answer
        assert "[[MORE]]" not in answer and "##" not in answer and fake.sent[-1]["type"] == "text"
        await feed(bot, inbound("text", {"body": "Что мне теперь делать?"}))
        (title, bid), = fake.buttons()
        assert title == "Составить документ" and bid.startswith("doc:")
        cid = bid.split(":")[1]
        # 3. «Составить документ»: the case's questions, answered in the chat (at most four)
        await feed(bot, press(bid))
        answers = {"lender_name": "МФО Ромашка", "applicant_name": "Иванов Иван", "applicant_iin": "900101300123",
                   "applicant_phone": "+77010000000", "applicant_address": "Алматы, ул. Абая 1",
                   "loan_date": "2026-09-01", "amount": "50000"}
        for _ in range(6):
            case = await bot.api.call(WA, "GET", f"/v1/cases/{cid}")
            if case["status"] != "intake":
                break
            assert WA in bot.interview
            await feed(bot, inbound("text", {"body": answers.get(case["question"]["field"], "пропустить")}))
        case = await bot.api.call(WA, "GET", f"/v1/cases/{cid}")
        assert case["status"] == "qualified"
        last = fake.texts()[-1]
        assert f"https://konsilier.com/case/{cid}?login=" in last and "1 час" in last
        assert any(b == ("Подготовить документ", f"prep:{cid}") for b in fake.buttons())
        # 4. the personal link opens the same account on the site, once
        code = last.split("?login=")[1].split()[0]
        r = await bot.api.http.post("/v1/auth/link/redeem", json={"code": code})
        token = r.json()["token"]
        mine = await bot.api.http.get(f"/v1/cases/{cid}", headers={"Authorization": f"Bearer {token}"})
        assert mine.status_code == 200
        again = await bot.api.http.post("/v1/auth/link/redeem", json={"code": code})
        assert again.status_code == 410
        # 5. «Подготовить документ» (payment stub): the document arrives as a file, uploaded to WhatsApp
        await feed(bot, press(f"prep:{cid}"))
        docs = [m for m in fake.sent if m["type"] == "document"]
        assert docs and docs[-1]["document"]["filename"].endswith(".docx") and fake.uploads
        # 6. a voice note: transcribed by the API, answered by the chat, the words echoed back
        await feed(bot, inbound("audio", {"id": "voice1", "mime_type": "audio/ogg; codecs=opus", "voice": True}))
        assert fake.texts()[-1].startswith("Вы сказали: «Ещё у меня есть скриншот кредитной истории»")
        # 7. a photo: downloaded from Meta, saved as the case's evidence
        await feed(bot, inbound("image", {"id": "img1", "mime_type": "image/png"}))
        case = await bot.api.call(WA, "GET", f"/v1/cases/{cid}")
        assert len(case["evidence"]) == 1
        await bot.api.close()
        await bot.graph.close()

    asyncio.run(scenario())


def test_payment_screen_as_in_telegram(api_app, monkeypatch):
    async def scenario():
        fake = FakeGraph()
        bot = make_bot(api_app, fake)
        bot.welcomed.add(WA)
        case = {"id": "c1", "language": "ru", "status": "qualified", "actions": [], "proposal": None,
                "payment": {"amount": 1990, "currency": "KZT", "status": "pending", "code": "KA-7F3K2Q",
                            "recipient_name": "Получатель", "kaspi_phone": "+7 700 000 00 00"}}

        async def code(_wa):
            return "CODE123"
        monkeypatch.setattr(bot.api, "login_code", code)
        bot.last_inbound[WA] = time.time()
        await bot.show(WA, case)
        body = fake.texts()[-1]
        assert "1 990 KZT" in body and "KA-7F3K2Q" in body and "login=CODE123" in body
        assert ("Оплатить", "paid:c1") in fake.buttons() and ("Подготовить документ", "prep:c1") in fake.buttons()
        await bot.api.close()
        await bot.graph.close()

    asyncio.run(scenario())


def test_window_duplicates_statuses_and_other_numbers(api_app):
    async def scenario():
        fake = FakeGraph()
        bot = make_bot(api_app, fake)
        old = inbound("text", {"body": FRAUD}, ts=time.time() - WINDOW_S + 60)  # re-delivered after the window
        await feed(bot, old)
        assert fake.sent == [] and fake.read == []
        msg = inbound("text", {"body": "Здравствуйте"})
        payload = delivery(msg)
        payload["entry"][0]["changes"][0]["value"]["statuses"] = [{"id": "wamid.out1", "status": "delivered"}]
        first = bot.accept(payload, PHONE_ID)
        assert len(first) == 1 and bot.accept(payload, PHONE_ID) == []  # the same message id again: skipped
        statuses_only = {"entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": PHONE_ID}, "statuses": [{"id": "x", "status": "read"}]}}]}]}
        assert bot.accept(statuses_only, PHONE_ID) == []
        assert bot.accept(delivery(inbound("text", {"body": "hi"}), phone_id="999"), PHONE_ID) == []
        for m, c in first:
            await bot.handle(m, c)
        assert "Опишите одним сообщением" in fake.texts()[-1]  # a greeting: the welcome asks for the story
        # the window: open after the person wrote, closed 24 hours later — then nothing is sent
        assert await bot.relay(WA, "Документ готов") is True
        bot.clock = lambda: time.time() + WINDOW_S
        n = len(fake.sent)
        assert await bot.relay(WA, "Документ готов") is False and len(fake.sent) == n
        await bot.api.close()
        await bot.graph.close()

    asyncio.run(scenario())


def test_kazakh_is_answered_in_kazakh(api_app):
    async def scenario():
        fake = FakeGraph()
        bot = make_bot(api_app, fake)
        await feed(bot, inbound("text", {"body": "Сәлеметсіз бе"}))
        assert "пайдаланушы келісімін" in fake.texts()[-1]
        await feed(bot, inbound("sticker", {"id": "s1"}))
        assert "мәтінді" in fake.texts()[-1]
        await bot.api.close()
        await bot.graph.close()

    asyncio.run(scenario())


# ------------------------------------------------------------------ the HTTP endpoints
def _client(config: Config, bot) -> TestClient:
    return TestClient(TestServer(build_app(config, bot)))


CONFIG = Config("wa-token", PHONE_ID, SECRET, "verify-me", "s")


def test_webhook_off_without_variables():
    async def scenario():
        async with _client(Config(), None) as c:
            assert (await c.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "",
                                                             "hub.challenge": "1"})).status == 404
            assert (await c.post("/whatsapp/webhook", data=b"{}")).status == 404
            assert (await c.post("/whatsapp/notify", json={"to": WA, "text": "x"})).status == 404
            assert await (await c.get("/whatsapp/health")).json() == {"enabled": False}

    asyncio.run(scenario())


def test_webhook_verification_and_signature(api_app):
    async def scenario():
        fake = FakeGraph()
        bot = make_bot(api_app, fake)
        async with _client(CONFIG, bot) as c:
            ok = await c.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                          "hub.challenge": "1158201444"})
            assert ok.status == 200 and await ok.text() == "1158201444"
            bad = await c.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                           "hub.challenge": "1"})
            assert bad.status == 403
            body = json.dumps(delivery(inbound("text", {"body": "Здравствуйте"}))).encode()
            unsigned = await c.post("/whatsapp/webhook", data=body)
            assert unsigned.status == 401
            forged = await c.post("/whatsapp/webhook", data=body,
                                  headers={"X-Hub-Signature-256": "sha256=" + "0" * 64})
            assert forged.status == 401 and fake.sent == []
            sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
            r = await c.post("/whatsapp/webhook", data=body, headers={"X-Hub-Signature-256": sig})
            assert r.status == 200
            for _ in range(100):  # handled in the background
                if fake.sent:
                    break
                await asyncio.sleep(0.05)
            assert "konsilier.com/terms" in fake.texts()[-1]
            # the API's relay: the bot secret is required; the window is open now
            assert (await c.post("/whatsapp/notify", json={"to": WA, "text": "x"})).status == 403
            r = await c.post("/whatsapp/notify", json={"to": WA, "text": "Документ готов"},
                             headers={"X-Bot-Secret": "s"})
            assert r.status == 200 and fake.texts()[-1] == "Документ готов"
            r = await c.post("/whatsapp/notify", json={"to": "77000000001", "text": "x"},
                             headers={"X-Bot-Secret": "s"})
            assert r.status == 409
        await bot.api.close()
        await bot.graph.close()

    asyncio.run(scenario())
