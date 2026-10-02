"""Free consultation chat of a case: history, and a streamed reply from the fast model (konsilier/chat.py)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..container import Container
from ..core.models import Case, ChatMessage, Evidence, User
from ..core.pii import PiiVault
from ..gemini import EmptyReply
from .background import after_commit
from .deps import current_user, get_container, get_session
from .questions import _case_for, _context

router = APIRouter(prefix="/v1")
log = logging.getLogger(__name__)


def one_more_marker(text: str) -> str:
    """Keep the first «[[MORE]]» (the cut between the short answer and the details) and drop any later ones."""
    parts = re.split(r"\s*\[\[\s*MORE\s*\]\]\s*", text)
    if len(parts) <= 2:
        return text
    return parts[0] + "\n[[MORE]]\n" + "\n\n".join(p for p in parts[1:] if p.strip())


# Shown when no model can answer right now (Gemini over quota, Claude off or over its daily budget).
BUSY = {
    "ru": "Сейчас большая нагрузка, повторите через минуту.",
    "kk": "Қазір жүктеме көп, бір минуттан кейін қайталаңыз.",
    "en": "We're under heavy load right now. Please try again in a minute.",
    "tr": "Şu anda yoğunluk var, lütfen bir dakika sonra tekrar deneyin.",
    "ar": "الضغط كبير الآن، يرجى المحاولة مرة أخرى بعد دقيقة.",
}


def provider_of(agent: Any) -> str:
    """For metrics and the Claude budget only; never shown to clients."""
    kind = type(getattr(agent, "client", None)).__name__
    return {"GeminiClient": "gemini", "ChainClient": "free"}.get(kind, "anthropic")


def _day_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def reply_cost_usd(usage: dict[str, Any], settings: Settings) -> float:
    """Estimated cost of one Claude reply from the token counts the API returned."""
    return (usage.get("input_tokens", 0) * settings.anthropic_price_input_per_mtok / 1e6
            + usage.get("output_tokens", 0) * settings.anthropic_price_output_per_mtok / 1e6
            + usage.get("web_search_requests", 0) * settings.anthropic_price_web_search)


def chat_usage_today(session: Session, settings: Settings) -> dict[str, Any]:
    """Replies by provider, refusals and the estimated Claude spend since 00:00 UTC (stored messages only, so the
    count survives restarts and is shared by all API workers)."""
    start = _day_start()
    rows = session.execute(select(ChatMessage.role, ChatMessage.meta)
                           .where(ChatMessage.created_at >= start)).all()
    out = {"gemini": 0, "free": 0, "anthropic": 0, "unavailable": 0}
    cost = 0.0
    for role, meta in rows:
        meta = meta or {}
        if role == "assistant" and meta.get("provider") in ("gemini", "free", "anthropic"):
            out[meta["provider"]] += 1
            if meta["provider"] == "anthropic":
                cost += reply_cost_usd(meta.get("usage") or {}, settings)
        elif role == "user" and meta.get("failed"):
            out["unavailable"] += 1
    budget = settings.chat_fallback_daily_budget_usd
    return {"day": start.date().isoformat(), **out, "anthropic_cost_usd": round(cost, 4),
            "anthropic_budget_usd": budget, "fallback_open": budget > 0 and cost < budget}


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, max(0, round(q * (len(v) - 1))))]


def chat_latency(session: Session, hours: int = 24) -> dict[str, Any]:
    """Time to the first words of chat replies over the last ``hours`` (ms, the reply's ``first_ms``): p50 / p95
    overall and by the provider that answered (``served_by``: cerebras, gemini … inside the free chain)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = session.scalars(select(ChatMessage.meta).where(ChatMessage.role == "assistant",
                                                          ChatMessage.created_at >= since)).all()
    by: dict[str, list[int]] = {}
    for meta in rows:
        meta = meta or {}
        if isinstance(meta.get("first_ms"), (int, float)):
            by.setdefault(str(meta.get("served_by") or meta.get("provider") or "?"), []).append(int(meta["first_ms"]))
    every = [v for vs in by.values() for v in vs]
    return {"hours": hours, "n": len(every), "p50_ms": _percentile(every, 0.5), "p95_ms": _percentile(every, 0.95),
            "by_provider": {k: {"n": len(v), "p50_ms": _percentile(v, 0.5), "p95_ms": _percentile(v, 0.95)}
                            for k, v in sorted(by.items())}}


def warm_chat(container: Container) -> None:
    """Open the chat providers' connections in the background (the chat page opened, a case is being created), so
    the person's message does not wait for a TLS handshake. Each client does it at most once a minute."""
    clients = [getattr(a, "client", None) for a in (container.chat_agent, container.chat_fallback_agent)]
    warm = [c.warm for c in clients if c is not None and callable(getattr(c, "warm", None))]
    if warm:
        threading.Thread(target=lambda: [w() for w in warm], name="chat-warm", daemon=True).start()


def _reason(provider: str, e: Exception) -> str:
    status = getattr(e, "status_code", None)
    if status is None and (m := re.match(r"gemini (\d{3})", str(e))):
        status = m.group(1)
    return f"{provider}_{status or type(e).__name__}"


def _view(m: ChatMessage) -> dict[str, Any]:
    return {"id": str(m.id), "role": m.role, "text": m.text, "created_at": m.created_at.isoformat(),
            "attachments": m.meta.get("attachments", []), "norms": m.meta.get("norms", []),
            "sources": m.meta.get("sources", []), "offer_document": bool(m.meta.get("offer_document")),
            "ask_files": bool(m.meta.get("ask_files"))}


def _evidence_note(session: Session, case: Case, vault: PiiVault) -> list[dict[str, Any]]:
    rows = session.scalars(select(Evidence).where(Evidence.case_id == case.id)).all()
    return [vault.redact_obj({"file": e.filename, "kind": e.kind, "facts": e.extracted_facts or {},
                              "text": (e.text or "")[:1500]}) for e in rows]


@router.get("/chat/info")
def info(container: Container = Depends(get_container)) -> dict[str, Any]:
    """Whether the chat is available and its daily limit; which AI answers is not disclosed to clients. The chat page
    asks this when it opens: the providers' connections are opened meanwhile."""
    warm_chat(container)
    return {"available": container.chat_agent is not None, "daily_limit": container.settings.chat_daily_limit}


@router.get("/cases/{case_id}/chat")
def history(case_id: uuid.UUID, user: User = Depends(current_user),
            session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    case = _case_for(session, case_id, user)
    rows = session.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id)
                           .order_by(ChatMessage.created_at, ChatMessage.id)).all()
    return [_view(m) for m in rows]


