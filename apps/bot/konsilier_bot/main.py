"""Konsilier Telegram bot (aiogram 3). All decisions are made by the API."""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           Message)

from .api import ApiError, KonsilierApi
from .i18n import t
from .ui import Screen, case_screen, last_action

log = logging.getLogger("konsilier_bot")

# chats that pressed "response arrived" and whose next message is the counterparty reply
AWAITING_REPLY: set[str] = set()
# chats that asked for a brand-new case
NEW_CASE: set[str] = set()


def keyboard(screen: Screen) -> InlineKeyboardMarkup | None:
    if not screen.buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in row] for row in screen.buttons])


def lang_of(message: Message) -> str:
    code = (message.from_user.language_code or "ru") if message.from_user else "ru"
    return "kk" if code.startswith("kk") else "ru"


async def show(bot: Bot, api: KonsilierApi, chat_id: int, case: dict, message: str | None = None) -> None:
    screen = case_screen(case, message)
    if screen.document_action:
        a = screen.document_action
        fmt = "pdf" if a["has_pdf"] else "docx"
        data = await api.document(str(chat_id), case["id"], a["id"], fmt)
        caption = t("document_caption", case["language"], title=a["title"], ai_label=case["ai_label"])
        await bot.send_document(chat_id, BufferedInputFile(data, filename=f"{a['action_id']}.{fmt}"),
                                caption=caption[:1000])
        draft = (case.get("scenario") or {}).get("draft_disclaimer")
        if draft:
            await bot.send_message(chat_id, t("draft", case["language"], text=draft))
    await bot.send_message(chat_id, screen.text, reply_markup=keyboard(screen))


