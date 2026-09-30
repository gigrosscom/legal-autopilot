"""Free, live access to the official legislation portal: open an act, take one article.

The agent never gets whole codes. When it needs an article, our server opens the act's official page (like a
browser would), cuts out that one article and hands it over with the page URL. Nothing is copied into a
database; a short in-memory cache (per process, hours) only avoids re-opening the same page within a session.

The portal: ИПС «Әділет» of the Ministry of Justice (adilet.zan.kz) — free, public, current wording. Its new
site renders text with JavaScript, so the server-rendered mirror old.adilet.zan.kz is read. Document codes
look like K1500000414 (Labour Code) or Z100000274 (a law); the language segment is rus or kaz.
"""

from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol

import httpx

CODE_RE = re.compile(r"^[A-Z]\d{9,10}_?$")
URL_CODE_RE = re.compile(r"/docs/([A-Z]\d{9,10}_?)")
# "Статья 113. Порядок…", "Статья 113-1. …", "113-бап. …" (kk), with optional markdown bold
ARTICLE_RE = re.compile(r"^\**\s*(?:Статья\s+(\d+(?:-\d+)?)\.|(\d+(?:-\d+)?)-бап\.)\s*(.*?)\**\s*$")


class ActNotFound(Exception):
    pass


@dataclass(frozen=True)
class Article:
    act_code: str
    act_title: str
    number: str
    title: str
    text: str
    url: str


def act_code(ref: str) -> str:
    """Accept a code or any adilet URL; return the document code."""
    ref = ref.strip()
    m = URL_CODE_RE.search(ref)
    code = m.group(1) if m else ref
    if not CODE_RE.match(code):
        raise ActNotFound(ref)
    return code


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "article", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def page_text(raw: str) -> tuple[str, str]:
    """(title, text) from the portal page: HTML, or the markdown-ish text some fetchers return."""
    if "<html" in raw[:2000].lower() or "<body" in raw.lower():
        p = _Text()
        p.feed(raw)
        text, title = "".join(p.parts), p.title
    else:
        text = raw
        m = re.search(r"^title:\s*(.+)$", raw, re.M)
        title = m.group(1) if m else ""
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    title = re.sub(r"\s*-\s*ИПС.*$", "", html.unescape(title)).strip()
    return title, text


def split_articles(text: str) -> dict[str, tuple[str, str]]:
    """number → (title, body). A body runs until the next article or chapter heading."""
    out: dict[str, tuple[str, str]] = {}
    current: str | None = None
    title, body = "", []
    for line in text.splitlines():
        s = line.strip()
        m = ARTICLE_RE.match(s)
        heading = bool(m) or bool(re.match(r"^\**\s*(Глава|Раздел|ГЛАВА|РАЗДЕЛ|\d+-тарау|\d+-бөлім)\b", s))
        if heading and current is not None:
            out.setdefault(current, (title, "\n".join(body).strip()))
            current = None
        if m:
            current, title, body = (m.group(1) or m.group(2)), m.group(3).strip(" *"), []
        elif current is not None:
            body.append(line)
    if current is not None:
        out.setdefault(current, (title, "\n".join(body).strip()))
    return out


class Fetch(Protocol):
    def __call__(self, url: str) -> str: ...


def http_fetch(url: str, timeout: float = 25) -> str:
    r = httpx.get(url, timeout=timeout, follow_redirects=True,
                  headers={"User-Agent": "Konsilier.AI legal research (+https://konsilier.com)"})
    if r.status_code == 404:
        raise ActNotFound(url)
    r.raise_for_status()
    return r.text


def quick_fetch(url: str) -> str:
    """For the chat: the person waits for the reply, so a slow portal page is given up after 8 s (the model then
    says the article could not be checked) instead of holding the answer for up to 25 s."""
    return http_fetch(url, timeout=8)


class Adilet:
    BASE = "https://old.adilet.zan.kz"

    def __init__(self, fetch: Fetch = http_fetch, ttl_seconds: int = 6 * 3600, max_acts: int = 16):
        self.fetch, self.ttl, self.max_acts = fetch, ttl_seconds, max_acts
        self._cache: dict[str, tuple[float, str, dict[str, tuple[str, str]]]] = {}
        self._lock = threading.Lock()

    def url(self, code: str, lang: str = "rus") -> str:
        return f"{self.BASE}/{lang}/docs/{code}"

    def _act(self, code: str, lang: str) -> tuple[str, dict[str, tuple[str, str]]]:
        key = f"{lang}:{code}"
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < self.ttl:
                return hit[1], hit[2]
        title, text = page_text(self.fetch(self.url(code, lang)))
        articles = split_articles(text)
        if not articles:
            raise ActNotFound(code)
        with self._lock:
            if len(self._cache) >= self.max_acts:  # keep memory small: drop the oldest page
                self._cache.pop(min(self._cache, key=lambda k: self._cache[k][0]))
            self._cache[key] = (time.time(), title, articles)
        return title, articles

    def article(self, ref: str, number: str, lang: str = "rus") -> Article:
        code = act_code(ref)
        title, articles = self._act(code, lang)
        num = re.sub(r"[^\d-]", "", number.replace("–", "-"))
        if num not in articles:
            raise ActNotFound(f"{code} article {number}")
        a_title, body = articles[num]
        return Article(code, title, num, a_title, body[:12000], self.url(code, lang))

    def contents(self, ref: str, lang: str = "rus", limit: int = 400) -> tuple[str, list[tuple[str, str]]]:
        """Act title and its article list (number, title): what the agent uses to pick the right article."""
        code = act_code(ref)
        title, articles = self._act(code, lang)
        return title, [(n, t) for n, (t, _) in list(articles.items())[:limit]]