REPLY_LANGS = ("ru", "kk", "en", "tr", "ar")  # the web interface languages
# the person asks for a document themselves: then it may be offered in the very first reply
ASKS_FOR_DOCUMENT = re.compile(
    r"документ|претензи|жалоб|\bиск|заявлени|составь|составить|напиши|напишите|"
    r"құжат|талап|шағым|арыз|document|claim|complaint|lawsuit|letter|draft|belge|dilekçe|şikâyet|şikayet|"
    r"مستند|شكوى|دعوى|مطالبة", re.IGNORECASE)


# P0 02.10: «да, покажите», «составьте», «нужен документ» right after a document was offered — the person wants the
# document: the reply is the paid offer (card «Услуга / Стоимость / Оплатить»), never its text written in the chat
YES_AFTER_OFFER = re.compile(
    r"^\s*(да|ага|угу|давай|давайте|хочу|покажи|покажите|показать|составь|составьте|сделай|сделайте|подготовь|"
    r"подготовьте|нужен|нужна|нужно|конечно|ок|окей|ok|yes|sure|иә|ия|иа|керек|жасаңыз|көрсетіңіз|evet|نعم)\b",
    re.IGNORECASE)
WANTS_DOCUMENT = re.compile(
    r"\b(покажи|покажите|составь|составьте|составить|напиши|напишите|подготовь|подготовьте|сделай|сделайте|пришли|"
    r"пришлите|дай|дайте|хочу|нужен|нужна)\b[^?.!\n]{0,25}\b(документ|претензи|жалоб|иск|заявлени|текст)|"
    r"\bқұжат\w*\s+(жасаңыз|көрсетіңіз|керек)", re.IGNORECASE)
