"""Legal research ("правовая справка") over the official legislation portals, live, with verified quotes.

The case description (PII-redacted) goes to Claude with web search and web fetch restricted to the country
pack's official legal sources (`legal_sources` in pack.yaml, e.g. adilet.zan.kz). Claude returns the norms
that may apply: act, article, a verbatim quote and the URL it read. We keep a norm only if its URL is on an
allowed domain AND its quote is actually found in the text Claude fetched in this very request — so an
invented article or a paraphrase presented as a quote never reaches the client.

We do not copy the portals' databases: each справка reads only the pages it needs, and links back to them.
The result is information for the client and the lawyer ("проверит юрист"); it is never inserted into
documents automatically.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

log = logging.getLogger(__name__)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["norms", "summary"],
    "properties": {
        "summary": {"type": "string"},
        "norms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["act", "article", "quote", "url", "why"],
                "properties": {
                    "act": {"type": "string"},
                    "article": {"type": "string"},
                    "quote": {"type": "string"},
                    "url": {"type": "string"},
                    "why": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM = """You are a legal researcher for a legal-help platform. Find the norms of the given country's law that
may apply to the client's situation, using ONLY the web_search and web_fetch tools (they are restricted to the
official legislation portals). Rules:
- Codes are very long. Always call web_search and web_fetch from inside code execution and print only the
  articles you need (find them by "Статья N" / "N-бап" headings); never read a whole act into the conversation.
- Open the official text of every act you cite with web_fetch and read the article there.
- "quote" must be copied verbatim from the fetched text (one to three sentences of the article, no ellipses,
  no paraphrase). "url" must be the exact URL you fetched.
- Prefer the current version of the act; mention if it is marked as expired.
- 3 to 8 norms, most important first: the rights and duties, deadlines, and where to complain.
- "article" like "Статья 113" (or the Kazakh/English equivalent), "act" is the full act title with date and number.
- "why" and "summary": short, plain, in the language requested, no legal advice beyond what the norms say.
If you cannot find a norm in the official text, leave it out rather than guess."""


@dataclass
class Fetched:
    url: str
    text: str


@dataclass
class RawResearch:
    answer: dict[str, Any]
    fetched: list[Fetched] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""


class Researcher(Protocol):
    def research(self, *, system: str, user: str, domains: list[str]) -> RawResearch: ...


class AnthropicResearcher:
    def __init__(self, model: str, api_key: str | None = None, max_uses: int = 6):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model, self.max_uses = model, max_uses

    def research(self, *, system: str, user: str, domains: list[str]) -> RawResearch:
        tools = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": self.max_uses, "allowed_domains": domains},
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": self.max_uses, "allowed_domains": domains},
        ]
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        content: list[Any] = []
        usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
        for _ in range(4):  # server tools may pause a long turn: continue it
            with self.client.messages.stream(
                model=self.model, max_tokens=32000, system=system, tools=tools, messages=messages,
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            ) as stream:
                response = stream.get_final_message()
            content.extend(response.content)
            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens
            if response.stop_reason != "pause_turn":
                break
            messages = [{"role": "user", "content": user}, {"role": "assistant", "content": response.content}]
        if response.stop_reason == "refusal":
            raise RuntimeError("research refused")
        fetched = []
        for b in content:
            if b.type == "web_fetch_tool_result":
                doc = getattr(b.content, "content", None)
                src = getattr(doc, "source", None)
                text = getattr(src, "data", None)
                url = getattr(b.content, "url", None)
                if isinstance(text, str) and url:
                    fetched.append(Fetched(url=url, text=text))
        text = next((b.text for b in reversed(content) if b.type == "text" and b.text.strip().startswith("{")), None)
        if text is None:
            raise RuntimeError("no JSON answer")
        return RawResearch(answer=json.loads(text), fetched=fetched, usage=usage, model=self.model)


# ------------------------------------------------------------------ verification
_WS = re.compile(r"\s+")
_MARKUP = re.compile(r"[*_`#>\[\]«»\"“”„]")


def _norm(s: str) -> str:
    return _WS.sub(" ", _MARKUP.sub("", s or "")).strip().lower()


def _host_ok(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def verify(raw: RawResearch, domains: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Keep norms whose URL is on an allowed domain and whose quote occurs in text fetched in this request."""
    texts = [(f.url, _norm(f.text)) for f in raw.fetched if _host_ok(f.url, domains)]
    kept, dropped = [], 0
    for n in raw.answer.get("norms", []):
        quote = _norm(n.get("quote", ""))
        ok = len(quote) >= 25 and _host_ok(n.get("url", ""), domains) and any(quote in t for _, t in texts)
        if ok:
            kept.append({k: (n.get(k) or "").strip() for k in ("act", "article", "quote", "url", "why")})
        else:
            dropped += 1
    return kept, dropped


def allowed_domains(pack: Any) -> list[str]:
    out = []
    for s in pack.manifest.legal_sources:
        if s.kind in ("legislation", "gazette", "registry", "case_law"):
            host = (urlparse(str(s.url)).hostname or "").lower()
            if host and host not in out:
                out.append(host.removeprefix("www."))
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
