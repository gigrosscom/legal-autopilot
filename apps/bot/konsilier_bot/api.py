"""Thin async client of the Konsilier API. The bot holds no business logic."""

from __future__ import annotations

import json
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status, self.detail = status, detail
        super().__init__(f"{status}: {detail}")


class KonsilierApi:
    """``channel``: whose people the bot speaks for — "telegram" (chat id) or "whatsapp" (the sender's number)."""

    def __init__(self, base_url: str, bot_secret: str, default_country: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, channel: str = "telegram"):
        self.http = httpx.AsyncClient(base_url=base_url, timeout=120, transport=transport)
        self.bot_secret = bot_secret
        self.default_country = default_country
        self.channel = channel
        self._tokens: dict[str, str] = {}

    async def close(self) -> None:
        await self.http.aclose()

    async def _token(self, tg_id: str, language: str) -> str:
        if tg_id not in self._tokens:
            if self.channel == "whatsapp":
                path, body = "/v1/users/whatsapp", {"wa_id": tg_id, "language": language}
            else:
                path, body = "/v1/users/telegram", {"telegram_id": tg_id, "language": language}
            r = await self.http.post(path, headers={"X-Bot-Secret": self.bot_secret}, json=body)
            self._check(r)
            self._tokens[tg_id] = r.json()["token"]
        return self._tokens[tg_id]

    async def _headers(self, tg_id: str, language: str = "ru") -> dict[str, str]:
        # the bot secret too: the API then knows the request is the bot's (one address for many people)
        return {"Authorization": f"Bearer {await self._token(tg_id, language)}", "X-Bot-Secret": self.bot_secret}

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, detail)

    async def call(self, tg_id: str, method: str, url: str, *, language: str = "ru", **kw) -> Any:
        r = await self.http.request(method, url, headers=await self._headers(tg_id, language), **kw)
        self._check(r)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.content

    async def chat(self, tg_id: str, case_id: str, text: str, language: str | None = None,
                   attachments: list[str] | None = None) -> dict:
        """The free chat's answer (the site's chat, POST …/chat, a stream of server-sent events) read to the end:
        the final ``done`` event (``message`` with its text and ``offer_document``)."""
        body: dict[str, Any] = {"text": text[:4000], "attachments": attachments or []}
        if language:
            body["language"] = language
        async with self.http.stream("POST", f"/v1/cases/{case_id}/chat", json=body,
                                    headers=await self._headers(tg_id)) as r:
            if r.status_code >= 400:
                await r.aread()
                self._check(r)
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "done":
                    return ev
                if ev.get("type") == "error":
                    raise ApiError(503, {"code": ev.get("code") or "busy", "message": ev.get("message")})
        raise ApiError(502, {"code": "agent_failed", "message": "the chat stream ended without an answer"})

    async def transcribe(self, tg_id: str, data: bytes, content_type: str, language: str = "ru") -> str:
        out = await self.call(tg_id, "POST", "/v1/transcribe", data={"lang": language},
                              files={"file": ("voice.ogg", data, content_type)})
        return (out.get("text") or "").strip()

    async def login_code(self, tg_id: str) -> str:
        """A one-time code for a link that opens the person's account on the site (…?login=<code>)."""
        return (await self.call(tg_id, "POST", "/v1/auth/link"))["code"]

    # ---- convenience ------------------------------------------------
    async def active_case(self, tg_id: str) -> dict | None:
        cases = await self.call(tg_id, "GET", "/v1/cases")
        return next((c for c in cases if c["status"] != "resolved"), None)

    async def create_case(self, tg_id: str, text: str, language: str = "ru", defer: bool = False) -> dict:
        # the welcome message says that sending a description accepts the Terms of Use (current version);
        # defer: the chat answers at once and the scenario is worked out meanwhile (as on the site)
        body: dict[str, Any] = {"text": text, "language": language, "accept_terms": True}
        if defer:
            body["defer"] = True
        if self.default_country:
            body["country"] = self.default_country
        return await self.call(tg_id, "POST", "/v1/cases", json=body)

    async def message(self, tg_id: str, case_id: str, text: str) -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/messages", json={"text": text})

    async def upload_evidence(self, tg_id: str, case_id: str, kind: str, filename: str, data: bytes,
                              content_type: str) -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/evidence", data={"kind": kind},
                               files={"file": (filename, data, content_type)})

    async def confirm_evidence(self, tg_id: str, case_id: str, evidence_id: str) -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/evidence/{evidence_id}/confirm", json={})

    async def prepare_next(self, tg_id: str, case_id: str) -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/actions/next")

    async def document(self, tg_id: str, case_id: str, action_id: str, fmt: str) -> bytes:
        return await self.call(tg_id, "GET", f"/v1/cases/{case_id}/actions/{action_id}/document",
                               params={"format": fmt})

    async def submitted(self, tg_id: str, case_id: str, action_id: str, via: str = "user_submits") -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/actions/{action_id}/submitted", json={"via": via})

    async def response(self, tg_id: str, case_id: str, action_id: str, **body: Any) -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/actions/{action_id}/response", json=body)

    async def response_file(self, tg_id: str, case_id: str, action_id: str, filename: str, data: bytes,
                            content_type: str) -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/actions/{action_id}/response/file",
                               files={"file": (filename, data, content_type)})

    async def close_case(self, tg_id: str, case_id: str, result: str, amount: str | None) -> dict:
        return await self.call(tg_id, "POST", f"/v1/cases/{case_id}/close",
                               json={"result": result, "amount_recovered": amount})