# the text of a document written in the chat: a header, placeholders for the person's data, a signature line
_DOC_SIGNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in (
    r"^\s*\**\s*(ПРЕТЕНЗИЯ|ЖАЛОБА|ИСКОВОЕ\s+ЗАЯВЛЕНИЕ|ЗАЯВЛЕНИЕ|НАРАЗЫЛЫҚ|ШАҒЫМ|ТАЛАП\s+АРЫЗ)\b",
    r"^\s*\**\s*(Кому|От кого|От|Кімге|Кімнен)\s*:",
    r"[\(\[]\s*(ваш[аие]?|укажите|ФИО|дата|адрес|подпись|сумма|наименование)[^\)\]]{0,40}[\)\]]",
    r"^\s*(Подпись|Дата)\s*[:_]",
    r"^\s*(Прошу|Требую)\b",
)]


# owner 02.10: the bot asks for the documents first — under such an answer the chat shows «Сфотографировать» and
# «Приложить файл». ZANN's prompt marks it with [[FILES]]; until then the request is read from the words.
FILES_MARK = re.compile(r"\[\[\s*FILES\s*\]\]")
ASKS_FILES = re.compile(r"(?i)\b(прилож(ите|ить)|сфотографируйте|загрузите|пришлите\s+(фото|скан|копи)|"
                        r"отправьте\s+(фото|скан|копи)|жүктеңіз|суретке\s+түсіріңіз|тіркеңіз)")


def document_kinds(text: str, kinds: dict[str, tuple[str, ...]]) -> set[str]:
    """The kinds of document a text names («исковое заявление» → lawsuit), by the pack's word stems."""
    low = (text or "").lower()
    found = {k for k, stems in kinds.items() if any(s.lower() in low for s in stems)}
    if "lawsuit" in found:  # «исковое заявление» names a lawsuit, not a statement
        found.discard("statement")
    return found


def asks_for_files(text: str) -> tuple[str, bool]:
    """The reply without the [[FILES]] mark, and whether it asks the person for documents."""
    marked = bool(FILES_MARK.search(text or ""))
    clean = FILES_MARK.sub("", text or "").strip()
    return clean, marked or bool(ASKS_FILES.search(re.split(r"\[\[\s*MORE\s*\]\]", clean)[0]))


def looks_like_document(text: str) -> bool:
    """The reply writes out a claim, complaint or lawsuit (P0 02.10: the chat gave the whole claim away for free)."""
    return sum(1 for r in _DOC_SIGNS if r.search(text or "")) >= 2


