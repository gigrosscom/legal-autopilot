"""The nightly crawler of the official library: fetch → extract the main text → store changed pages as chunks.

Polite by construction: only the domains the country pack allows (packs/<cc>/sources/official.yaml), robots.txt
obeyed (wildcards and ``$`` included; a robots.txt that cannot be read closes the site for the run), a clear
User-Agent, one request per second per domain (longer if robots.txt asks), HTML only. Conditional GET (ETag /
If-Modified-Since) and a hash of the extracted text make an unchanged page cost one small request and no writes.

Resumable: pages found are stored at once as ``pending``; each run takes pending pages first, then the ones fetched
longest ago, skipping those refreshed within ``fresh_hours``. A time-boxed run that stops half way is continued by
the next one. Nothing here runs during a conversation: the chat only reads the stored chunks (search.py).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import OfficialChunk, OfficialPage
from .config import OfficialSources

log = logging.getLogger(__name__)

USER_AGENT = "KonsilierBot/1.0 (+https://konsilier.com)"
ROBOTS_TOKEN = "konsilierbot"
TIMEOUT = 25  # seconds, as the portal tools of the legal agent
MAX_BYTES = 3_000_000
MIN_TEXT = 200  # characters of main text below which a page is not worth keeping (script-only pages, menus)
CHUNK_CHARS = 1500
BINARY_EXT = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|7z|gz|jpe?g|png|gif|webp|svg|ico|mp[34]|avi|mov|"
                        r"exe|apk|xml|json|css|js|woff2?|ttf)$", re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d  # SQLite drops the zone


# ---------------------------------------------------------------------------------------------------- robots.txt
@dataclass
class Robots:
    """Rules of one robots.txt for our user agent: the group naming us, else the ``*`` group."""
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float = 0.0
    disallow_all: bool = False

    @classmethod
    def parse(cls, text: str, token: str = ROBOTS_TOKEN) -> "Robots":
        groups: list[tuple[list[str], list[tuple[bool, str]], float]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        delay = 0.0
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (s.strip() for s in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if in_rules:  # a new group starts
                    groups.append((agents, rules, delay))
                    agents, rules, delay, in_rules = [], [], 0.0, False
                agents.append(value.lower())
            elif key in ("allow", "disallow"):
                in_rules = True
                if value:
                    rules.append((key == "allow", value))
            elif key == "crawl-delay":
                in_rules = True
                try:
                    delay = float(value)
                except ValueError:
                    pass
        if agents:
            groups.append((agents, rules, delay))
        mine = [g for g in groups if any(a != "*" and a in token for a in g[0])]
        chosen = mine or [g for g in groups if "*" in g[0]]
        out = cls()
        for _, r, d in chosen:
            out.rules += r
            out.crawl_delay = max(out.crawl_delay, d)
        return out

    @staticmethod
    def _match(pattern: str, path: str) -> int:
        """Length of the pattern when it matches the start of ``path`` (``*`` any run, ``$`` end), else -1."""
        rx = "".join(".*" if ch == "*" else ("$" if ch == "$" and i == len(pattern) - 1 else re.escape(ch))
                     for i, ch in enumerate(pattern))
        return len(pattern) if re.match(rx, path) else -1

    def allowed(self, url: str) -> bool:
        if self.disallow_all:
            return False
        p = urlsplit(url)
        path = (p.path or "/") + (f"?{p.query}" if p.query else "")
        best, verdict = -1, True
        for allow, pattern in self.rules:
            n = self._match(pattern, path)
            if n > best or (n == best and n >= 0 and allow):
                best, verdict = n, allow
        return verdict


# ---------------------------------------------------------------------------------------------------- extraction
@dataclass
class Section:
    heading: str
    text: str


@dataclass
class Extracted:
    title: str
    lang: str
    text: str
    sections: list[Section]
    links: list[str]


SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "aside", "form", "button", "select", "iframe",
             "template", "dialog", "canvas", "object", "video", "audio", "map"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track",
             "wbr"}
BLOCK_TAGS = {"p", "div", "li", "tr", "td", "th", "table", "ul", "ol", "dl", "dt", "dd", "section", "article", "main",
              "blockquote", "pre", "br", "hr", "header", "figcaption", "summary", "details"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
# class / id / role of site chrome: menus, breadcrumbs, cookie banners, share buttons, footers
CHROME = re.compile(r"(^|[\s_-])(nav|navbar|navigation|menu|mainmenu|topmenu|submenu|footer|breadcrumbs?|sidebar|"
                    r"cookies?|share|social|modal|popup|search|pagination|banner)([\s_-]|$)", re.I)
MAIN = re.compile(r"(^|[\s_-])(content|main|article)([\s_-]|$)", re.I)
# service cards embedded as JSON in the text of some portals: {"id": 1, "title": "…", "service_link": "…"}
JSON_CARD = re.compile(r"\{[^{}]{0,1200}?\"title\"\s*:\s*\"([^\"]+)\"[^{}]{0,1200}?\}")
KK_LETTERS = set("әғқңөұүһі")


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []  # (tag, skip, main)
        self.blocks: list[tuple[int, str, bool]] = []  # (heading level or 0, text, inside main content)
        self.links: list[str] = []
        self.title = ""
        self._buf: list[str] = []
        self._level = 0
        self._in_title = False

    @property
    def _skip(self) -> bool:
        return any(s for _, s, _ in self.stack)

    @property
    def _main(self) -> bool:
        return any(m for _, _, m in self.stack)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            self.blocks.append((self._level, text, self._main))
        self._buf, self._level = [], 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "title":
            self._in_title = True
        if tag in ("a", "label") and not self._skip:  # adjacent inline items must not run together
            self._buf.append(" ")
        if tag in BLOCK_TAGS or tag in HEADINGS:
            self._flush()
        if tag in HEADINGS and not self._skip:
            self._level = HEADINGS[tag]
        if tag in VOID_TAGS:
            return
        marks = f"{a.get('class', '')} {a.get('id', '')} {a.get('role', '')}"
        skip = (tag in SKIP_TAGS or (tag == "header" and not self._main) or a.get("aria-hidden") == "true"
                or "hidden" in a or bool(CHROME.search(marks)) and tag not in ("body", "html", "main", "article"))
        main = tag in ("main", "article") or a.get("role") == "main" or (tag == "div" and bool(MAIN.search(a.get("id", ""))))
        self.stack.append((tag, skip, main))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in ("a", "label") and not self._skip:
            self._buf.append(" ")
        if tag in BLOCK_TAGS or tag in HEADINGS:
            self._flush()
        if tag in VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, -1, -1):  # close up to the matching tag (tolerates unclosed children)
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._buf.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def detect_lang(url: str, text: str, default: str = "ru") -> str:
    """Language code from the address (``?lang=kk``, ``/kk/``, ``/kaz/``, ``/ru/``, ``/rus/``, ``/en/``) or else from the
    letters of the text (letters that Russian lacks)."""
    p = urlsplit(url)
    m = re.search(r"(?:^|&)lang=([a-z]{2})", p.query) or re.match(r"^/([a-z]{2,3})(?:/|$)", p.path)
    if m:
        code = {"rus": "ru", "kaz": "kk", "eng": "en"}.get(m.group(1), m.group(1))
        if code in ("ru", "kk", "en"):
            return code
    letters = [c for c in text.lower()[:5000] if c.isalpha()]
    if not letters:
        return default
    if sum(c in KK_LETTERS for c in letters) / len(letters) > 0.01:
        return "kk"
    cyr = sum("а" <= c <= "я" or c == "ё" for c in letters)
    return "ru" if cyr > len(letters) / 3 else ("en" if cyr == 0 else default)


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    for sep in (" | ", " — ", " - "):
        head = title.split(sep)[0].strip()
        if len(head) >= 8:
            title = head
    return title[:500]


def _chunks(heading: str, paragraphs: list[str]) -> list[Section]:
    out: list[Section] = []
    buf: list[str] = []
    size = 0
    for p in paragraphs:
        if buf and size + len(p) > CHUNK_CHARS:
            out.append(Section(heading, "\n".join(buf)))
            buf, size = [], 0
        while len(p) > CHUNK_CHARS:  # one huge paragraph: cut at a sentence end
            cut = p.rfind(". ", 0, CHUNK_CHARS)
            cut = cut + 1 if cut > CHUNK_CHARS // 3 else CHUNK_CHARS
            out.append(Section(heading, p[:cut].strip()))
            p = p[cut:].strip()
        buf.append(p)
        size += len(p)
    if buf:
        out.append(Section(heading, "\n".join(buf)))
    return out


def extract(html: str, url: str, default_lang: str = "ru", drop: tuple[str, ...] = ()) -> Extracted:
    """Title, language, main text split by headings, and the links of an HTML page. Menus, footers, scripts, cookie
    banners and other site chrome are dropped; when the page marks its main content (<main>, <article>,
    role=main) and it holds enough text, only that is kept. ``drop``: regexes of a site's own boilerplate lines."""
    p = _Page()
    p.feed(html)
    p.close()
    blocks = [(lvl, JSON_CARD.sub(lambda m: f"«{m.group(1)}»", t), inside) for lvl, t, inside in p.blocks
              if not any(re.search(rx, t) for rx in drop)]
    main = [b for b in blocks if b[2]]
    if sum(len(t) for _, t, _ in main) >= MIN_TEXT:
        blocks = main
    title = _clean_title(p.title) or next((t for lvl, t, _ in blocks if lvl == 1), "")
    sections: list[Section] = []
    heading, paragraphs = "", []
    seen: set[str] = set()
    for lvl, t, _ in blocks:
        if lvl:
            sections += _chunks(heading, paragraphs)
            heading, paragraphs = t[:500], []
            continue
        if t in seen and len(t) < 200:  # repeated short lines: tabs, "read more", duplicated menus
            continue
        seen.add(t)
        paragraphs.append(t)
    sections += _chunks(heading, paragraphs)
    sections = [s for s in sections if len(s.text) >= 40 or s.heading]
    text = "\n\n".join((f"{s.heading}\n{s.text}" if s.heading else s.text) for s in sections)
    return Extracted(title, detect_lang(url, text, default_lang), text, sections, p.links)


