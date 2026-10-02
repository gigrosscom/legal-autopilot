"""The legal agent: a client's question → Claude picks what to look up → tools → answer where every norm is
backed by an article it actually read → automatic check → anything unconfirmed becomes "уточнит юрист".

Tools
- web_search (Anthropic server tool, restricted to the official portal): find which act governs the question.
- act_contents(act): the act's article list (numbers and titles) — to pick the right article.
- get_article(act, article): the text of one article from the official page, with its URL.
- forums(): bodies/courts from the country pack's registry that accept this kind of case.
- deadline(start, calendar_days | business_days): date arithmetic done by code with the pack's calendar.

Deadlines, bodies and fees are never invented: they come from articles the agent read, from the registry,
or are computed by `deadline`. The check after the answer drops any norm whose article was not retrieved in
this run or whose quote is not in the article text, and marks the answer for a lawyer.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .sources import Adilet, ActNotFound

log = logging.getLogger(__name__)

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["answer", "steps", "norms", "confidence"],
    "properties": {
        "answer": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "norms": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["act_code", "article", "quote"],
            "properties": {"act_code": {"type": "string"}, "article": {"type": "string"}, "quote": {"type": "string"}},
        }},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}

from ..core.legal_method import LEGAL_METHOD  # noqa: E402

SYSTEM = """You answer legal questions of people in {country} for Konsilier, an AI assistant for legal matters.
Work only from the official texts you open with the tools; never answer a legal rule from memory.
1. Find the governing act(s): web_search on the official portal (document pages look like /rus/docs/K1500000414).
2. act_contents to see the articles, then get_article for each article you rely on. Read before you cite.
3. For bodies/courts use forums(); for any date use deadline(); do not compute dates yourself.
4. Answer in {language}, plainly, 3–6 sentences, then concrete next steps. Every legal statement must rest on
   an article in "norms" with a verbatim quote (one or two sentences) copied from get_article output.
5. If the question needs a lawyer (criminal defence, children, large sums, missed deadlines) or the texts do not
   settle it, say so and set confidence "low". Do not give guarantees about outcomes.
