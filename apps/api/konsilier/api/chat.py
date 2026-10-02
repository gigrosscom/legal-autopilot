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
            "ask_files": bool(m.meta.get("asked_documents") or m.meta.get("ask_files"))}


# owner 02.10 (decisions.md): understand the gist → ask for the documents (what is in them is read, never asked) → one
# or two questions only if still short → then the solution. The chat model sees which documents this scenario uses,
# which of them came, which facts are already known (from the story, the chat and the files) and which facts that
# change the solution are still missing — names, addresses and ID numbers are left to the form before payment.
DOC_DETAIL = re.compile(r"_(?:name|address|bin|iin|email|phone)$")


def intake_note(container: Container, case: Case, lang: str) -> dict[str, Any]:
    if not case.scenario_id:
        return {}
    try:
        sc = container.engine.scenario_of(case)
        pack = container.engine.pack_of(case)
    except Exception:  # noqa: BLE001 — a scenario that went away: the chat goes on without the note
        return {}
    came = {e.kind for e in case.evidence}
    kinds = [k for f in sc.intake if f.type == "evidence" for k in f.evidence_kinds
             if k not in ("id_document", "other")]
    facts = case.facts or {}
    return {
        "documents_to_ask": [pack.t(lang, f"evidence.{k}", default=k) for k in kinds if k not in came],
        "documents_received": [pack.t(lang, f"evidence.{k}", default=k) for k in kinds if k in came],
        "facts_known": sorted(n for n in facts if not n.startswith("_")),
        # one list with the offer's gate (engine.facts_missing, R-29): the chat asks exactly what the gate waits for
        "facts_missing": [n for n in container.engine.facts_missing(case) if n != "scenario"],
    }


ASKED_DOCUMENTS = re.compile(r"пришлите|прикрепите|приложите|загрузите|сфотографируйте|отправьте\s+(?:фото|скан|копи)|"
                             r"жіберіңіз|жүктеңіз|суретке\s+түсіріңіз|тіркеңіз|"
                             r"send\s+(?:a\s+)?(?:photo|scan|cop)|upload", re.IGNORECASE)


SOLUTION = re.compile(r"\[\[\s*MORE\s*\]\]|Что делать:|Не істеу керек:", re.IGNORECASE)
STEPS_HEAD = {"ru": "Что делать:", "kk": "Не істеу керек:"}


def route_steps_text(route: list[dict[str, Any]], lang: str) -> str:
    """«Что делать:» and the route's steps, one line each (who, and when the next one comes in)."""
    if not route:
        return ""
    lines = [STEPS_HEAD.get(lang, STEPS_HEAD["ru"])]
    for st in route[:3]:
        label = (st.get("label") or "").strip().rstrip(".")
        when = f" — {st['when'].strip().rstrip('.')}" if st.get("when") else ""
        lines.append(f"{st['step']}. **{label}**{when}.")
    return "\n".join(lines)


def missing_question(container: Container, case: Case, lang: str, field: str) -> str:
    """The chat's words for the fact a solution still waits for (chat_ask), else the form's question."""
    eng = container.engine
    try:
        sc, pack = eng.scenario_of(case), eng.pack_of(case)
    except Exception:  # noqa: BLE001
        return ""
    lg = pack.lang(lang)
    return pack.t(lg, f"chat_ask.{field}", default="") or eng.question_for(sc, pack, lg, field).text or ""


def asked_and_answered(rows: list[Any], question: str) -> bool:
    """The bot already asked this very question and the person wrote after it."""
    if not question:
        return False
    for i, m in enumerate(rows):
        if m.role == "assistant" and question in (m.text or ""):
            return any(r.role == "user" for r in rows[i + 1:])
    return False


def needs_documents_line(text: str, *, asked_before: bool, offer: bool, files: bool, told: str) -> bool:
    """A fact-finding question (no solution, no offer) that does not ask for the documents, in a chat where they were
    never asked and none came, after a story (not «здравствуйте»). The QA gate (scripts/qa_gate.py) uses it too."""
    return (not ASKED_DOCUMENTS.search(text) and not asked_before and not offer and not files
            and not re.search(r"\[\[\s*MORE", text) and text.rstrip().endswith("?") and len(told) >= 40)


