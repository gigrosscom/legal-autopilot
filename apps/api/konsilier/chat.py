"""Free consultation chat: a fast model talks with the person, collects the facts and explains the next steps.

The chat answers in plain words and streams its reply. It may look up the official text of an article (the same
portal tools as the legal agent, konsilier/lawagent), the registry of bodies of the country pack and the library of
official pages (konsilier/official: state services, benefits, grants, tenders — refreshed at night, searched in
milliseconds, never crawled during a conversation); it is told never to state article numbers, deadlines, fees or
addressees from memory. Before the model is called the library is searched with the person's last message and the
best excerpts go into the context, so every model benefits, whether or not it calls tools. After the reply a check compares the
article numbers mentioned in it with the articles actually opened in this turn: anything not opened is flagged
"unchecked" in the reply's meta for metrics and logs (the person is not shown a note). Documents are prepared by the case engine (a separate,
paid step), not by the chat.

Speed (owner 30.09: first words within ~2 s): articles are cut from the Zann corpus copy when it has the act
(milliseconds; the live portal otherwise), and the phases — library search, each model round with the providers
tried, each tool call and where its text came from, the first words — are logged as "chat timing:" and kept in
``ChatResult.timing``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from .lawagent.agent import LawAgent
from .lawagent.sources import Adilet
from .official.search import Hit

log = logging.getLogger(__name__)

HISTORY_TURNS = 20  # messages sent to the model; older ones are dropped
PRE_HITS = 3  # library excerpts added to the context before the model is called
TOOL_HITS = 5  # excerpts one official_sources call returns

SYSTEM = """You are Konsiliér AI, a free assistant that helps people in {country} with legal questions.
Talk like a patient, friendly consultant: short plain sentences, no legal jargon.
Language: write every sentence in {language} — also the short notes you write before or while looking something up
with a tool. Never switch to English or any other language, whatever language the tools return.

Reply shape — short first, details on request
Start every reply with the SHORT ANSWER: 1–3 plain sentences, at most about 50 words, that answer exactly what was
asked: the person's rights in one line and the key action in **bold**. If the answer depends on a fact, add one
short question there. Then write {more_marker} on its own line, and after it the DETAILS: the numbered steps, what
to prepare, the official sources («По данным …» with links) and caveats. The app shows only the short answer and a
«Подробнее» link that opens the details, so the short answer must make sense on its own and never say "see below".
If there is nothing to add (a greeting, a one-line fact), write only the short answer, without the marker.
Never write the words "SHORT ANSWER", "DETAILS" or any other label — just the text.
Speed matters: the person is waiting. Write the short answer FIRST, before calling any tool, from what you already
know and the excerpts given below; call tools only afterwards, for the details (an article, a deadline, a body).

How to work
1. Help at once, then ask. Every reply first gives something useful: what the person's rights most likely are and
   what to do now; the steps as a short numbered list go into the details. Only if the answer depends on it, ask
   one or two short questions about the facts that matter (when it happened, how much money, which documents the
   person has). Never reply with questions alone, do not interrogate, and do not ask for anything that is already
   in the case context or in the files the person attached.
   Format: short paragraphs, numbered steps, **bold** for the main action; no tables, no headings.
2. Find out who the person is in the dispute: a private individual, or a business (sole trader, company). Consumer
   protection rules protect individuals who buy for personal use; a dispute between businesses follows the contract
   and the civil code. Never apply consumer protection rules to a business.
3. Explain what the person can do, step by step, and what to prepare.
4. Legal rules: never state an article number, a deadline, a fee or which body to write to from memory.
   {portal_rule}
   Bodies and courts come only from the forums tool. For any date use the deadline tool.
   If you could not check something, say so plainly instead of guessing.
5. Offer a document later, never in your first reply of the conversation (unless the person asks for a document
   themselves). Offer it when the key facts are known (who, what, when, how much, whether there is a receipt or a
   contract) and a written claim, complaint, lawsuit or application is really the next step. Offer it softly, as a
   question in one sentence, e.g. «Могу подготовить претензию продавцу — показать?», and end the reply (after the
   details) with the marker {offer_marker} on its own line (the app shows a button there). Never offer a document for
   a question that only needs an explanation, never twice in a row, and never write about buttons or prices yourself.