def document_offer(session: Session, container: Container, case: Case, lang: str) -> dict[str, Any]:
    """What the paid document is: its title, price and whether it is paid — for the card in the chat. Before the
    scenario is known the price is the lowest document price of the country («от 2 990 ₸»)."""
    from ..core.bill import BillWords

    eng = container.engine
    title, price, currency, from_ = None, None, None, False
    try:
        pack = eng.pack_of(case)
        if case.scenario_id:
            sc = eng.scenario_of(case)
            spec = eng.next_action_spec(case, sc)
            if spec is not None:
                title = pack.localized(spec.title, pack.lang(lang))
            p = eng.price(case)
            if p is not None:
                price, currency = float(p[0]), BillWords.of(pack, p[1]).sign or p[1]
        if price is None:
            prices = [s.pricing.amount for s in eng.packs.published(pack.country)
                      if s.pricing.model == "fixed" and s.pricing.amount]
            if prices:
                price, currency, from_ = float(min(prices)), BillWords.of(pack, pack.currency).sign or pack.currency, True
    except Exception:  # noqa: BLE001 — the card works without them
        log.warning("document offer for case %s", case.id, exc_info=True)
    paid = bool(case.paid) or any(a.unlocked_by is not None for a in case.actions)
    # owner 02.10: the ways to solve it under the answer — «Дело под ключ» shows its price too
    return {"title": title, "price": price, "currency": currency, "price_from": from_, "paid": paid,
            # R-29: the ways to solve it only once the facts are there, and never under a chat naming another document
            "ready": not eng.facts_missing(case) and not (case.taxonomy or {}).get("doc_mismatch"),
            "case_price": None if case.paid else float(eng.config.case_price), "case_paid": bool(case.paid)}


def offer_text(offer: dict[str, Any], lang: str, pack: Any) -> str:
    """The paid offer in the person's language, from the pack's texts (chat_offer), always with the price."""
    lg = pack.lang(lang)
    amount = f"{offer['price']:,.0f}".replace(",", " ") if offer.get("price") else ""
    price = f"{amount} {offer.get('currency') or ''}".strip()
    if offer.get("price_from"):
        price = pack.t(lg, "chat_offer.price_from", price=price)
    title = (offer.get("title") or "").strip()
    if title:
        return pack.t(lg, "chat_offer.document", title=title, price=price)
    return pack.t(lg, "chat_offer.untitled", price=price)


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    attachments: list[str] = Field(default_factory=list, max_length=10)  # evidence ids uploaded with this message
    language: str | None = Field(default=None, max_length=5)  # the interface language: the reply is written in it


