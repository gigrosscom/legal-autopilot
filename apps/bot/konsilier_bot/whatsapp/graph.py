"""WhatsApp Cloud API (Meta Graph API) — only the calls the bot needs: send a message, upload and download media.

Docs (opened 01.10.2026): developers.facebook.com/documentation/business-messaging/whatsapp/ — messages
(text up to 4096 characters), interactive reply buttons (up to 3, titles up to 20 characters) and lists (up to 10
rows, titles up to 24), media (a download URL lives 5 minutes and needs the same token).
"""

from __future__ import annotations

from typing import Any

import httpx

GRAPH_URL = "https://graph.facebook.com"
GRAPH_VERSION = "v25.0"

TEXT_MAX = 4096
INTERACTIVE_BODY_MAX = 1024
BUTTON_TITLE_MAX = 20
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESCRIPTION_MAX = 72
CAPTION_MAX = 1024
MAX_MEDIA_BYTES = 15 * 1024 * 1024  # the API's own upload limit for case files


class GraphError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status, self.detail = status, detail
        code = detail.get("error", {}).get("code") if isinstance(detail, dict) else None
        self.code = code
        super().__init__(f"graph {status}: {detail}")


class Graph:
    def __init__(self, token: str, phone_id: str, *, base_url: str = GRAPH_URL, version: str = GRAPH_VERSION,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.phone_id = phone_id
        self.prefix = f"/{version}"
        self.http = httpx.AsyncClient(base_url=base_url, timeout=60, transport=transport,
                                      headers={"Authorization": f"Bearer {token}"})

    async def close(self) -> None:
        await self.http.aclose()

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                detail: Any = r.json()
            except ValueError:
                detail = r.text[:500]
            raise GraphError(r.status_code, detail)

    async def _send(self, to: str, payload: dict[str, Any]) -> str | None:
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **payload}
        r = await self.http.post(f"{self.prefix}/{self.phone_id}/messages", json=body)
        self._check(r)
        ids = r.json().get("messages") or []
        return ids[0].get("id") if ids else None

    async def send_text(self, to: str, text: str) -> str | None:
        # no link previews: the sign-in link must not be opened by a preview fetcher
        return await self._send(to, {"type": "text", "text": {"body": text[:TEXT_MAX], "preview_url": False}})

    async def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> str | None:
        """Up to 3 reply buttons: (title, id)."""
        return await self._send(to, {"type": "interactive", "interactive": {
            "type": "button", "body": {"text": body[:INTERACTIVE_BODY_MAX]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": bid[:256], "title": title[:BUTTON_TITLE_MAX]}}
                                   for title, bid in buttons[:3]]}}})

    async def send_list(self, to: str, body: str, button: str, rows: list[tuple[str, str, str]]) -> str | None:
        """A list of up to 10 rows: (title, id, description)."""
        out_rows = []
        for title, rid, description in rows[:10]:
            row = {"id": rid[:200], "title": title[:LIST_ROW_TITLE_MAX]}
            if description:
                row["description"] = description[:LIST_ROW_DESCRIPTION_MAX]
            out_rows.append(row)
        return await self._send(to, {"type": "interactive", "interactive": {
            "type": "list", "body": {"text": body[:INTERACTIVE_BODY_MAX]},
            "action": {"button": button[:BUTTON_TITLE_MAX], "sections": [{"rows": out_rows}]}}})

    async def upload(self, data: bytes, filename: str, content_type: str) -> str:
        r = await self.http.post(f"{self.prefix}/{self.phone_id}/media",
                                 data={"messaging_product": "whatsapp", "type": content_type},
                                 files={"file": (filename, data, content_type)})
        self._check(r)
        return r.json()["id"]

    async def send_document(self, to: str, data: bytes, filename: str, content_type: str,
                            caption: str = "") -> str | None:
        media_id = await self.upload(data, filename, content_type)
        doc: dict[str, Any] = {"id": media_id, "filename": filename}
        if caption:
            doc["caption"] = caption[:CAPTION_MAX]
        return await self._send(to, {"type": "document", "document": doc})

    async def download(self, media_id: str) -> tuple[bytes, str]:
        """The file a person sent: its URL first (valid 5 minutes), then the bytes with the same token."""
        r = await self.http.get(f"{self.prefix}/{media_id}", params={"phone_number_id": self.phone_id})
        self._check(r)
        meta = r.json()
        if int(meta.get("file_size") or 0) > MAX_MEDIA_BYTES:
            raise GraphError(413, {"error": {"code": "too_large", "message": "file too large"}})
        f = await self.http.get(meta["url"])
        self._check(f)
        if len(f.content) > MAX_MEDIA_BYTES:
            raise GraphError(413, {"error": {"code": "too_large", "message": "file too large"}})
        return f.content, (meta.get("mime_type") or f.headers.get("content-type") or "").split(";")[0].strip()

    async def mark_read(self, message_id: str) -> None:
        r = await self.http.post(f"{self.prefix}/{self.phone_id}/messages",
                                 json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id})
        self._check(r)
