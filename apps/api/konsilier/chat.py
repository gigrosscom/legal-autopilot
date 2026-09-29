"""Free consultation chat: a fast model talks with the person, collects the facts and explains the next steps.

The chat answers in plain words and streams its reply. It may look up the official text of an article (the same
portal tools as the legal agent, konsilier/lawagent) and the registry of bodies of the country pack; it is told
never to state article numbers, deadlines, fees or addressees from memory. After the reply a check compares the
article numbers mentioned in it with the articles actually opened in this turn: anything not opened is flagged
"unchecked" in the reply's meta for metrics and logs (the person is not shown a note). Documents are prepared by the case engine (a separate,
paid step), not by the chat.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from .lawagent.agent import LawAgent
from .lawagent.sources import Adilet

log = logging.getLogger(__name__)

HISTORY_TURNS = 20  # messages sent to the model; older ones are dropped

SYSTEM = """You are Konsiliér AI, a free assistant that helps people in {country} with legal questions.
Talk like a patient, friendly consultant: short plain sentences, no legal jargon.
Language: write every sentence in {language} — also the short notes you write before or while looking something up
with a tool. Never switch to English or any other language, whatever language the tools return.

How to work
1. Understand the situation. Ask one or two short questions at a time to learn the facts that matter
   (what happened, when, how much money, which documents the person has). Do not interrogate, and do not ask for
   anything that is already in the case context or in the files the person attached.
2. Find out who the person is in the dispute: a private individual, or a business (sole trader, company). Consumer
   protection rules protect individuals who buy for personal use; a dispute between businesses follows the contract
   and the civil code. Never apply consumer protection rules to a business.
3. Explain what the person can do, step by step, and what to prepare.
4. Legal rules: never state an article number, a deadline, a fee or which body to write to from memory.
   {portal_rule}
   Bodies and courts come only from the forums tool. For any date use the deadline tool.
   If you could not check something, say so plainly instead of guessing.
5. When the person needs a written claim, complaint or lawsuit, say that Konsiliér AI can prepare it with the
   button "Prepare the document" (a paid step: one document, or the whole case).
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
   from memory — say plainly that they must be checked in the official service standard, programme rules or tender
   documents. Never promise that a benefit, a grant, a place or a tender will be won. Konsiliér AI can prepare the
   package (application, checklist, cover letter, business plan outline, inventory) with the same button. A refusal
   or a rejected bid is a dispute again: follow steps 3–5, and the body to complain to comes only from the forums
   tool.
7. Criminal defence, children's custody, large sums or missed deadlines: say plainly that this needs a lawyer.
   Never promise an outcome. Never ask about or guess religion or other sensitive traits.
8. Files the person attached are listed in the case context with any text read from them: use them.
Keep replies under about 150 words unless the person asks for detail."""

PORTAL_RULE = ("State an article number only if you opened that article's text with get_article or act_contents "
               "in this reply; otherwise name the law or code by its title without any article number. "
               "Find the act among the main acts listed below{search}.")
NO_PORTAL_RULE = ("You have no access to the official texts here, so never state article numbers: name the law or "
                  "code by its title only.")

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


def mentioned_articles(text: str) -> set[str]:
    return {m.group(1) or m.group(2) for m in ARTICLE_MENTION.finditer(text)}


class ChatAgent:
    def __init__(self, client: Any, model: str, adilet: Adilet | None = None, *,
                 portal_domain: str = "adilet.zan.kz", max_turns: int = 6, max_tokens: int = 2000,
                 web_search: bool = True):
        self.client, self.model, self.max_turns, self.max_tokens = client, model, max_turns, max_tokens
        self.portal_domain, self.web_search = portal_domain, web_search
        # the portal tools are the legal agent's; the chat reuses them rather than re-implementing
        self._law = LawAgent(client, model, adilet or Adilet(), portal_domain=portal_domain)

    def tools(self, use_portal: bool) -> list[dict[str, Any]]:
        out = []
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
        got: dict[tuple[str, str], Any] = {}
        case_note = json.dumps(context.get("case", {}), ensure_ascii=False)
        messages: list[dict[str, Any]] = [{"role": m["role"], "content": m["text"]} for m in history[-HISTORY_TURNS:]]
        if messages and messages[0]["role"] != "user":
            messages = messages[1:]
        search = " or with web_search on the official portal" if self.web_search else ""
        system = SYSTEM.format(country=country, language=language,
                               portal_rule=PORTAL_RULE.format(search=search) if use_portal else NO_PORTAL_RULE)
        if use_portal and context.get("key_acts"):
            system += "\n\nMain acts on the official portal (code — title):\n" + "\n".join(
                f"{a['code']} — {a['title']}" for a in context["key_acts"])
        system += "\n\nCase context (names and numbers are replaced by placeholders):\n" + case_note
        usage = {"input_tokens": 0, "output_tokens": 0}
        text_parts: list[str] = []
        calls = 0
        for _ in range(self.max_turns):
            with self.client.messages.stream(model=self.model, max_tokens=self.max_tokens, system=system,
                                             tools=self.tools(use_portal), messages=messages) as s:
                for chunk in s.text_stream:
                    text_parts.append(chunk)
                    yield {"type": "text", "text": chunk}
                final = s.get_final_message()
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
                        results.append({"type": "tool_result", "tool_use_id": b.id,
                                        "content": self._law._run_tool(b.name, dict(b.input), context, got)})
                messages.append({"role": "user", "content": results})
                if text_parts and not text_parts[-1].endswith(("\n", " ")):
                    text_parts.append("\n\n")
                    yield {"type": "text", "text": "\n\n"}
                continue
            if final.stop_reason == "pause_turn":
                continue
            break
        text = "".join(text_parts).strip()
        yield {"type": "done", "result": self._check(text, got, calls, usage)}

    @staticmethod
    def _check(text: str, got: dict[tuple[str, str], Any], calls: int, usage: dict[str, int]) -> ChatResult:
        read = {num: r for (_, num), r in got.items()}
        mentioned = mentioned_articles(text)
        norms = [{"act": r.act_title, "act_code": r.code, "article": r.number, "title": r.title, "url": r.url}
                 for num, r in read.items() if num in mentioned]
        return ChatResult(text, norms, unchecked=bool(mentioned - set(read)), tool_calls=calls, usage=usage)