@router.get("/cases/{case_id}/chat/document")
def chat_document(case_id: uuid.UUID, user: User = Depends(current_user), session: Session = Depends(get_session),
                  container: Container = Depends(get_container)) -> dict[str, Any]:
    """The card under the chat's last reply: the document, its price and whether it is paid (P0 02.10)."""
    case = _case_for(session, case_id, user)
    return document_offer(session, container, case, case.language or "ru")


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/cases/{case_id}/chat")
def send(case_id: uuid.UUID, body: ChatIn, user: User = Depends(current_user),
         session: Session = Depends(get_session), container: Container = Depends(get_container)) -> StreamingResponse:
    case = _case_for(session, case_id, user)
    agent = container.chat_agent
    if agent is None:
        raise HTTPException(503, {"code": "agent_unavailable", "message": "agent_unavailable"})
    since = datetime.now(timezone.utc) - timedelta(days=1)
    # messages nobody could answer (overload) do not use up the daily limit
    metas = session.scalars(select(ChatMessage.meta).where(
        ChatMessage.user_id == user.id, ChatMessage.role == "user", ChatMessage.created_at > since)).all()
    sent = sum(1 for m in metas if not (m or {}).get("failed"))
    daily_limit = container.settings.chat_daily_limit
    if sent >= daily_limit:
        raise HTTPException(429, {"code": "too_many_messages", "message": "too_many_messages",
                                  "limit": daily_limit, "remaining": 0, "window_hours": 24})

    names = {str(e.id): e.filename for e in case.evidence}
    attachments = [{"id": a, "filename": names[a]} for a in body.attachments if a in names]
    asked = ChatMessage(case_id=case.id, user_id=user.id, role="user", text=body.text,
                        meta={"attachments": attachments})
    session.add(asked)
    session.flush()
    asked_pk = asked.id
    asked_text = body.text
    rows = session.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id)
                           .order_by(ChatMessage.created_at, ChatMessage.id)).all()
    ctx = _context(container, case)
    vault: PiiVault = ctx.pop("vault")
    pack = ctx["pack"]
    ctx["case"] = {**ctx["case"], "files": _evidence_note(session, case, vault)}
    turns = [{"role": m.role, "text": vault.redact(m.text)} for m in rows]
    lang = pack.lang(case.language)  # the pack's language for its titles (KZ: ru, kk)
    # the reply follows the person: the interface language they write from, else the case's language — not the pack's
    # fallback (an English page got Russian answers because the KZ pack has only ru and kk)
    reply_lang = (body.language or case.language or lang).split("-")[0].lower()
    if reply_lang not in REPLY_LANGS:
        reply_lang = lang
    country = pack.localized(pack.manifest.name, "en") or pack.country
    portal = [s for s in pack.manifest.legal_sources if agent.portal_domain in str(s.url)]
    use_portal = bool(portal)
    ctx["lang"] = lang
    ctx["case_id"] = str(case.id)
    ctx["key_acts"] = [{"code": a.code, "title": pack.localized(a.title, lang)} for s in portal for a in s.key_acts]
    case_pk, user_pk = case.id, user.id
    # a test account (production smoke checks, deploy/smoke.py): its replies carry where the time went, so the speed
    # can be measured from outside without the server logs; never for a real person
    diagnostics = bool(user.is_test)
    first_reply = not any(m.role == "assistant" for m in rows)
    if not case.scenario_id and case.status == "intake" and not (case.taxonomy or {}).get("dispute_id"):
        # the first message said too little to classify: try again with what the person tells now (PM 02.10)
        after_commit(session, container, lambda s: container.engine.requalify_from_chat(s, case_pk), "requalify")
    session.commit()  # the user's message is saved even if the reply fails

    agents = [a for a in (agent, container.chat_fallback_agent) if a is not None]
    settings = container.settings

    def fallback_allowed() -> bool:
        with container.session_factory() as s:
            return chat_usage_today(s, settings)["fallback_open"]

    def unavailable(reason: str, started: bool) -> Iterator[str]:
        """No reply: say so in the person's language and give the message back to the daily limit."""
        log.warning("chat=unavailable reason=%s case=%s started=%s", reason, case_pk, int(started))
        with container.session_factory() as s:
            m = s.get(ChatMessage, asked_pk)
            if m is not None:
                m.meta = {**(m.meta or {}), "failed": reason}
                s.commit()
        ev = {"type": "error", "code": "agent_failed" if started else "busy", "message": BUSY.get(lang, BUSY["ru"])}
        if diagnostics:
            ev["reason"] = reason
        yield _sse(ev)

    t_request = time.perf_counter()
    last_reply = next((m for m in reversed(rows[:-1]) if m.role == "assistant"), None)
    offered = bool(last_reply is not None and (last_reply.meta or {}).get("offer_document"))
    complete = not container.engine.facts_missing(case)  # R-29: no offer while the case lacks its facts
    if complete and ((offered and YES_AFTER_OFFER.search(body.text)) or WANTS_DOCUMENT.search(body.text)):
        # the person wants the document: the paid offer at once, no model — the chat never writes it out (P0 02.10)
        with container.session_factory() as s:
            c = s.get(Case, case_pk)
            offer = document_offer(s, container, c, reply_lang)
            if not offer["paid"]:
                m = ChatMessage(case_id=case_pk, user_id=None, role="assistant", text=offer_text(offer, reply_lang, container.engine.pack_of(c)),
                                meta={"provider": "offer", "offer_document": True, "pay_now": True})
                s.add(m)
                container.engine.audit(s, c, f"user:{user_pk}", "chat_document_offer")
                s.commit()
                view = _view(m)

                def offered_now() -> Iterator[str]:
                    yield _sse({"type": "text", "text": view["text"]})
                    yield _sse({"type": "done", "message": view, "limit": daily_limit,
                                "remaining": max(daily_limit - sent - 1, 0), "window_hours": 24})
                return StreamingResponse(offered_now(), media_type="text/event-stream",
                                         headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def events() -> Iterator[str]:
        # waiting for a worker thread between the response and its first chunk (a busy server shows here)
        queue_ms = int((time.perf_counter() - t_request) * 1000)
        result, used, reasons, started = None, None, [], False
        first_ms: int | None = None  # how long the person waited for the first words
        for i, a in enumerate(agents):
            provider = provider_of(a)
            if i > 0 and provider == "anthropic" and not fallback_allowed():
                reasons.append("anthropic_budget")
                break
            started = False
            try:
                for ev in a.stream(turns, context=ctx, language=f"the language with ISO 639-1 code '{reply_lang}'",
                                   country=country, use_portal=use_portal):
                    if ev["type"] == "done":
                        result = ev["result"]
                    else:
                        started = started or ev["type"] == "text"
                        if started and first_ms is None:
                            first_ms = int((time.perf_counter() - t_request) * 1000)
                        yield _sse(ev)
                if result is None or not (result.text or "").strip():
                    # a reply never ends empty: the fallback, else «busy» (the message goes back to the limit)
                    raise EmptyReply(f"{provider}: empty reply")
                used = provider
                break
            except Exception as e:  # quota, API down, no credits, …: the fallback agent, else "try in a minute"
                reasons.append(_reason(provider, e))
                if started:
                    break
                if i < len(agents) - 1:
                    log.warning("chat agent failed before the reply started, trying the fallback: %s", str(e)[:200])
        if used is None or result is None:
            yield from unavailable("+".join(reasons) or "no_reply", started)
            return
        text = vault.restore(result.text) if result else ""
        text = one_more_marker(text)  # QA BUG-05: a second [[MORE]] (after a tool call) never reaches the client
        cut = looks_like_document(text)
        if cut:
            # P0 02.10: the model wrote the document out — keep the short answer, the document is the paid offer
            with container.session_factory() as s:
                cc = s.get(Case, case_pk)
                offer = document_offer(s, container, cc, reply_lang)
                pack_cc = container.engine.pack_of(cc)
            short = re.split(r"\[\[\s*MORE\s*\]\]", text)[0].strip()
            short = "" if looks_like_document(short) else short
            text = f"{short}\n\n{offer_text(offer, reply_lang, pack_cc)}".strip()
            result.offer_document = True
            log.warning("chat=document_text_cut case=%s", case_pk)
        # owner 30.09: not in the first reply — unless the person asks for a document or attached documents (01.10)
        # owner 01.10 (decision 167): in the first reply too when the situation is clear — the scenario is known
        with container.session_factory() as s:
            clear = bool(getattr(s.get(Case, case_pk), "scenario_id", None))
        if result.offer_document and first_reply and not clear and not ASKS_FOR_DOCUMENT.search(body.text) \
                and not body.attachments:
            result.offer_document = False  # owner 30.09: never in the first reply — it scares people off
        if cut:  # the document's text was taken out: its place is the paid offer, even in the first reply
            result.offer_document = True
        with container.session_factory() as s:
            cc = s.get(Case, case_pk)
            missing = container.engine.facts_missing(cc) if cc is not None else []
            if result.offer_document and missing:
                # R-29 (owner 02.10): no solution buttons and no paid offer while who, whom, what, when, how much is
                # not known — the next missing fact is asked instead
                result.offer_document = False
                if missing != ["scenario"]:
                    eng = container.engine
                    sc_cc, pack_cc = eng.scenario_of(cc), eng.pack_of(cc)
                    q = eng.question_for(sc_cc, pack_cc, pack_cc.lang(reply_lang), missing[0]).text
                    if cut:
                        text = re.split(r"\[\[\s*MORE\s*\]\]", text)[0].strip()
                        text = "" if looks_like_document(text) else text
                    if q and q not in text:
                        text = f"{text}\n\n{q}".strip()
        text, ask_files = asks_for_files(text)
        if result.offer_document:
            # PM 02.10: the chat and the card name the same document — «Составлю исковое заявление» over a card
            # «Досудебная претензия» is a contradiction: the card is withheld and the case goes to a second look
            with container.session_factory() as s:
                cc = s.get(Case, case_pk)
                pack_cc = container.engine.pack_of(cc)
                kinds = pack_cc.coverage.routing.document_kinds if pack_cc.coverage else {}
                title = (document_offer(s, container, cc, reply_lang).get("title") or "") if kinds else ""
                said = document_kinds(text, kinds)  # anywhere in the reply, «Подробнее» too
                card = document_kinds(title, kinds)
                if said and card and not said & card:
                    result.offer_document = False
                    cc.needs_review = True
                    cc.taxonomy = {**(cc.taxonomy or {}), "doc_mismatch": True}  # the card stays hidden
                    container.engine.audit(s, cc, "system", "chat_document_mismatch", chat=sorted(said),
                                           card=sorted(card), title=title)
                    s.commit()
                    log.warning("chat=document_mismatch case=%s chat=%s card=%s", case_pk, sorted(said), sorted(card))
                elif (cc.taxonomy or {}).get("doc_mismatch"):
                    cc.taxonomy = {k: v for k, v in cc.taxonomy.items() if k != "doc_mismatch"}  # they agree again
                    s.commit()
        # the agent's phases (library, each model round with the providers tried, each tool call and its source)
        timing = {**(getattr(result, "timing", None) or {}), "queue_ms": queue_ms}
        served_by = timing.get("provider") or used  # inside the free chain: cerebras, gemini …
        log.info("chat timing: case=%s summary %s", case_pk, json.dumps(
            {k: v for k, v in timing.items() if k not in ("rounds", "tools")} | {
                "first_ms": first_ms, "served_by": served_by, "rounds": len(timing.get("rounds", [])),
                "tools": [t.get("source") for t in timing.get("tools", [])]}))
        with container.session_factory() as s:
            m = ChatMessage(case_id=case_pk, user_id=None, role="assistant", text=text,
                            meta={"provider": used, "served_by": served_by, "norms": result.norms,
                                  "sources": result.sources, "unchecked": result.unchecked,
                                  "offer_document": result.offer_document, "tool_calls": result.tool_calls,
                                  "ask_files": ask_files and not result.offer_document,
                                  "usage": result.usage, "first_ms": first_ms,
                                  # P0 01.10: rounds cut before their end ("provider:reason") — continued, or the
                                  # reply ended at its last whole sentence (trimmed); counted hourly (chatspeed)
                                  "truncated": getattr(result, "truncated", "") or None,
                                  "trimmed": bool(getattr(result, "trimmed", False)),
                                  "total_ms": int((time.perf_counter() - t_request) * 1000), "timing": timing})
            s.add(m)
            c = s.get(Case, case_pk)
            container.engine.audit(s, c, f"user:{user_pk}", "chat_reply", tokens=result.usage,
                                   unchecked=result.unchecked)
            # QA BUG-03: the facts told in the chat go into the case (after the reply, never delaying it)
            after_commit(s, container, lambda s2: container.engine.facts_from_chat(s2, case_pk, asked_text),
                         "chat_facts")
            s.commit()
            log.info("chat=reply case=%s provider=%s first_ms=%s total_ms=%s tools=%s", case_pk, used, first_ms,
                     m.meta.get("total_ms"), result.tool_calls)
            if result.unchecked:  # not shown to the person; the team watches how often it happens
                log.warning("chat=unchecked_norms case=%s", case_pk)
            # what is left of the daily limit (a rolling 24-hour window) after this answered message
            done = {"type": "done", "message": _view(m), "limit": daily_limit,
                    "remaining": max(daily_limit - sent - 1, 0), "window_hours": 24}
            if diagnostics:
                done["diagnostics"] = {"served_by": served_by, "first_ms": first_ms,
                                       "total_ms": m.meta.get("total_ms"), "timing": timing}
            yield _sse(done)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