def build_dispatcher(api: KonsilierApi) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        await message.answer(t("start", lang_of(message)))

    @dp.message(Command("new"))
    async def on_new(message: Message) -> None:
        NEW_CASE.add(str(message.chat.id))
        await message.answer(t("new_case", lang_of(message)))

    @dp.message(Command("status"))
    async def on_status(message: Message, bot: Bot) -> None:
        case = await api.active_case(str(message.chat.id))
        if not case:
            await message.answer(t("no_case", lang_of(message)))
            return
        await show(bot, api, message.chat.id, case)

    @dp.message(F.text)
    async def on_text(message: Message, bot: Bot) -> None:
        tg = str(message.chat.id)
        lang = lang_of(message)
        case = None if tg in NEW_CASE else await api.active_case(tg)
        if case is None:
            NEW_CASE.discard(tg)
            out = await api.create_case(tg, message.text, lang)
            await show(bot, api, message.chat.id, out["case"], out["reply"]["message"])
            return
        if tg in AWAITING_REPLY and case["status"] == "awaiting_response":
            AWAITING_REPLY.discard(tg)
            out = await api.response(tg, case["id"], last_action(case)["id"], text=message.text)
            await show(bot, api, message.chat.id, out["case"])
            return
        if case["status"] == "intake":
            out = await api.message(tg, case["id"], message.text)
            await show(bot, api, message.chat.id, out["case"], out["reply"]["message"])
            return
        await show(bot, api, message.chat.id, case)

    @dp.message(F.photo | F.document)
    async def on_file(message: Message, bot: Bot) -> None:
        tg = str(message.chat.id)
        case = await api.active_case(tg)
        if case is None:
            await message.answer(t("no_case", lang_of(message)))
            return
        if message.photo:
            file_id, filename, ctype = message.photo[-1].file_id, "photo.jpg", "image/jpeg"
        else:
            doc = message.document
            file_id, filename, ctype = doc.file_id, doc.file_name or "file", doc.mime_type or "application/pdf"
        buf = await bot.download(file_id)
        data = buf.read()
        if case["status"] == "awaiting_response":
            AWAITING_REPLY.discard(tg)
            out = await api.response_file(tg, case["id"], last_action(case)["id"], filename, data, ctype)
            await show(bot, api, message.chat.id, out["case"])
            return
        q = case.get("question") or {}
        kinds = q.get("evidence_kinds") or []
        kind = kinds[0]["kind"] if kinds else "other"
        out = await api.upload_evidence(tg, case["id"], kind, filename, data, ctype)
        ev = out["evidence"]
        lang = case["language"]
        if ev["extracted_facts"]:
            labels = {f["field"]: f["label"] for f in out["case"]["facts"]}
            facts = "\n".join(f"• {labels.get(k, k)}: {v}" for k, v in ev["extracted_facts"].items())
            text = t("evidence_found", lang, facts=facts)
        else:
            text = t("evidence_nothing", lang)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=t("buttons.confirm_facts", lang), callback_data=f"ev:{case['id']}:{ev['id'][:8]}")]])
        await message.answer(text, reply_markup=kb)

    @dp.callback_query()
    async def on_button(query: CallbackQuery, bot: Bot) -> None:
        tg = str(query.message.chat.id)
        parts = (query.data or "").split(":")
        cmd, cid = parts[0], parts[1] if len(parts) > 1 else ""
        await query.answer()
        case = await api.call(tg, "GET", f"/v1/cases/{cid}")
        action = last_action(case)
        out: dict | None = None
        if cmd == "skip":
            out = await api.message(tg, cid, "пропустить")
            await show(bot, api, query.message.chat.id, out["case"], out["reply"]["message"])
            return
        if cmd == "ev":
            ev = next(e for e in case["evidence"] if e["id"].startswith(parts[2]))
            out = await api.confirm_evidence(tg, cid, ev["id"])
            await show(bot, api, query.message.chat.id, out["case"], out["reply"]["message"] or None)
            return
        if cmd == "prep":
            out = await api.prepare_next(tg, cid)
        elif cmd == "sub":
            out = await api.submitted(tg, cid, action["id"])
        elif cmd == "mail":
            out = await api.submitted(tg, cid, action["id"], via="email")
        elif cmd == "resp":
            AWAITING_REPLY.add(tg)
            await bot.send_message(query.message.chat.id, t("send_response", case["language"]))
            return
        elif cmd == "none":
            out = await api.response(tg, cid, action["id"], no_response=True)
        elif cmd == "cls":
            out = await api.response(tg, cid, action["id"], response_class=parts[2])
        elif cmd == "close":
            result = parts[2]
            amount = case.get("amount_at_stake") if result == "won" else None
            out = await api.close_case(tg, cid, result, amount)
        await show(bot, api, query.message.chat.id, (out or {}).get("case", case))

    @dp.errors()
    async def on_error(event) -> bool:
        log.exception("bot error: %s", event.exception)
        update = event.update
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg is not None:
            text = t("error")
            if isinstance(event.exception, ApiError) and isinstance(event.exception.detail, dict):
                text = f"{text} ({event.exception.detail.get('code')})"
            await msg.answer(text)
        return True

    return dp


BOT_COMMANDS = ("start", "new", "status")


async def setup_profile(bot: Bot) -> None:
    """Menu commands and profile texts from locales; kk for Kazakh-language clients, ru for everyone else."""
    for lang, code in (("ru", None), ("kk", "kk")):
        commands = [BotCommand(command=c, description=t(f"profile.commands.{c}", lang)) for c in BOT_COMMANDS]
        await bot.set_my_commands(commands, language_code=code)
        await bot.set_my_description(t("profile.description", lang).strip(), language_code=code)
        await bot.set_my_short_description(t("profile.short", lang), language_code=code)


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN is not set — bot is idle. Set it in .env to enable Telegram.")
        while True:
            await asyncio.sleep(3600)
    api = KonsilierApi(os.environ.get("API_URL", "http://localhost:8000"), os.environ.get("BOT_API_SECRET", ""),
                       os.environ.get("BOT_DEFAULT_COUNTRY") or None)
    bot = Bot(token)
    try:
        try:
            await setup_profile(bot)
        except Exception:  # profile texts are cosmetic; never block the bot on them
            log.exception("could not set bot commands/description")
        await build_dispatcher(api).start_polling(bot)
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(run())