def documents_line(pack: Any, lang: str, note: dict[str, Any]) -> str:
    """The one sentence asking for the documents (owner 02.10), with this scenario's documents when known."""
    docs = [d[:1].lower() + d[1:] for d in note.get("documents_to_ask") or []]
    listed = "; ".join(docs) if docs else pack.t(lang, "chat_documents.any")
    return pack.t(lang, "chat_documents.ask", docs=listed)


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


# owner 02.10: the bot asks for the documents first — under such an answer (meta asked_documents, ASKED_DOCUMENTS)
# the chat shows «Сфотографировать» and «Приложить файл»; ZANN's prompt may also mark it with [[FILES]]
FILES_MARK = re.compile(r"\[\[\s*FILES\s*\]\]")


# a sentence pointing at a button («…после нажатия кнопки „Составить документ“ ниже»)
_BUTTON_SENTENCE = re.compile(r"[^.!?\n]*(?:кнопк|түйме|\bbutton\b|«Составить документ»|«Оплатить»|\"Составить документ\")"
                              r"[^.!?\n]*[.!?]?", re.IGNORECASE)


def without_button_talk(text: str) -> str:
    """PM 02.10: when no card is shown, a sentence about a button that is not there is taken out."""
    out = _BUTTON_SENTENCE.sub("", text or "")
    out = re.sub(r"[ \t]+\n", "\n", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def document_kinds(text: str, kinds: dict[str, tuple[str, ...]]) -> set[str]:
    """The kinds of document a text names («исковое заявление» → lawsuit), by the pack's word stems."""
    low = (text or "").lower()
    found = {k for k, stems in kinds.items() if any(s.lower() in low for s in stems)}
    if "lawsuit" in found:  # «исковое заявление» names a lawsuit, not a statement
        found.discard("statement")
    return found


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
    ctx["case"] = {**ctx["case"], "files": _evidence_note(session, case, vault),
                   **intake_note(container, case, pack.lang(case.language)),
                   # the route only once the facts are in: given earlier it pulled the model to a solution (P0 02.10)
                   "route": [{k: st[k] for k in ("step", "label", "when", "why", "norm")}
                             for st in container.engine.recipient_route(case)]
                   if not container.engine.facts_missing(case) else []}
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
    # PM 02.10 P0: the sum and the date the person wrote are read by rule before anything else (a model that missed
    # «450 000 тенге» kept the chat asking for it forever)
    if container.engine.facts_from_text(session, case, [m.text for m in rows if m.role == "user"]):
        session.commit()
    missing_now = container.engine.facts_missing(case)
    # a question asked and answered is never asked again: the solution goes on with what there is (PM 02.10 P0)
    complete = not missing_now or (missing_now != ["scenario"]
                                   and asked_and_answered(rows, missing_question(container, case, reply_lang, missing_now[0])))
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
            if missing and missing != ["scenario"] and asked_and_answered(
                    rows, missing_question(container, cc, reply_lang, missing[0])):
                missing = []  # asked and answered already: the offer goes on with what there is (PM 02.10 P0)
            if result.offer_document and missing:
                # R-29 (owner 02.10): no solution buttons and no paid offer while who, whom, what, when, how much is
                # not known; if the bot did not ask anything itself, the next missing fact is asked (one question)
                result.offer_document = False
                if cut:
                    text = re.split(r"\[\[\s*MORE\s*\]\]", text)[0].strip()
                    text = "" if looks_like_document(text) else text
                asked = "?" in (text.rstrip().splitlines() or [""])[-1]  # «Когда? (ДД.ММ.ГГГГ)» is a question too
                if missing != ["scenario"] and not asked:
                    eng = container.engine
                    sc_cc, pack_cc = eng.scenario_of(cc), eng.pack_of(cc)
                    q = missing_question(container, cc, reply_lang, missing[0]) or \
                        eng.question_for(sc_cc, pack_cc, pack_cc.lang(reply_lang), missing[0]).text
                    if q and q not in text:
                        text = f"{text}\n\n{q}".strip()
                        yield _sse({"type": "text", "text": f"\n\n{q}"})
        # PM 02.10 (P0 after #215): a solution comes only after the facts (R-29, decisions 225, 226, 229) and its steps
        # follow the case's route (R-35). The facts of this very message are read first (they would otherwise reach
        # the case only after the reply, and the bot would ask the sum it was just told).
        if SOLUTION.search(text):
            eng = container.engine
            with container.session_factory() as s:
                cc = s.get(Case, case_pk)
                missing = eng.facts_missing(cc) if cc is not None else []
                if missing and missing != ["scenario"]:
                    try:
                        eng.facts_from_chat(s, case_pk, asked_text)
                        s.commit()
                    except Exception:  # noqa: BLE001 — no extraction: ask, never guess
                        log.warning("chat facts before the solution failed for case %s", case_pk, exc_info=True)
                    cc = s.get(Case, case_pk)
                    missing = eng.facts_missing(cc)
                q = ""
                if missing and missing != ["scenario"]:
                    q = missing_question(container, cc, reply_lang, missing[0])
                    if asked_and_answered(rows, q):  # asked and answered: no loop, the solution with what there is
                        log.warning("chat=question_not_repeated case=%s field=%s", case_pk, missing[0])
                        q = ""
                route = eng.recipient_route(cc) if cc is not None and not q else []
                kinds = (eng.pack_of(cc).coverage.routing.document_kinds
                         if cc is not None and eng.pack_of(cc).coverage else {})
            if q:  # not yet: one question (and the documents, below), no solution and no card
                own = [ln for ln in re.split(r"\[\[\s*MORE\s*\]\]", text)[0].splitlines() if ln.strip().endswith("?")]
                text = own[-1].strip() if own else q
                result.offer_document = False
                log.info("chat=solution_held case=%s missing=%s", case_pk, missing)
            else:
                # the facts are in: the solution starts with «Что делать:» — no greeting, no question before it
                # (QA gate 02.10: K3, K6, K9 asked and solved in one reply)
                head = re.search(r"(?m)^\s*(?:Что делать:|Не істеу керек:)", text)
                if head and head.start() > 0 and "[[MORE]]" not in text[:head.start()]:
                    text = text[head.start():].lstrip()
            if not q and route:
                short = re.split(r"\[\[\s*MORE\s*\]\]", text, maxsplit=1)
                first = next((ln for ln in short[0].splitlines() if re.match(r"\s*\**\s*1[.)]", ln)), "")
                want = document_kinds(route[0].get("label") or "", kinds)
                if first and want and not (document_kinds(first, kinds) & want):  # its first step is not the route's
                    text = route_steps_text(route, reply_lang) + (
                        f"\n\n[[MORE]]\n{short[1].strip()}" if len(short) > 1 and short[1].strip() else "")
                    log.warning("chat=steps_from_route case=%s model_first=%r", case_pk, first[:120])
        # [[FILES]] — ZANN's mark of a reply that asks for the documents: taken out of the text, counted as asking
        marked_files = bool(FILES_MARK.search(text))
        text = FILES_MARK.sub("", text).strip()
        # owner 02.10: documents first. A fact-finding question (no solution yet) asks for the documents once; if the
        # model forgot, the server adds the sentence — no files yet, never asked before in this chat.
        asked_docs = marked_files or bool(ASKED_DOCUMENTS.search(text))
        asked_before = any((m.meta or {}).get("asked_documents") for m in rows if m.role == "assistant")
        if needs_documents_line(text, asked_before=asked_before, offer=result.offer_document,
                                files=bool(body.attachments or ctx["case"].get("files")),
                                told=" ".join(m.text for m in rows if m.role == "user")):
            extra = documents_line(pack, lang if reply_lang not in ("ru", "kk") else reply_lang, ctx["case"])
            if extra and "{" not in extra:
                text = f"{text.rstrip()}\n\n{extra}"
                yield _sse({"type": "text", "text": f"\n\n{extra}"})
                asked_docs = True
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
        if not result.offer_document:
            text = without_button_talk(text)  # no card under this reply: no word about its button
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
                                  # one sign for «the bot asks for the documents»: the upload buttons show under it
                                  "asked_documents": asked_docs and not result.offer_document,
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