6. Applications, not disputes. Many people ask how to get something from the state: a social benefit (at the birth
   of a child, childcare, disability, loss of a breadwinner, targeted social assistance, loss of a job), a grant or
   non-repayable funding for a business, an education grant or a scholarship, or how to take part in a public
   tender. Guide them in order:
   - which benefit, programme or procedure fits, and who may apply (say it depends on the official rules);
   - where people usually apply: the country's e-government portal or its mobile app, a public service centre,
     the local administration or employment office, the programme's organiser, the official procurement portal.
     Name the official site only as the place to check the service standard or the announcement;
   - which documents are typically asked for (identity document, bank account, certificates of birth, death,
     disability or income; for a business: registration, no tax debt, a business plan and a budget; for a tender:
     the qualification documents and the bid security the tender documents require);
   - the steps: find the service or announcement, check eligibility, collect documents, apply before the
     deadline, keep the receipt, and what to do after a refusal.
   Amounts, income thresholds, deadlines and document lists change and depend on the programme: never state them
   from memory. {official_rule}
   Never promise that a benefit, a grant, a place or a tender will be won. Konsiliér AI can prepare the
   package (application, checklist, cover letter, business plan outline, inventory) with the same button. A refusal
   or a rejected bid is a dispute again: follow steps 3–5, and the body to complain to comes only from the forums
   tool.
7. Criminal defence, children's custody, large sums or missed deadlines: say plainly that this needs a lawyer.
   Never promise an outcome. Never ask about or guess religion or other sensitive traits.
