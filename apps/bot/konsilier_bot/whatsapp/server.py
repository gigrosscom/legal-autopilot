"""The WhatsApp webhook (aiohttp): Meta's verification GET, signed message POSTs, and the API's notification relay.

Routes (behind Caddy at https://<API_DOMAIN>/whatsapp/…):
- GET  /whatsapp/webhook — hub.mode=subscribe + hub.verify_token == WHATSAPP_VERIFY_TOKEN → hub.challenge;
- POST /whatsapp/webhook — X-Hub-Signature-256 = HMAC-SHA256(raw body, WHATSAPP_APP_SECRET); answered 200 at once,
  the messages are handled in the background (a chat answer takes seconds; Meta re-delivers slow webhooks);
- POST /whatsapp/notify  — from the API only (X-Bot-Secret): a notification, sent if the person's window is open;
- GET  /whatsapp/health  — {"enabled": …} for the deploy log.
Off (404 everywhere but health) unless WHATSAPP_TOKEN, WHATSAPP_PHONE_ID, WHATSAPP_APP_SECRET and
WHATSAPP_VERIFY_TOKEN are all set.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass

from aiohttp import web

from ..api import KonsilierApi
from .bot import WhatsAppBot
from .graph import Graph

log = logging.getLogger("konsilier_bot.whatsapp")

VARS = ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN")
MAX_BODY = 3 * 1024 * 1024


@dataclass
class Config:
    token: str = ""
    phone_id: str = ""
    app_secret: str = ""
    verify_token: str = ""
    bot_secret: str = ""

    @property
    def enabled(self) -> bool:
        return all((self.token, self.phone_id, self.app_secret, self.verify_token))

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ
        return cls(e.get("WHATSAPP_TOKEN", "").strip(), e.get("WHATSAPP_PHONE_ID", "").strip(),
                   e.get("WHATSAPP_APP_SECRET", "").strip(), e.get("WHATSAPP_VERIFY_TOKEN", "").strip(),
                   e.get("BOT_API_SECRET", ""))


def signature_ok(body: bytes, header: str | None, app_secret: str) -> bool:
    if not header or not header.startswith("sha256=") or not app_secret:
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):].strip().lower())


def build_app(config: Config, bot: WhatsAppBot | None) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY)
    tasks: set[asyncio.Task] = set()

    def off() -> web.Response:
        return web.Response(status=404, text="not found")

    async def verify(request: web.Request) -> web.Response:
        if not config.enabled:
            return off()
        q = request.query
        if q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""),
                                                                     config.verify_token):
            return web.Response(text=q.get("hub.challenge", ""))
        return web.Response(status=403, text="forbidden")

    async def receive(request: web.Request) -> web.Response:
        if not config.enabled or bot is None:
            return off()
        body = await request.read()
        if not signature_ok(body, request.headers.get("X-Hub-Signature-256"), config.app_secret):
            log.warning("whatsapp: webhook with a bad signature refused")
            return web.Response(status=401, text="bad signature")
        try:
            payload = json.loads(body)
        except ValueError:
            return web.Response(status=400, text="bad json")
        for msg, contact in bot.accept(payload, config.phone_id):
            task = asyncio.create_task(bot.handle(msg, contact))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        return web.Response(text="ok")

    async def notify(request: web.Request) -> web.Response:
        if not config.enabled or bot is None:
            return off()
        secret = request.headers.get("X-Bot-Secret", "")
        if not config.bot_secret or not hmac.compare_digest(secret, config.bot_secret):
            return web.Response(status=403, text="forbidden")
        data = await request.json()
        to, text = str(data.get("to") or ""), str(data.get("text") or "")
        if not to.isdigit() or not text.strip():
            return web.Response(status=400, text="to and text required")
        if not await bot.relay(to, text):
            return web.Response(status=409, text="outside the 24-hour window")
        return web.json_response({"sent": True})

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"enabled": config.enabled})

    app.router.add_get("/whatsapp/webhook", verify)
    app.router.add_post("/whatsapp/webhook", receive)
    app.router.add_post("/whatsapp/notify", notify)
    app.router.add_get("/whatsapp/health", health)
    return app


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    config = Config.from_env()
    bot = None
    api = graph = None
    if config.enabled:
        api = KonsilierApi(os.environ.get("API_URL", "http://localhost:8000"), config.bot_secret,
                           os.environ.get("BOT_DEFAULT_COUNTRY") or None, channel="whatsapp")
        graph = Graph(config.token, config.phone_id)
        bot = WhatsAppBot(api, graph, site_url=os.environ.get("PUBLIC_SITE_URL") or "https://konsilier.com")
    else:
        log.warning("WhatsApp is off: set %s to enable it (team/integrations/whatsapp.md)", ", ".join(VARS))
    runner = web.AppRunner(build_app(config, bot))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("WHATSAPP_PORT", "8080"))).start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
        if api is not None:
            await api.close()
        if graph is not None:
            await graph.close()


if __name__ == "__main__":
    asyncio.run(run())