""" + LEGAL_METHOD


@dataclass
class Retrieved:
    code: str
    number: str
    title: str
    text: str
    url: str
    act_title: str


@dataclass
class AgentResult:
    answer: str
    steps: list[str]
    norms: list[dict[str, str]]
    unverified: int
    needs_lawyer: bool
    confidence: str
    tool_calls: int
    usage: dict[str, int] = field(default_factory=dict)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_`«»\"“”„]", "", s or "")).strip().lower()


class LawAgent:
    def __init__(self, client: Any, model: str, adilet: Adilet, *, portal_domain: str = "adilet.zan.kz",
                 max_turns: int = 12):
        self.client, self.model, self.adilet = client, model, adilet
        self.portal_domain, self.max_turns = portal_domain, max_turns

    def tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": 4,
             "allowed_domains": [self.portal_domain]},
            {"name": "act_contents", "description": "List the articles (number and title) of an act on the official portal.",
             "input_schema": {"type": "object", "additionalProperties": False, "required": ["act"],
                              "properties": {"act": {"type": "string", "description": "Document code like K1500000414 or its URL"}}}},
            {"name": "get_article", "description": "Official text of one article of an act, with the page URL.",
             "input_schema": {"type": "object", "additionalProperties": False, "required": ["act", "article"],
                              "properties": {"act": {"type": "string"}, "article": {"type": "string", "description": "e.g. 113 or 113-1"}}}},
            {"name": "forums", "description": "Courts and bodies from the platform's verified registry for this case.",
             "input_schema": {"type": "object", "additionalProperties": False, "properties": {}}},
            {"name": "deadline", "description": "Date that falls N calendar or business days after a start date (country calendar).",
             "input_schema": {"type": "object", "additionalProperties": False, "required": ["start"],
                              "properties": {"start": {"type": "string", "description": "YYYY-MM-DD"},
                                             "calendar_days": {"type": "integer"}, "business_days": {"type": "integer"}}}},
        ]

    # ---------------------------------------------------------------- tool execution
    def _run_tool(self, name: str, args: dict[str, Any], ctx: dict[str, Any], got: dict[tuple[str, str], Retrieved]) -> str:
        try:
            if name == "act_contents":
                title, items = self.adilet.contents(args["act"])
                return json.dumps({"act": title, "articles": [f"{n}. {t}" for n, t in items]}, ensure_ascii=False)
            if name == "get_article":
                a = self.adilet.article(args["act"], str(args["article"]))
                got[(a.act_code, a.number)] = Retrieved(a.act_code, a.number, a.title, a.text, a.url, a.act_title)
                return json.dumps({"act": a.act_title, "act_code": a.act_code, "article": a.number, "title": a.title,
                                   "url": a.url, "text": a.text}, ensure_ascii=False)
            if name == "forums":
                return json.dumps(ctx.get("forums", []), ensure_ascii=False)
            if name == "deadline":
                start = date.fromisoformat(args["start"])
                cal, bus = args.get("calendar_days"), args.get("business_days")
                if (cal is None) == (bus is None):
                    return "error: give exactly one of calendar_days or business_days"
                return ctx["pack"].add_days(start, cal, bus).isoformat()
        except (ActNotFound, KeyError, ValueError) as e:
            return f"error: not found ({e})"
        except Exception as e:  # network trouble etc.: tell the model, do not crash the run
            log.warning("tool %s failed: %s", name, e)
            return "error: the official portal did not answer; try again or say the norm must be checked by a lawyer"
        return f"error: unknown tool {name}"

    # ---------------------------------------------------------------- the loop
    def ask(self, question: str, *, context: dict[str, Any], language: str, country: str) -> AgentResult:
        got: dict[tuple[str, str], Retrieved] = {}
        messages: list[dict[str, Any]] = [{"role": "user", "content": json.dumps(
            {"question": question, "case": context.get("case", {})}, ensure_ascii=False)}]
        usage = {"input_tokens": 0, "output_tokens": 0}
        calls = 0
        final = None
        for _ in range(self.max_turns):
            response = self.client.messages.create(
                model=self.model, max_tokens=16000,
                system=SYSTEM.format(country=country, language=language),
                tools=self.tools(), messages=messages,
                output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}, "effort": "medium"},
            )
            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "tool_use":
                results = []
                for b in response.content:
                    if b.type == "tool_use":
                        calls += 1
                        results.append({"type": "tool_result", "tool_use_id": b.id,
                                        "content": self._run_tool(b.name, dict(b.input), context, got)})
                messages.append({"role": "user", "content": results})
                continue
            if response.stop_reason == "pause_turn":
                continue
            final = next((b.text for b in reversed(response.content) if b.type == "text"), None)
            break
        if not final:
            return AgentResult("", [], [], 0, True, "low", calls, usage)
        data = json.loads(final)
        return self._verify(data, got, calls, usage)

    def _verify(self, data: dict[str, Any], got: dict[tuple[str, str], Retrieved], calls: int,
                usage: dict[str, int]) -> AgentResult:
        norms, unverified = [], 0
        for n in data.get("norms", []):
            try:
                key = (_code(n["act_code"]), re.sub(r"[^\d-]", "", n["article"]))
            except ActNotFound:
                unverified += 1
                continue
            r = got.get(key)
            q = _norm(n.get("quote", ""))
            if r and len(q) >= 20 and q in _norm(r.text):
                norms.append({"act": r.act_title, "act_code": r.code, "article": r.number, "title": r.title,
                              "quote": n["quote"].strip(), "url": r.url})
            else:
                unverified += 1
        needs_lawyer = unverified > 0 or not norms or data.get("confidence") == "low"
        return AgentResult(data.get("answer", ""), list(data.get("steps", [])), norms, unverified, needs_lawyer,
                           data.get("confidence", "low"), calls, usage)


def _code(ref: str) -> str:
    from .sources import act_code

    return act_code(ref)