8. Files the person attached are listed in the case context with any text read from them: use them.
Keep the details under about 200 words unless the person asks for more."""

PORTAL_RULE = ("State an article number only if you opened that article's text with get_article or act_contents "
               "in this reply; otherwise name the law or code by its title without any article number. "
               "Find the act among the main acts listed below{search}.")
NO_PORTAL_RULE = ("You have no access to the official texts here, so never state article numbers: name the law or "
                  "code by its title only.")
OFFICIAL_RULE = ("For a question about a state service, a benefit, a grant or business support, an education grant, a "
                 "public tender or an e-government procedure, first consult the official library: the excerpts given "
                 "below for the last message, or official_sources with a short query. State an amount, a deadline, an "
                 "income threshold or a document list only as an excerpt says it, and cite it as «По данным <domain>: "
                 "…» (in the reply language) with the page link. If the library has nothing on the question, say so "
                 "plainly and name the official portal to check (listed below); never fill the gap from memory.")
NO_OFFICIAL_RULE = ("Say plainly that they must be checked in the official service standard, programme rules or tender "
                    "documents.")

# "статья 113", "ст. 113-1", "113-бап", "article 113", "madde 113", "المادة 113"
ARTICLE_MENTION = re.compile(
    r"(?:стать\w*|ст\.|article|art\.|madde\w*|المادة)\s*(\d+(?:-\d+)?)|(\d+(?:-\d+)?)\s*-?\s*бап",
    re.IGNORECASE)


@dataclass
class ChatResult:
    text: str
    norms: list[dict[str, str]] = field(default_factory=list)
    unchecked: bool = False
    tool_calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)  # official pages the reply cites (url, title, domain)
    offer_document: bool = False  # the reply ends with OFFER_MARKER: the app shows «Составить документ» under it
    # where the time went (ms): library search, each model round (with the providers tried), each tool call and
    # where its text came from, the first words; logged as "chat timing:" and kept in the reply's meta
    timing: dict[str, Any] = field(default_factory=dict)


OFFER_MARKER = "[[DOCUMENT]]"


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)
MORE_MARKER = "[[MORE]]"  # between the short answer and the details; the app shows the details under «Подробнее»


def take_offer(text: str) -> tuple[str, bool]:
    """The reply without the document marker, and whether it had one (models sometimes drop a bracket)."""
    cleaned = re.sub(r"\[?\[\s*DOCUMENT\s*\]\]?", "", text)
    return cleaned.strip(), cleaned != text


# Some open models slip a word of Chinese or Japanese into an answer in a Cyrillic language ("если 母亲 работала"). The
# person never reads those scripts here, so such runs are dropped from the stream.
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]+ ?")


def strip_foreign_script(text: str, language: str) -> str:
    if not text or language.lower().startswith(("chinese", "japanese", "korean", "中", "日", "한")):
        return text
    return _CJK.sub("", text)


def mentioned_articles(text: str) -> set[str]:
    return {m.group(1) or m.group(2) for m in ARTICLE_MENTION.finditer(text)}


class ChatAgent:
    def __init__(self, client: Any, model: str, adilet: Adilet | None = None, *,
                 portal_domain: str = "adilet.zan.kz", max_turns: int = 6, max_tokens: int = 2000,
                 web_search: bool = True, library: Any = None):
        self.client, self.model, self.max_turns, self.max_tokens = client, model, max_turns, max_tokens
        self.portal_domain, self.web_search = portal_domain, web_search
        self.library = library  # konsilier.official.search.OfficialLibrary, or None
        # the portal tools are the legal agent's; the chat reuses them rather than re-implementing
        self._law = LawAgent(client, model, adilet or Adilet(), portal_domain=portal_domain)

    def tools(self, use_portal: bool, use_library: bool = False) -> list[dict[str, Any]]:
        out = []
        if use_library:
            out.append({"name": "official_sources",
                        "description": "Search the library of official state pages (services, benefits, grants, "
                                       "business support, tenders, e-government how-tos). Returns excerpts with the "
                                       "page URL, title and domain.",
                        "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                                         "properties": {"query": {"type": "string", "description":
                                                                  "A few key words in the language of the pages"}}}})
        for t in self._law.tools():
            if t.get("name") == "web_search":
                if use_portal and self.web_search:  # basic search variant: works on the fast model too
                    out.append({"type": "web_search_20250305", "name": "web_search", "max_uses": 2,
                                "allowed_domains": [self.portal_domain]})
            elif t["name"] in ("act_contents", "get_article"):
                if use_portal:
                    out.append(t)
            else:
                out.append(t)
        return out

    def stream(self, history: list[dict[str, str]], *, context: dict[str, Any], language: str, country: str,
               use_portal: bool) -> Iterator[dict[str, Any]]:
        """Yield {"type": "text", "text"} chunks and {"type": "tool", "name"} markers; the last event is
        {"type": "done", "result": ChatResult}."""
        t0 = time.perf_counter()
        timing: dict[str, Any] = {"rounds": [], "tools": []}
        case_id = context.get("case_id", "")
        got: dict[tuple[str, str], Any] = {}
        found: dict[str, Hit] = {}  # official pages seen in this turn, by URL
        case_note = json.dumps(context.get("case", {}), ensure_ascii=False)
        messages: list[dict[str, Any]] = [{"role": m["role"], "content": m["text"]} for m in history[-HISTORY_TURNS:]]
        if messages and messages[0]["role"] != "user":
            messages = messages[1:]
        cc, lang = getattr(context.get("pack"), "country", None), context.get("lang")
        use_library = self.library is not None and self.library.available(cc)
        search = " or with web_search on the official portal" if self.web_search else ""
        system = SYSTEM.format(country=country, language=language, offer_marker=OFFER_MARKER, more_marker=MORE_MARKER,
                               portal_rule=PORTAL_RULE.format(search=search) if use_portal else NO_PORTAL_RULE,
                               official_rule=OFFICIAL_RULE if use_library else NO_OFFICIAL_RULE)
        if use_portal and context.get("key_acts"):
            system += "\n\nMain acts on the official portal (code — title):\n" + "\n".join(
                f"{a['code']} — {a['title']}" for a in context["key_acts"])
        if use_library:
            portals = self.library.portals(cc, lang or "")
            if portals:
                system += "\n\nOfficial portals (domain — what is there):\n" + "\n".join(
                    f"{p['domain']} — {p['name']}: {p['about']}" for p in portals)
            # pre-retrieval: every model gets the best excerpts, also one that never calls tools
            last = next((m["text"] for m in reversed(history) if m["role"] == "user"), "")
            t = time.perf_counter()
            hits = self._library_search(last, cc, lang, PRE_HITS, found)
            timing["library_ms"] = _ms(t)
            log.info("chat timing: case=%s phase=library ms=%d hits=%d", case_id, timing["library_ms"], len(hits))
            system += ("\n\nOfficial library excerpts for the last message (may be off-topic; cite what you use):\n"
                       + json.dumps(hits, ensure_ascii=False) if hits else
                       "\n\nThe official library found nothing for the last message as written; if it is about a "
                       "state service, try official_sources with other key words.")
        system += "\n\nCase context (names and numbers are replaced by placeholders):\n" + case_note
        tools = self.tools(use_portal, use_library)
        # the prompt's size drives the model's time to the first token (about 4 characters a token)
        timing["system_chars"] = len(system)
        timing["prompt_chars"] = len(system) + len(json.dumps(tools, ensure_ascii=False)) + sum(
            len(m["content"]) for m in messages if isinstance(m["content"], str))
        timing["setup_ms"] = _ms(t0)
        usage = {"input_tokens": 0, "output_tokens": 0}
        text_parts: list[str] = []
        calls = 0
        served = ""  # the provider of a chain that answered keeps the rest of the turn (its own tool calls)
        for n in range(self.max_turns):
            t_round = time.perf_counter()
            first_ms = None
            kw: dict[str, Any] = {"prefer": served} if served and getattr(self.client, "accepts_prefer", False) else {}
            with self.client.messages.stream(model=self.model, max_tokens=self.max_tokens, system=system,
                                             tools=tools, messages=messages, **kw) as s:
                for chunk in s.text_stream:
                    chunk = strip_foreign_script(chunk, language)
                    if not chunk:
                        continue
                    if first_ms is None:
                        first_ms = _ms(t_round)
                        if "ttft_ms" not in timing:
                            timing["ttft_ms"] = _ms(t0)
                            log.info("chat timing: case=%s phase=first_token ms=%d round=%d", case_id,
                                     timing["ttft_ms"], n + 1)
                    text_parts.append(chunk)
                    yield {"type": "text", "text": chunk}
                final = s.get_final_message()
            served = getattr(s, "provider", "") or served
            rnd: dict[str, Any] = {"n": n + 1, "provider": getattr(s, "provider", "") or getattr(self.client, "name", ""),
                                   "first_ms": first_ms, "ms": _ms(t_round), "stop": final.stop_reason}
            if attempts := getattr(s, "attempts", None):
                rnd["attempts"] = attempts
            timing["rounds"].append(rnd)
            log.info("chat timing: case=%s phase=round %s", case_id, json.dumps(rnd, ensure_ascii=False))
            usage["input_tokens"] += final.usage.input_tokens
            usage["output_tokens"] += final.usage.output_tokens
            searches = getattr(getattr(final.usage, "server_tool_use", None), "web_search_requests", 0) or 0
            if searches:  # Claude's server web search is billed per search
                usage["web_search_requests"] = usage.get("web_search_requests", 0) + int(searches)
            messages.append({"role": "assistant", "content": final.content})
            if final.stop_reason == "tool_use":
                results = []
                for b in final.content:
                    if b.type == "tool_use":
                        calls += 1
                        yield {"type": "tool", "name": b.name}
                        t_tool = time.perf_counter()
                        source = "code"
                        if b.name == "official_sources" and use_library:
                            hits = self._library_search(str(dict(b.input).get("query", "")), cc, lang, TOOL_HITS,
                                                        found)
                            content = (json.dumps(hits, ensure_ascii=False) if hits else
                                       "nothing found in the official library: say so and name the portal to check")
                            source = "library"
                        else:
                            content = self._law._run_tool(b.name, dict(b.input), context, got)
                            if b.name in ("get_article", "act_contents"):
                                source = self._law.adilet.last_source()
                        tool = {"name": b.name, "ms": _ms(t_tool), "source": source}
                        timing["tools"].append(tool)
                        log.info("chat timing: case=%s phase=tool %s", case_id, json.dumps(tool))
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
                messages.append({"role": "user", "content": results})
                if text_parts and not text_parts[-1].endswith(("\n", " ")):
                    text_parts.append("\n\n")
                    yield {"type": "text", "text": "\n\n"}
                continue
            if final.stop_reason == "pause_turn":
                continue
            break
        text = "".join(text_parts).strip()
        result = self._check(text, got, calls, usage)
        result.sources = [{"url": h.url, "title": h.title, "domain": h.domain} for h in found.values()
                          if h.url in text or h.domain in text]
        timing["total_ms"] = _ms(t0)
        timing["provider"] = served or getattr(self.client, "name", "")
        result.timing = timing
        yield {"type": "done", "result": result}

    def _library_search(self, query: str, cc: str | None, lang: str | None, limit: int,
                        found: dict[str, Hit]) -> list[dict[str, str]]:
        """Excerpts of the official library for the model; never raises (the chat goes on without them)."""
        if not query.strip() or not cc:
            return []
        try:
            hits = self.library.search(query[:500], cc, lang, limit)
        except Exception:
            log.exception("official library search failed")
            return []
        for h in hits:
            found.setdefault(h.url, h)
        return [{"url": h.url, "domain": h.domain, "title": h.title, "section": h.heading, "excerpt": h.snippet}
                for h in hits]

    @staticmethod
    def _check(text: str, got: dict[tuple[str, str], Any], calls: int, usage: dict[str, int]) -> ChatResult:
        read = {num: r for (_, num), r in got.items()}
        mentioned = mentioned_articles(text)
        norms = [{"act": r.act_title, "act_code": r.code, "article": r.number, "title": r.title, "url": r.url}
                 for num, r in read.items() if num in mentioned]
        text, offer = take_offer(text)
        return ChatResult(text, norms, unchecked=bool(mentioned - set(read)), tool_calls=calls, usage=usage,
                          offer_document=offer)