# ---------------------------------------------------------------------------------------------------- the run
@dataclass
class Stats:
    fetched: int = 0
    changed: int = 0  # new text stored (first fetch included)
    unchanged: int = 0  # 304, or the same text hash
    found: int = 0  # new pages queued from links
    skipped: int = 0  # robots.txt, not HTML, too little text, off-domain redirect
    errors: int = 0


@dataclass
class _Fetched:
    status_code: int
    url: str
    text: str = ""
    etag: str | None = None
    last_modified: str | None = None
    content_type: str = ""


class Crawler:
    def __init__(self, session_factory: sessionmaker[Session], sources: OfficialSources, *,
                 http: httpx.Client | None = None, delay: float = 1.0, fresh_hours: float = 20,
                 max_pages: int | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.session_factory, self.sources = session_factory, sources
        self.http = http or httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                                         headers={"User-Agent": USER_AGENT})
        self.delay, self.fresh_hours, self.max_pages = delay, fresh_hours, max_pages
        self.sleep, self.clock = sleep, clock
        self._robots: dict[str, Robots] = {}
        self._next: dict[str, float] = {}  # domain → earliest time of the next request

    # ---- HTTP, one request per domain per `delay` seconds
    def _wait(self, domain: str) -> None:
        now = self.clock()
        at = self._next.get(domain, now)
        if at > now:
            self.sleep(at - now)
        robots = self._robots.get(domain)
        self._next[domain] = self.clock() + max(self.delay, min(robots.crawl_delay if robots else 0, 10))

    def robots(self, domain: str) -> Robots:
        if domain not in self._robots:
            self._wait(domain)
            try:
                r = self.http.get(f"https://{domain}/robots.txt")
                if r.status_code >= 500:
                    rules = Robots(disallow_all=True)  # the site is struggling: leave it alone this run
                elif r.status_code >= 400 or "html" in r.headers.get("content-type", ""):
                    rules = Robots()  # no robots.txt: everything allowed
                else:
                    rules = Robots.parse(r.text)
            except httpx.HTTPError as e:
                log.warning("official: robots.txt of %s unreadable: %s", domain, e)
                rules = Robots(disallow_all=True)
            self._robots[domain] = rules
        return self._robots[domain]

    def fetch(self, url: str, etag: str | None = None, last_modified: str | None = None) -> _Fetched:
        domain = urlsplit(url).hostname or ""
        headers = {"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        self._wait(domain)
        with self.http.stream("GET", url, headers=headers) as r:
            ctype = r.headers.get("content-type", "")
            out = _Fetched(r.status_code, str(r.url), etag=r.headers.get("etag"),
                           last_modified=r.headers.get("last-modified"), content_type=ctype)
            if r.status_code == 200 and "html" in ctype.lower():
                body = b""
                for part in r.iter_bytes():
                    body += part
                    if len(body) > MAX_BYTES:
                        break
                out.text = body.decode(r.encoding or "utf-8", errors="replace")
        return out

    def _cap(self, d: Any) -> int:
        cap = self.sources.cap(d)
        return min(cap, self.max_pages) if self.max_pages else cap

    # ---- storing
    def _queue_links(self, s: Session, page: OfficialPage, ext: Extracted, raw: str, counts: Counter,
                     stats: Stats) -> list[OfficialPage]:
        if page.depth >= self.sources.max_depth:
            return []
        d = self.sources.domain_of(page.url)
        found = list(ext.links)
        for lp in (d.link_patterns if d else ()):
            for m in re.finditer(lp.match, raw):
                found.append(lp.url.format(m.group(0), *m.groups()))
        new: list[OfficialPage] = []
        seen: set[str] = set()
        for href in found:
            url = self.sources.normalize(href, base=page.url)
            if not url or url in seen or BINARY_EXT.search(urlsplit(url).path) or not self.sources.follow(url):
                continue
            seen.add(url)
            nd = self.sources.domain_of(url)
            assert nd is not None
            if counts[nd.domain] >= self._cap(nd):
                continue
            if s.scalar(select(OfficialPage.id).where(OfficialPage.url == url)) is not None:
                continue
            if not self.robots(nd.domain).allowed(url):
                continue
            row = OfficialPage(country=self.sources.country, url=url, domain=nd.domain, topic=page.topic,
                               depth=page.depth + 1, status="pending")
            s.add(row)
            counts[nd.domain] += 1
            stats.found += 1
            new.append(row)
        return new

    def _store(self, s: Session, page: OfficialPage, ext: Extracted, now: datetime) -> bool:
        """Save the text and chunks if the text changed; True when it did."""
        digest = hashlib.sha256(ext.text.encode("utf-8")).hexdigest()
        page.title, page.lang, page.status, page.error = ext.title or page.title, ext.lang, "ok", None
        if digest == page.content_hash:
            return False
        page.text, page.content_hash, page.changed_at = ext.text, digest, now
        s.execute(delete(OfficialChunk).where(OfficialChunk.page_id == page.id))
        for i, sec in enumerate(ext.sections):
            s.add(OfficialChunk(page_id=page.id, country=page.country, lang=ext.lang, ord=i,
                                heading=sec.heading or None, text=sec.text))
        return True

    def _process(self, s: Session, page: OfficialPage, counts: Counter, stats: Stats) -> list[OfficialPage]:
        now = utcnow()
        d = self.sources.domain_of(page.url)
        if d is None:  # the allow-list changed since the page was found
            page.status, page.error, page.fetched_at = "skipped", "domain not allowed", now
            stats.skipped += 1
            return []
        if not self.robots(d.domain).allowed(page.url):
            page.status, page.error, page.fetched_at = "skipped", "robots.txt", now
            stats.skipped += 1
            return []
        try:
            r = self.fetch(page.url, page.etag, page.last_modified)
        except httpx.HTTPError as e:
            page.error, page.fetched_at = f"{type(e).__name__}: {e}"[:500], now
            page.status = "ok" if page.status == "ok" else "error"  # a passing outage keeps the page searchable
            stats.errors += 1
            return []
        stats.fetched += 1
        page.fetched_at = now
        if r.status_code == 304:  # as it was: status, text and chunks stay
            stats.unchanged += 1
            return []
        if r.status_code in (404, 410):
            page.status, page.error, page.content_hash, page.etag = "gone", f"HTTP {r.status_code}", None, None
            s.execute(delete(OfficialChunk).where(OfficialChunk.page_id == page.id))
            stats.errors += 1
            return []
        if r.status_code != 200:
            page.error = f"HTTP {r.status_code}"
            page.status = "ok" if page.status == "ok" else "error"
            stats.errors += 1
            return []
        final = self.sources.normalize(r.url) if r.url else page.url
        if final is None:
            page.status, page.error = "skipped", f"redirected off the allowed domains: {r.url}"[:500]
            stats.skipped += 1
            return []
        if final != page.url and s.scalar(select(OfficialPage.id).where(OfficialPage.url == final)) is not None:
            page.status, page.error = "skipped", f"same page as {final}"[:500]
            stats.skipped += 1
            return []
        if not r.text:
            page.status, page.error = "skipped", f"not HTML ({r.content_type[:60]})"
            stats.skipped += 1
            return []
        page.etag, page.last_modified = r.etag, r.last_modified
        ext = extract(r.text, final, d.lang, d.drop)
        new = self._queue_links(s, page, ext, r.text, counts, stats)
        if self.sources.is_hub(final):  # read for its links only
            page.status, page.error = "hub", None
            stats.unchanged += 1
            return new
        if len(ext.text) < MIN_TEXT:
            page.status, page.error = "skipped", "too little text"
            stats.skipped += 1
            return new
        if self._store(s, page, ext, now):
            stats.changed += 1
        else:
            stats.unchanged += 1
        return new

    def run(self, *, limit: int | None = None, budget_seconds: float | None = None) -> dict[str, Stats]:
        """One pass: seeds, then pending pages, then the least recently fetched ones. Stops after ``limit`` requests
        or ``budget_seconds``; returns stats per domain."""
        started = self.clock()
        cc = self.sources.country
        stats: dict[str, Stats] = {}
        with self.session_factory() as s:
            counts: Counter = Counter(dict(s.execute(
                select(OfficialPage.domain, func.count()).where(OfficialPage.country == cc)
                .group_by(OfficialPage.domain)).all()))
            for topic, url in self.sources.seed_list():
                if s.scalar(select(OfficialPage.id).where(OfficialPage.url == url)) is None:
                    d = self.sources.domain_of(url)
                    assert d is not None
                    s.add(OfficialPage(country=cc, url=url, domain=d.domain, topic=topic, depth=0, status="pending"))
                    counts[d.domain] += 1
            s.commit()
            fresh = utcnow() - timedelta(hours=self.fresh_hours)
            rows = s.scalars(select(OfficialPage).where(OfficialPage.country == cc)
                             .order_by(OfficialPage.fetched_at.is_not(None), OfficialPage.fetched_at,
                                       OfficialPage.depth, OfficialPage.id)).all()
            queues: dict[str, deque[OfficialPage]] = {}
            for row in rows:
                if row.fetched_at is None or _aware(row.fetched_at) < fresh:
                    queues.setdefault(row.domain, deque()).append(row)
            done = 0
            while any(queues.values()):
                if limit is not None and done >= limit:
                    break
                if budget_seconds is not None and self.clock() - started > budget_seconds:
                    log.info("official: time budget reached, the next run continues")
                    break
                # the domain that may be asked soonest: domains are interleaved, each at its own pace
                domain = min((d for d, q in queues.items() if q), key=lambda d: self._next.get(d, 0))
                page = queues[domain].popleft()
                st = stats.setdefault(domain, Stats())
                try:
                    new = self._process(s, page, counts, st)
                    s.commit()
                except Exception as e:  # one broken page must not stop the night's run
                    s.rollback()
                    log.exception("official: %s failed", page.url)
                    page = s.get(OfficialPage, page.id) or page
                    page.status, page.error, page.fetched_at = "error", f"{type(e).__name__}: {e}"[:500], utcnow()
                    s.commit()
                    st.errors += 1
                    new = []
                done += 1
                for row in new:
                    queues.setdefault(row.domain, deque()).append(row)
        return stats

