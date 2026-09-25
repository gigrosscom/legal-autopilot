"""Thin async client of the Konsilier API. The bot holds no business logic."""

from __future__ import annotations

from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status, self.detail = status, detail
        super().__init__(f"{status}: {detail}")


class KonsilierApi:
    def __init__(self, base_url: str, bot_secret: str, default_country: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(base_url=base_url, timeout=120, transport=transport)
        self.bot_secret = bot_secret
        self.default_country = default_country
        self._tokens: dict[str, str] = {}

    async def close(self) -> None:
        await self.http.aclose()

    async def _token(self, tg_id: str, language: str) -> str:
        if tg_id not in self._tokens:
            r = await self.http.post("/v1/users/telegram", headers={"X-Bot-Secret": self.bot_secret},
                                     json={"telegram_id": tg_id, "language": language})
            self._check(r)
            self._tokens[tg_id] = r.json()["token"]
        return self._tokens[tg_id]

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, detail)

    async def call(self, tg_id: str, method: str, url: str, *, language: str = "ru", **kw) -> Any:
        token = await self._token(tg_id, language)
        r = await self.http.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kw)
        self._check(r)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.content

    # ---- convenience ------------------------------------------------
    async def active_case(self, tg_id: str) -> dict | None:
        cases = await self.call(tg_id, "GET", "/v1/cases")
        return next((c for c in cases if c["status"] != "resolved"), None)

    async def create_case(self, tg_id: str, text: str, language: str = "ru") -> dict:
        body: dict[str, Any] = {"text": text, "language": language}
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
