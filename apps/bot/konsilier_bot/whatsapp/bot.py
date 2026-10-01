"""The WhatsApp bot: the same API (engine) as the Telegram bot and the site's chat.

Answers only people who wrote first, and only within WhatsApp's 24-hour customer service window (no templates, no
messages first — owner 01.10). The first message opens a case and gets the chat's answer (as on the site);
«Составить документ» leads through the Telegram bot's case flow — up to four questions, payment by Kaspi transfer
with «Оплатить», the document as a file — and a personal link opens the same case on the site.
Voice notes are transcribed by the API (free Gemini); photos and PDFs become evidence of the case.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any

from ..api import ApiError, KonsilierApi
from ..errors import error_text
from ..i18n import t
from ..ui import Screen, case_screen, last_action
from .graph import BUTTON_TITLE_MAX, INTERACTIVE_BODY_MAX, LIST_ROW_TITLE_MAX, Graph, GraphError
from .text import split, to_whatsapp

log = logging.getLogger("konsilier_bot.whatsapp")

WINDOW_S = 24 * 3600
WINDOW_MARGIN_S = 120  # never answer in the window's last minutes: the reply could arrive after it closed
SEEN_MAX = 20000  # message ids remembered against Meta's re-deliveries (it retries for up to 7 days)

KK_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
# words instead of slash commands (ru, kk); a slash form works too
WORDS = {
    "help": {"помощь", "справка", "help", "/help", "көмек", "/start", "start", "старт"},
    "new": {"новое дело", "новое", "/new", "жаңа іс"},
    "status": {"статус", "/status", "күйі", "күй"},
    "document": {"документ", "составить документ", "құжат", "құжат құрастыру"},
    "site": {"сайт", "ссылка", "/site", "сілтеме"},
}
FILE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
SUBSTANTIVE = 20  # a first message this long is a description of the situation, not a greeting


def detect_lang(text: str) -> str | None:
    return "kk" if any(c in KK_LETTERS for c in text or "") else None


class WhatsAppBot:
    def __init__(self, api: KonsilierApi, graph: Graph, *, site_url: str = "https://konsilier.com",
                 clock=time.time):
        self.api, self.graph = api, graph
        self.site_url = site_url.rstrip("/")
        self.clock = clock
        self.last_inbound: dict[str, float] = {}  # wa_id → when the person last wrote (opens the 24-hour window)
        self.lang: dict[str, str] = {}
        self.seen: OrderedDict[str, None] = OrderedDict()
        self.locks: dict[str, asyncio.Lock] = {}
        self.new_case: set[str] = set()  # asked for a new case: the next text opens one
        self.awaiting_reply: set[str] = set()  # pressed «Пришёл ответ»: the next text is the other side's reply
        self.interview: set[str] = set()  # pressed «Составить документ»: texts answer the case's questions
        self.welcomed: set[str] = set()
        self.pending: dict[str, str] = {}  # a first description held until the person accepts the terms

    # ------------------------------------------------------------------ webhook entry
    def accept(self, payload: dict[str, Any], phone_id: str) -> list[tuple[dict, dict]]:
        """The new inbound messages of a webhook delivery, oldest first, each once. Status updates (sent, delivered,
        read, failed), other numbers and other fields are skipped."""
        out: list[tuple[dict, dict]] = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                if change.get("field") != "messages" or value.get("messaging_product", "whatsapp") != "whatsapp":
                    continue
                if str((value.get("metadata") or {}).get("phone_number_id") or phone_id) != str(phone_id):
                    continue
                names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
                for msg in value.get("messages") or []:
                    mid, wa = msg.get("id"), msg.get("from")
                    if not mid or not wa or mid in self.seen:
                        continue
                    self.seen[mid] = None
                    while len(self.seen) > SEEN_MAX:
                        self.seen.popitem(last=False)
                    out.append((msg, {"name": names.get(wa)}))
        out.sort(key=lambda m: int(m[0].get("timestamp") or 0))
        return out

    def in_window(self, wa: str) -> bool:
        last = self.last_inbound.get(wa)
        return last is not None and self.clock() - last < WINDOW_S - WINDOW_MARGIN_S

    async def handle(self, msg: dict[str, Any], contact: dict[str, Any] | None = None) -> None:
        wa = msg["from"]
        sent_at = float(msg.get("timestamp") or self.clock())
        if self.clock() - sent_at >= WINDOW_S - WINDOW_MARGIN_S:
            log.info("whatsapp: a late delivery of %s, the window has closed — not answered", msg.get("id"))
            return
        self.last_inbound[wa] = max(self.last_inbound.get(wa, 0.0), sent_at)
        lock = self.locks.setdefault(wa, asyncio.Lock())
        async with lock:  # one person's messages one after another, in order
            try:
                try:
                    await self.graph.mark_read(msg["id"])
                except Exception:  # noqa: BLE001 — blue ticks are cosmetic
                    pass
                await self._dispatch(wa, msg)
            except Exception as e:  # noqa: BLE001 — the person always hears something
                log.exception("whatsapp: message %s failed", msg.get("id"))
                try:
                    await self._say(wa, error_text(e, self._lang(wa), prefix="whatsapp."))
                except Exception:  # noqa: BLE001 — Meta itself refuses (token, number, window): only the log is left
                    log.exception("whatsapp: could not tell %s about the failure", wa[-4:])

    # ------------------------------------------------------------------ sending (only inside the window)
    def _lang(self, wa: str) -> str:
        return self.lang.get(wa, "ru")

    async def _say(self, wa: str, text: str, buttons: list[tuple[str, str]] | None = None) -> None:
        if not self.in_window(wa):
            log.info("whatsapp: not sending to %s — outside the 24-hour window", wa[-4:])
            return
        text = text.strip()
        flat = [b for b in (buttons or []) if b[0] and b[1]]
        if not flat:
            for part in split(text):
                await self.graph.send_text(wa, part)
            return
        parts = split(text, INTERACTIVE_BODY_MAX) or ["…"]
        if len(parts) > 1:  # a long text goes as text; the buttons follow under its last lines
            for part in split("\n\n".join(parts[:-1])):
                await self.graph.send_text(wa, part)
        body = parts[-1]
        if len(flat) <= 3 and all(len(title) <= BUTTON_TITLE_MAX for title, _ in flat):
            await self.graph.send_buttons(wa, body, flat)
        else:
            rows = [(title if len(title) <= LIST_ROW_TITLE_MAX else title[:LIST_ROW_TITLE_MAX - 1] + "…", bid,
                     title if len(title) > LIST_ROW_TITLE_MAX else "") for title, bid in flat]
            await self.graph.send_list(wa, body, t("whatsapp.choose", self._lang(wa)), rows)

    async def relay(self, wa: str, text: str) -> bool:
        """A notification from the API (payment confirmed, document ready, a deadline): sent only inside the window."""
        if not self.in_window(wa):
            return False
        await self._say(wa, to_whatsapp(text))
        return True

    async def site_link(self, wa: str, case_id: str) -> str:
        code = await self.api.login_code(wa)
        return t("whatsapp.site", self._lang(wa), url=f"{self.site_url}/case/{case_id}?login={code}")

    async def show(self, wa: str, case: dict[str, Any], message: str | None = None, link: bool = False) -> None:
        """A case screen of the Telegram bot (ui.case_screen) with its buttons; the document as a file."""
        lang = case.get("language") or self._lang(wa)
        screen: Screen = case_screen(case, to_whatsapp(message) if message else None)
        if screen.document_action:
            a = screen.document_action
            fmt = "pdf" if a["has_pdf"] else "docx"
            data = await self.api.document(wa, case["id"], a["id"], fmt)
            ctype = "application/pdf" if fmt == "pdf" else \
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if self.in_window(wa):
                await self.graph.send_document(wa, data, f"{a['action_id']}.{fmt}", ctype,
                                               t("document_caption", lang, title=a["title"], ai_label=case["ai_label"]))
            draft = (case.get("scenario") or {}).get("draft_disclaimer")
            if draft:
                screen.text = f"{t('draft', lang, text=draft)}\n\n{screen.text}"
        text = screen.text
        if link or case.get("status") in ("qualified", "action_ready"):
            text = f"{text}\n\n{await self.site_link(wa, case['id'])}"
        await self._say(wa, text, [b for row in screen.buttons for b in row])

    # ------------------------------------------------------------------ inbound
    async def _dispatch(self, wa: str, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "text":
            text = (msg.get("text") or {}).get("body") or ""
            self.lang[wa] = detect_lang(text) or self.lang.get(wa, "ru")
            await self.on_text(wa, text)
        elif kind == "interactive":
            reply = (msg.get("interactive") or {})
            chosen = reply.get("button_reply") or reply.get("list_reply") or {}
            await self.on_button(wa, chosen.get("id") or "")
        elif kind == "button":  # a quick reply of a template (not used by us): its text, as typed
            await self.on_text(wa, (msg.get("button") or {}).get("text") or "")
        elif kind in ("audio", "voice"):
            await self.on_voice(wa, (msg.get(kind) or {}).get("id"))
        elif kind in ("image", "document"):
            media = msg.get(kind) or {}
            await self.on_file(wa, media.get("id"), media.get("filename") or ("photo.jpg" if kind == "image" else
                                                                             "file.pdf"), media.get("mime_type"))
        elif kind in ("reaction", "system", "ephemeral", "request_welcome"):
            return  # nothing to answer
        else:  # sticker, location, contacts, video, unsupported
            await self._say(wa, t("whatsapp.unsupported", self._lang(wa)))

    async def on_voice(self, wa: str, media_id: str | None) -> None:
        lang = self._lang(wa)
        try:
            data, ctype = await self.graph.download(media_id or "")
            text = await self.api.transcribe(wa, data, ctype or "audio/ogg", lang)
        except (GraphError, ApiError) as e:
            log.warning("whatsapp: voice note not transcribed: %s", e)
            text = ""
        if not text:
            await self._say(wa, t("whatsapp.voice_failed", lang))
            return
        self.lang[wa] = detect_lang(text) or lang
        await self.on_text(wa, text, heard=text)

    async def on_text(self, wa: str, text: str, heard: str | None = None) -> None:
        text = text.strip()
        if not text:
            return
        lang = self._lang(wa)
        word = text.lower().strip(" .!?«»\"")
        if word in WORDS["help"]:
            await self._say(wa, t("whatsapp.help", lang))
            return
        if word in WORDS["new"]:
            self.new_case.add(wa)
            self.interview.discard(wa)
            self.awaiting_reply.discard(wa)
            await self._say(wa, t("new_case", lang))
            return
        case = None if wa in self.new_case else await self.api.active_case(wa)
        if word in WORDS["status"]:
            await (self.show(wa, case) if case else self._say(wa, t("no_case", lang)))
            return
        if word in WORDS["site"] and case:
            await self._say(wa, await self.site_link(wa, case["id"]))
            return
        if word in WORDS["document"] and case:
            await self.on_button(wa, f"doc:{case['id']}")
            return
        if case is None:
            await self.open_case(wa, text, heard)
            return
        if wa in self.awaiting_reply and case["status"] == "awaiting_response":
            self.awaiting_reply.discard(wa)
            out = await self.api.response(wa, case["id"], last_action(case)["id"], text=text)
            await self.show(wa, out["case"])
            return
        if wa in self.interview and case["status"] == "intake" and case.get("question"):
            out = await self.api.message(wa, case["id"], text)
            if out["case"]["status"] != "intake" or not out["case"].get("question"):
                self.interview.discard(wa)
            await self.show(wa, out["case"], out["reply"]["message"])
            return
        await self.answer(wa, case, text, heard)

    async def open_case(self, wa: str, text: str, heard: str | None) -> None:
        lang = self._lang(wa)
        first = wa not in self.welcomed and wa not in self.new_case and not await self.api.call(wa, "GET", "/v1/cases")
        if first:
            # the Terms of Use are shown before a description is taken: a description goes on with «Продолжить»
            self.welcomed.add(wa)
            if len(text) >= SUBSTANTIVE:
                self.pending[wa] = text
                await self._say(wa, f"{t('whatsapp.welcome', lang)}\n{t('whatsapp.welcome_go', lang)}",
                                [(t("whatsapp.buttons.go", lang), "go")])
            else:
                await self._say(wa, f"{t('whatsapp.welcome', lang)}\n{t('whatsapp.welcome_ask', lang)}")
            return
        if len(text) < 3:
            await self._say(wa, t("whatsapp.welcome_ask", lang))
            return
        self.new_case.discard(wa)
        self.interview.discard(wa)
        self.awaiting_reply.discard(wa)
        out = await self.api.create_case(wa, text, lang, defer=True)
        emergency = out["reply"].get("emergency")
        if emergency:  # danger first: numbers before anything else
            await self._say(wa, "\n".join([emergency["message"],
                                           *(f"{n['label']}: {n['number']}" for n in emergency["numbers"])]))
        await self.answer(wa, out["case"], text, heard)

    async def answer(self, wa: str, case: dict[str, Any], text: str, heard: str | None = None) -> None:
        """The site chat's answer; «Составить документ» under it when the answer offers the document."""
        lang = self._lang(wa)
        done = await self.api.chat(wa, case["id"], text, language=lang)
        message = done.get("message") or {}
        body = to_whatsapp(message.get("text") or "")
        if heard:
            body = f"{t('whatsapp.heard', lang)} «{heard}»\n\n{body}"
        buttons = [(t("whatsapp.buttons.document", lang), f"doc:{case['id']}")] if message.get("offer_document") \
            else None
        await self._say(wa, body, buttons)

    async def on_file(self, wa: str, media_id: str | None, filename: str, mime: str | None) -> None:
        lang = self._lang(wa)
        case = await self.api.active_case(wa)
        if case is None:
            await self._say(wa, t("no_case", lang))
            return
        ctype = (mime or "").split(";")[0].strip().lower()
        if ctype not in FILE_TYPES:
            await self._say(wa, t("whatsapp.file_failed", lang))
            return
        try:
            data, got = await self.graph.download(media_id or "")
        except GraphError as e:
            log.warning("whatsapp: file not downloaded: %s", e)
            await self._say(wa, t("whatsapp.file_failed", lang))
            return
        ctype = got if got in FILE_TYPES else ctype
        if case["status"] == "awaiting_response":
            self.awaiting_reply.discard(wa)
            out = await self.api.response_file(wa, case["id"], last_action(case)["id"], filename, data, ctype)
            await self.show(wa, out["case"])
            return
        q = case.get("question") or {}
        kinds = q.get("evidence_kinds") or []
        out = await self.api.upload_evidence(wa, case["id"], kinds[0]["kind"] if kinds else "other", filename, data,
                                             ctype)
        ev = out["evidence"]
        lang = case.get("language") or lang
        if ev["extracted_facts"]:
            labels = {f["field"]: f["label"] for f in out["case"]["facts"]}
            facts = "\n".join(f"• {labels.get(k, k)}: {v}" for k, v in ev["extracted_facts"].items())
            await self._say(wa, t("evidence_found", lang, facts=facts),
                            [(t("buttons.confirm_facts", lang), f"ev:{case['id']}:{ev['id'][:8]}")])
        else:
            await self._say(wa, t("evidence_nothing", lang))

    async def on_button(self, wa: str, data: str) -> None:
        """The Telegram bot's buttons (ui.case_screen) plus «Составить документ» (doc) and «Продолжить» (go)."""
        lang = self._lang(wa)
        if data == "go":
            text = self.pending.pop(wa, None)
            if text:
                await self.open_case(wa, text, None)
            else:
                await self._say(wa, t("whatsapp.welcome_ask", lang))
            return
        parts = data.split(":")
        cmd, cid = parts[0], parts[1] if len(parts) > 1 else ""
        if not cid:
            return
        case = await self.api.call(wa, "GET", f"/v1/cases/{cid}")
        lang = case.get("language") or lang
        action = last_action(case)
        out: dict | None = None
        if cmd == "doc":
            if case["status"] == "intake":
                if case.get("question"):
                    self.interview.add(wa)
                    await self.show(wa, case)
                    return
                if (case.get("coverage") or {}).get("options") or (case.get("safety") or {}).get("pending_ack"):
                    await self.show(wa, case)
                    return
                await self.show(wa, case, link=True)  # nothing to ask here: the case on the site
                return
            if case["status"] != "qualified":
                await self.show(wa, case)
                return
            cmd = "prep"
        if cmd == "forum":
            option = case["coverage"]["options"][int(parts[2])]
            out = await self.api.call(wa, "POST", f"/v1/cases/{cid}/forum", json={"forum_id": option["id"]})
            await self.show(wa, out["case"], out["reply"]["message"])
            return
        if cmd == "ack":
            out = await self.api.call(wa, "POST", f"/v1/cases/{cid}/acknowledge", json={"kind": parts[2]})
            await self.show(wa, out["case"], out["reply"]["message"] or None)
            return
        if cmd == "skip":
            out = await self.api.message(wa, cid, "пропустить")
            await self.show(wa, out["case"], out["reply"]["message"])
            return
        if cmd == "ev":
            ev = next((e for e in case["evidence"] if e["id"].startswith(parts[2])), None)
            if ev is None:
                return
            out = await self.api.confirm_evidence(wa, cid, ev["id"])
            await self.show(wa, out["case"], out["reply"]["message"] or None)
            return
        if cmd == "prep":
            try:
                out = await self.api.prepare_next(wa, cid)
            except ApiError as e:
                if isinstance(e.detail, dict) and e.detail.get("code") == "payment_unavailable":
                    await self._say(wa, t("payment_unavailable", lang))
                    return
                raise
        elif cmd == "paid":
            out = await self.api.call(wa, "POST", f"/v1/cases/{cid}/payment/claim")
        elif cmd == "sub" and action:
            out = await self.api.submitted(wa, cid, action["id"])
        elif cmd == "mail" and action:
            out = await self.api.submitted(wa, cid, action["id"], via="email")
        elif cmd == "resp":
            self.awaiting_reply.add(wa)
            await self._say(wa, t("send_response", lang))
            return
        elif cmd == "none" and action:
            out = await self.api.response(wa, cid, action["id"], no_response=True)
        elif cmd == "cls" and action:
            out = await self.api.response(wa, cid, action["id"], response_class=parts[2])
        elif cmd == "close":
            amount = case.get("amount_at_stake") if parts[2] == "won" else None
            out = await self.api.close_case(wa, cid, parts[2], amount)
        await self.show(wa, (out or {}).get("case", case))
