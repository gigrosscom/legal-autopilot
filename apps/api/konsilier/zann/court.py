"""Zann court practice (owner 01.10.2026: «брать всё, что открыто и доступно»): what a country's courts publish
openly, collected politely and kept on our server only. Research and limits: docs/zann-court.md.

The sources are the country's data — ``packs/<cc>/zann/court.yaml``: seed pages, which parser reads them
(``library_tree`` — groups and years with attached files; ``files`` — a page linking documents; ``years`` — a
page per year), URL patterns, hosts, the publishing court, categories and their keywords, how dates, numbers and
languages are read. Only pages open without login or captcha are listed there; a captcha is never bypassed.
Court acts obtained lawfully (an official data service, files saved by hand) go in through ``import_file``
(source ``acts``) and get the same storage, manifest and anonymised export.

Like the law-corpus collector (konsilier/zann/corpus.py, whose robots parser, Retry-After reader and job this
module reuses): state in the database (zann_court_pages → zann_court_docs, a priority queue: our scenarios'
categories first), one request at a time with a pause (never shorter than the site's Crawl-delay), back-off on
429/5xx and resets, originals gzip in the storage (zann/court/orig/…), their text next to them
(zann/court/text/…), and a manifest (zann/court/manifest.jsonl.gz). Off by default (ZANN_COURT_ENABLED).
"""

from __future__ import annotations

import gzip
import hashlib
import html
import io
import json
import logging
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import Message
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import unquote, urljoin, urlsplit

import httpx
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import ZannCourtDoc, ZannCourtPage
from ..lawagent.sources import ActNotFound
from ..official.crawler import Robots
from .anonymize import Rules, anonymize_record, load_rules
from .corpus import ZannCorpusJob, _aware, describe, retry_after, utcnow

log = logging.getLogger(__name__)

# Who we are, for the sites' logs. sud.kz (checked 01.10.2026) silently drops the connection when the User-Agent has
# words such as «collector», «spider», «bot» or «httpx» (robots.txt included), and the file service of sud.gov.kz
# (JBoss) answers 404 to a User-Agent without a platform token. So: a platform token, our name and version; the
# contact goes in the standard From header. A pack may set its own («user_agent» in zann/court.yaml).
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Konsilier.AI/1.0"
FROM = "info@konsilier.com"
ROBOTS_TOKEN = "konsilier.ai"
PREFIX = "zann/court/"
MANIFEST_KEY = PREFIX + "manifest.jsonl.gz"
MIN_CHARS = 200
MAX_ATTEMPTS = 3
MAX_ERRORS_IN_A_ROW = 5
IMPORTED = "acts"  # the source of court acts imported from a lawful export

# Markup of the parsers (Drupal pages: a tree of «node-link» anchors, library items with attached files)
TREE_RE = re.compile(r"<a href='([^']*)' class=\"node-link\">([^<]*)</a>")
ITEM_RE = re.compile(r'(?s)<h2 class="main-group-title">(.*?)</h2>(.*?)(?=<h2 class="main-group-title">|$)')
FILE_LINK_RE = re.compile(r'(?s)<a href="([^"]+)"[^>]*>(.*?)</a>')
DOC_EXT_RE = re.compile(r"\.(pdf|docx?|rtf)(?:$|\?)", re.I)
TAG_RE = re.compile(r"<[^>]+>")


def doc_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", fragment))).strip()


def _https(url: str) -> str:
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


# ---------------------------------------------------------------------------------------------------- the country
def site_path(packs_dir: Path, country: str) -> Path:
    return Path(packs_dir) / country.lower() / "zann" / "court.yaml"


def countries(packs_dir: Path) -> list[str]:
    """Country packs that describe court-practice sources (packs/<cc>/zann/court.yaml)."""
    return sorted(p.parent.parent.name for p in Path(packs_dir).glob("*/zann/court.yaml"))


class NoSources(ValueError):
    """Nothing to collect: no pack with court sources (or several and no ZANN_COURT_COUNTRY), or unknown sources."""


def pick_country(packs_dir: Path, wanted: str = "") -> str:
    """The configured country, else the only pack with court-practice sources."""
    if wanted:
        return wanted.lower()
    found = countries(packs_dir)
    if len(found) != 1:
        raise NoSources(f"set ZANN_COURT_COUNTRY, packs with court sources: {found}")
    return found[0]


@dataclass(frozen=True)
class Found:
    url: str
    title: str
    lang: str | None = None
    year: str | None = None
    status: str | None = None
    label: str | None = None


class Site:
    """A country's open court-practice sources (packs/<cc>/zann/court.yaml): seeds, parsers, URL patterns,
    categories and their keywords, how dates, numbers and languages are read."""

    def __init__(self, data: dict[str, Any], country: str = ""):
        self.country = country
        self.court: str = data.get("court", "")
        self.user_agent: str = data.get("user_agent") or USER_AGENT
        self.hosts = set(data.get("hosts", []))
        # hosts never fetched, whatever a page links to (a captcha-protected bank of court acts, a paused source)
        self.blocked = set(data.get("blocked_hosts", []))
        for src in data["sources"].values():
            for seed in src.get("seeds", []):
                if not self.fetchable(seed["url"]):
                    raise ValueError(f"zann court: seed on a blocked host: {seed['url']}")
        self.sources: dict[str, dict[str, Any]] = data["sources"]
        self.ranks = {k: int(v.get("rank", 5)) for k, v in self.sources.items()}
        self.ranks[IMPORTED] = int(data.get("imported_rank", 5))
        self.categories = [(c["name"], re.compile(c["pattern"], re.I)) for c in data.get("categories", [])]
        self.category_rank = {name: i for i, (name, _) in enumerate(self.categories)} | {"other": len(self.categories)}
        page = data.get("page", {})
        self.page_start, self.page_end = page.get("start", ""), list(page.get("end", []))
        self.months = {m: i + 1 for i, m in enumerate(data.get("months", []))}
        self.date_re = re.compile(r"(\d{1,2})\s+(" + "|".join(map(re.escape, self.months)) + r")\s+(\d{4})") \
            if self.months else None
        self.number_re = re.compile(data.get("number_pattern", r"№\s*([\w./-]{1,20})"))
        lang = data.get("lang", {})
        self.default_lang = lang.get("default")
        self.lang_hints = [(k, re.compile(v, re.I)) for k, v in lang.get("hints", {}).items()]
        self.lang_letters = {k: set(v) for k, v in lang.get("letters", {}).items()}

    def fetchable(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return host not in getattr(self, "blocked", ()) and (not self.hosts or host in self.hosts)

    def seeds(self, source: str) -> list[tuple[str, str]]:
        return [(s["url"], s.get("kind", "leaf")) for s in self.sources[source].get("seeds", [])]

    # ---- what a document is about, when it is collected
    def classify(self, *texts: str) -> str:
        joined = " ".join(t for t in texts if t)
        return next((name for name, rx in self.categories if rx.search(joined)), "other")

    def priority(self, category: str, source: str, status: str | None = None) -> int:
        lost = 100 if status == "lost" else 0  # lost force: after everything in force
        return self.category_rank.get(category, len(self.categories)) * 10 + self.ranks.get(source, 5) + lost

    def date_and_number(self, title: str, year: str | None = None) -> tuple[str | None, str | None]:
        m = self.date_re.search(title or "") if self.date_re else None
        date = f"{m.group(3)}-{self.months[m.group(2)]:02d}-{int(m.group(1)):02d}" if m else year
        n = self.number_re.search(title or "")
        return date, (n.group(1) if n else None)

    def lang_hint(self, name: str) -> str | None:
        return next((lang for lang, rx in self.lang_hints if rx.search(name or "")), None)

    def lang_of(self, text: str) -> str | None:
        letters = sum(ch.isalpha() for ch in text) or 1
        for lang, own in self.lang_letters.items():
            if sum(ch in own for ch in text) / letters > 0.01:
                return lang
        return self.default_lang

    # ---- parsing
    def main(self, raw: str) -> str:
        """The page's own content (menus and sidebars repeat links)."""
        i = raw.find(self.page_start) if self.page_start else -1
        seg = raw[i:] if i >= 0 else raw
        for end in self.page_end:
            j = seg.find(end)
            if j > 0:
                return seg[:j]
        return seg

    def parse_index(self, source: str, raw: str, url: str) -> list[tuple[str, str]]:
        """[(leaf url, label)] of an index page."""
        src = self.sources[source]
        if src["parser"] == "library_tree":  # a «#» node names the group below it
            out, group = [], ""
            for href, text in TREE_RE.findall(raw):
                if href == "#":
                    group = _clean(text)
                elif src.get("leaf_link", "") in href and self.fetchable(urljoin(url, href)):
                    out.append((urljoin(url, href), f"{group} / {_clean(text)}".strip(" /")))
            return out
        if src["parser"] == "years":
            seen: dict[str, str] = {}
            for href, year in re.findall(src["year_link"], raw):
                if self.fetchable(urljoin(url, href)):
                    seen.setdefault(urljoin(url, href), year)
            return sorted(seen.items(), key=lambda kv: kv[1], reverse=True)  # the newest first
        return []

    def parse_leaf(self, source: str, raw: str, url: str) -> list[Found]:
        src = self.sources[source]
        if src["parser"] == "library_tree":
            marker = src.get("lost_marker")
            status = "lost" if marker and marker in url else "in_force"
            year_re = re.compile(re.escape(src.get("year_label", "")) + r'</span>\s*<span class="field-value">\s*(\d{4})')
            out = []
            for title, body in ITEM_RE.findall(self.main(raw)):
                year = year_re.search(body)
                for href, name in FILE_LINK_RE.findall(body):
                    if src.get("file_link", "\0") not in href and not DOC_EXT_RE.search(href):
                        continue
                    name = _clean(name)
                    if not self.fetchable(_https(urljoin(url, href))):
                        continue
                    out.append(Found(_https(urljoin(url, href)), _clean(title), self.lang_hint(name),
                                     year.group(1) if year else None, status, name))
            return out
        return self.parse_files(raw, url)

    def parse_files(self, raw: str, url: str) -> list[Found]:
        """Document links (PDF, DOC, DOCX, RTF) in the page's content, each once, on the pack's hosts only."""
        seen, out = set(), []
        for href, text in FILE_LINK_RE.findall(self.main(raw)):
            if not DOC_EXT_RE.search(href):
                continue
            full = _https(urljoin(url, html.unescape(href)))
            if not self.fetchable(full) or full in seen:
                continue
            seen.add(full)
            title = _clean(text) or unquote(full.rsplit("/", 1)[-1])
            year = re.search(r"(20\d\d|19\d\d)", title + " " + full)
            out.append(Found(full, title[:1000], self.lang_hint(title), year.group(1) if year else None))
        return out


def load_site(packs_dir: Path, country: str) -> Site:
    path = site_path(packs_dir, country)
    if not path.is_file():
        raise NoSources(f"no court sources for {country!r} ({path})")
    return Site(yaml.safe_load(path.read_text("utf-8")), country.lower())


# ---------------------------------------------------------------------------------------------------- text
def extract_text(data: bytes, ext: str) -> str:
    """Plain text of a DOCX, PDF (text layer only; scans give nothing), RTF or text file."""
    ext = ext.lower()
    try:
        if ext == "docx":
            from ..core.documents import docx_text

            text = docx_text(data)
        elif ext == "pdf":
            from pypdf import PdfReader

            text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        elif ext == "rtf":
            raw = data.decode("latin-1")
            raw = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1251"), raw)
            raw = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), raw)
            text = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", raw)
        elif ext in ("txt", "html", "htm"):
            text = data.decode("utf-8", errors="replace")
            if ext != "txt":
                text = _clean(re.sub(r"(?is)<(script|style).*?</\1>", "", text).replace("</p>", "\n"))
        else:  # .doc (binary Word): kept as the original, no text without a converter
            return ""
    except Exception as e:  # noqa: BLE001 — a broken file is stored, its text is just empty
        log.warning("zann court: no text from a .%s file: %s", ext, e)
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip() + "\n" if text.strip() else ""


def file_ext(url: str, content_type: str, disposition: str) -> str:
    name = ""
    if disposition:
        msg = Message()
        msg["content-disposition"] = disposition
        name = msg.get_filename() or ""
        if not name:
            m = re.search(r"filename\*=utf-8''([^;]+)", disposition, re.I)
            name = unquote(m.group(1)) if m else ""
    for candidate in (name, urlsplit(url).path):
        m = DOC_EXT_RE.search(candidate.lower())
        if m:
            return m.group(1)
    ct = content_type.lower()
    for key, ext in (("pdf", "pdf"), ("wordprocessingml", "docx"), ("msword", "doc"), ("rtf", "rtf"),
                     ("html", "html"), ("text/plain", "txt")):
        if key in ct:
            return ext
    return "bin"


# ---------------------------------------------------------------------------------------------------- network
@dataclass
class Got:
    data: bytes
    content_type: str = ""
    disposition: str = ""

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


class CourtFetcher:
    """One request at a time with a pause (``delay``, raised to the site's Crawl-delay), retries with back-off on
    429/5xx and network resets, a size cap. Same manners as konsilier.zann.corpus.PoliteFetcher, but returns bytes."""

    def __init__(self, delay: float = 1.0, retries: int = 3, timeout: float = 120.0, max_bytes: int = 60_000_000,
                 sleep: Callable[[float], None] = time.sleep, client: httpx.Client | None = None,
                 user_agent: str = USER_AGENT):
        self.delay, self.retries, self.sleep, self.max_bytes = delay, retries, sleep, max_bytes
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                             headers={"User-Agent": user_agent, "From": FROM})
        self._last = 0.0

    def __call__(self, url: str) -> Got:
        for attempt in range(self.retries + 1):
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            try:
                with self.client.stream("GET", url) as r:
                    if r.status_code in (404, 410):
                        raise ActNotFound(url)
                    if r.status_code == 429 or r.status_code >= 500:
                        if attempt == self.retries:
                            r.raise_for_status()
                        wait = retry_after(r.headers.get("Retry-After", ""))
                        self.sleep(min(wait, 900.0) if wait is not None
                                   else max(self.delay, 5.0) * 2 ** (attempt + 1))
                        continue
                    r.raise_for_status()
                    chunks, size = [], 0
                    for chunk in r.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise ValueError(f"larger than {self.max_bytes} bytes")
                        chunks.append(chunk)
                    self._last = time.monotonic()  # the pause counts from the end of a long download
                    return Got(b"".join(chunks), r.headers.get("Content-Type", ""),
                               r.headers.get("Content-Disposition", ""))
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                self.sleep(max(self.delay, 5.0) * 2 ** (attempt + 1))
        raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------------------------------- collector
class SiteUnreachable(Exception):
    """robots.txt could not be read (resets, timeouts): nothing is fetched from that host in this run."""


@dataclass
class RunStats:
    pages: int = 0          # listing pages read
    discovered: int = 0     # documents seen for the first time
    docs: int = 0           # documents downloaded
    saved: int = 0          # originals stored (new or changed)
    unchanged: int = 0
    notext: int = 0         # stored, but no text layer (scans, .doc)
    missing: int = 0        # 404 on the site
    errors: int = 0
    masked: int = 0         # personal data replaced by labels in the stored texts
    bytes: int = 0          # gzip bytes stored
    stopped: str = ""       # budget | limit | idle | robots (closed by robots.txt) | unreachable (robots.txt not
    #                         read: resets, timeouts) | errors (MAX_ERRORS_IN_A_ROW failures in a row)
    error: str = ""         # the last error of the run


class Collector:
    def __init__(self, session_factory: sessionmaker[Session], storage: Any, fetch: Callable[[str], Got], site: Site,
                 rules: Rules, *, sources: tuple[str, ...] = (), refresh_days: int = 30,
                 clock: Callable[[], float] = time.monotonic, now: Callable[[], datetime] = utcnow):
        sources = sources or tuple(site.sources)
        bad = [s for s in sources if s not in site.sources]
        if bad or not sources:
            raise NoSources(f"unknown sources {bad}, the pack has {list(site.sources)}")
        self.sf, self.storage, self.fetch, self.site, self.sources = session_factory, storage, fetch, site, sources
        self.rules = rules  # the text kept for search and training is masked with these; the original stays as it is
        self.refresh = timedelta(days=refresh_days) if refresh_days > 0 else None
        self.clock, self.now = clock, now
        self._robots: dict[str, Robots] = {}
        self._failed: set[str] = set()

    # ---- robots.txt of each host, read once per run
    def allowed(self, url: str) -> bool:
        if not self.site.fetchable(url):  # never a blocked host (e.g. a captcha-protected bank of court acts)
            log.warning("zann court: not fetching %s (host not allowed by the pack)", url)
            return False
        parts = urlsplit(url)
        host = parts.hostname or ""
        if host not in self._robots:
            try:
                rules = Robots.parse(self.fetch(f"{parts.scheme}://{parts.netloc}/robots.txt").text, ROBOTS_TOKEN)
            except ActNotFound:
                rules = Robots()
            except Exception as e:  # the site is unreachable: no rules, no crawling; the run stops as «unreachable»
                raise SiteUnreachable(f"{host}: {describe(e)}") from e
            self._robots[host] = rules
            if rules.crawl_delay and hasattr(self.fetch, "delay"):
                self.fetch.delay = max(self.fetch.delay, rules.crawl_delay)
        return self._robots[host].allowed(url)

    def run(self, budget_seconds: float | None = None, limit: int | None = None,
            discover_only: bool = False) -> RunStats:
        stats = RunStats()
        deadline = self.clock() + budget_seconds if budget_seconds else None
        self._robots, self._failed = {}, set()
        self._seed()
        in_a_row = 0
        try:
            while True:
                if in_a_row >= MAX_ERRORS_IN_A_ROW:
                    stats.stopped = "errors"
                    break
                if deadline is not None and self.clock() >= deadline:
                    stats.stopped = "budget"
                    break
                if limit is not None and stats.docs >= limit:
                    stats.stopped = "limit"
                    break
                step = self._next_step(discover_only)
                if step is None:
                    stats.stopped = "idle"
                    break
                kind, arg = step
                before = stats.errors
                try:
                    ok = self._page(arg, stats) if kind == "page" else self._doc(arg, stats)
                except SiteUnreachable as e:
                    log.warning("zann court: robots.txt unreadable, stopping: %s", e)
                    stats.errors += 1
                    stats.stopped, stats.error = "unreachable", f"robots.txt {e}"[:300]
                    break
                if not ok:
                    stats.stopped, stats.error = "robots", f"robots.txt closes {arg}"[:300]
                    break
                in_a_row = in_a_row + 1 if stats.errors > before else 0
        finally:
            if stats.saved or stats.discovered:
                try:
                    self.write_manifest()
                except Exception:
                    log.exception("zann court: manifest not written")
        return stats

    def _seed(self) -> None:
        now = self.now()
        with self.sf() as s:
            for source in self.sources:
                for url, kind in self.site.seeds(source):
                    row = s.get(ZannCourtPage, url)
                    if row is None:
                        s.add(ZannCourtPage(url=url, source=source, kind=kind, state="pending", attempts=0, found=0))
                    elif self.refresh and row.state == "done" and row.done_at and _aware(row.done_at) < now - self.refresh:
                        row.state, row.attempts = "pending", 0  # walk again: new documents appear over time
            if self.refresh:
                old = now - self.refresh
                for row in s.scalars(select(ZannCourtPage).where(ZannCourtPage.kind == "leaf",
                                                                 ZannCourtPage.state == "done")):
                    if row.done_at and _aware(row.done_at) < old and row.source in self.sources:
                        row.state, row.attempts = "pending", 0
            s.commit()

    def _next_step(self, discover_only: bool) -> tuple[str, str] | None:
        with self.sf() as s:
            q = (select(ZannCourtPage.url).where(ZannCourtPage.source.in_(self.sources),
                                                 ZannCourtPage.state.in_(("pending", "error")),
                                                 ZannCourtPage.attempts < MAX_ATTEMPTS))
            if self._failed:
                q = q.where(ZannCourtPage.url.not_in(self._failed))
            page = s.scalar(q.order_by(ZannCourtPage.kind, ZannCourtPage.url).limit(1))  # index before leaf
            if page:
                return "page", page
            if discover_only:
                return None
            q = select(ZannCourtDoc.id).where(ZannCourtDoc.state.in_(("pending", "error")),
                                              ZannCourtDoc.attempts < MAX_ATTEMPTS,
                                              ZannCourtDoc.source.in_(self.sources))
            if self._failed:
                q = q.where(ZannCourtDoc.id.not_in(self._failed))
            doc = s.scalar(q.order_by(ZannCourtDoc.state.desc(), ZannCourtDoc.priority, ZannCourtDoc.id).limit(1))
            return ("doc", doc) if doc else None

    def _page(self, url: str, stats: RunStats) -> bool:
        if not self.site.fetchable(url):  # a host the pack forbids: never requested, never retried
            with self.sf() as s:
                row = s.get(ZannCourtPage, url)
                row.state, row.error = "blocked", "host not allowed by the pack"
                s.commit()
            return True
        if not self.allowed(url):
            log.warning("zann court: robots.txt closes %s", url)
            return False
        with self.sf() as s:
            row = s.get(ZannCourtPage, url)
            source, kind = row.source, row.kind
        try:
            raw = self.fetch(url).text
        except ActNotFound:  # the page is gone (or moved): nothing to list; walked again at the next refresh
            with self.sf() as s:
                row = s.get(ZannCourtPage, url)
                row.state, row.done_at, row.found, row.error = "done", self.now(), 0, "404"
                s.commit()
            return True
        except Exception as e:  # noqa: BLE001 — retried by a later step or run
            log.warning("zann court: page %s failed: %s", url, e)
            stats.errors += 1
            stats.error = f"{url}: {describe(e)}"[:300]
            self._failed.add(url)
            with self.sf() as s:
                row = s.get(ZannCourtPage, url)
                row.state, row.attempts = "error", (row.attempts or 0) + 1
                row.error = f"{describe(e)}"[:500]
                s.commit()
            return True
        stats.pages += 1
        now = self.now()
        leaves: list[tuple[str, str]] = []
        found: list[Found] = []
        if kind == "index":
            leaves = self.site.parse_index(source, raw, url)
        else:
            found = self.site.parse_leaf(source, raw, url)
        with self.sf() as s:
            for leaf, leaf_label in leaves:
                if s.get(ZannCourtPage, leaf) is None:
                    s.add(ZannCourtPage(url=leaf, source=source, kind="leaf", label=leaf_label[:300],
                                        state="pending", attempts=0, found=0))
            for f in found:
                did = doc_id(f.url)
                if s.get(ZannCourtDoc, did) is not None:
                    continue
                cat = self.site.classify(f.title)
                date, number = self.site.date_and_number(f.title, f.year)
                s.add(ZannCourtDoc(id=did, source=source, url=f.url[:1000], title=f.title[:1000],
                                   court=self.site.court or None, category=cat, doc_date=date, number=number, lang=f.lang,
                                   status=f.status, priority=self.site.priority(cat, source, f.status), state="pending",
                                   attempts=0, discovered_at=now))
                stats.discovered += 1
            row = s.get(ZannCourtPage, url)
            row.state, row.done_at, row.error = "done", now, None
            row.found = len(found) or len(leaves)
            s.commit()
        return True

    def _doc(self, did: str, stats: RunStats) -> bool:
        with self.sf() as s:
            d = s.get(ZannCourtDoc, did)
            url = d.url
            if not self.site.fetchable(url):  # a host the pack forbids: never requested, never retried
                d.state, d.error = "blocked", "host not allowed by the pack"
                s.commit()
                return True
        if not self.allowed(url):
            log.warning("zann court: robots.txt closes %s", url)
            return False
        try:
            got = self.fetch(url)
        except ActNotFound:
            stats.missing += 1
            with self.sf() as s:
                d = s.get(ZannCourtDoc, did)
                d.state, d.fetched_at = "missing", self.now()
                s.commit()
            return True
        except Exception as e:  # noqa: BLE001 — one bad file must not stop the run
            stats.errors += 1
            stats.error = f"{url}: {describe(e)}"[:300]
            self._failed.add(did)
            with self.sf() as s:
                d = s.get(ZannCourtDoc, did)
                d.state, d.attempts, d.error = "error", (d.attempts or 0) + 1, f"{describe(e)}"[:500]
                s.commit()
            return True
        stats.docs += 1
        ext = file_ext(url, got.content_type, got.disposition)
        if ext == "html" and DOC_EXT_RE.search(url):  # a «file» link answering with an HTML page: not there
            stats.missing += 1
            with self.sf() as s:
                d = s.get(ZannCourtDoc, did)
                d.state, d.fetched_at, d.error = "missing", self.now(), "html instead of a file"
                s.commit()
            return True
        self._store(did, got.data, ext, got.content_type, stats)
        return True

    def _store(self, did: str, data: bytes, ext: str, mime: str, stats: RunStats) -> None:
        digest = hashlib.sha256(data).hexdigest()
        now = self.now()
        with self.sf() as s:
            d = s.get(ZannCourtDoc, did)
            d.fetched_at, d.attempts, d.error = now, 0, None
            if d.sha256 == digest and d.key:
                stats.unchanged += 1
                d.state = "done" if d.chars else "notext"
                s.commit()
                return
            raw_text = extract_text(data, ext)
            if len(raw_text) >= MIN_CHARS:
                if not d.lang:
                    d.lang = self.site.lang_of(raw_text)
                if d.category == "other":  # the title said nothing: the opening of the text decides
                    d.category = self.site.classify(raw_text[:4000])
                    d.priority = self.site.priority(d.category, d.source, d.status)
            # Only the masked text is ever stored as text (indexed, searched, used for training); the unmasked
            # words live only inside the original file on our server.
            masked, report = anonymize_record({"title": d.title or "", "text": raw_text}, self.rules)
            text = masked["text"]
            if d.source == IMPORTED:
                d.title = masked["title"][:1000]
            stats.masked += report.total
            key = f"{PREFIX}orig/{did}.{ext}.gz"
            orig = gzip.compress(data, compresslevel=6)
            self.storage.put(key, orig, "application/gzip")
            size = len(orig)
            text_key = None
            if len(text) >= MIN_CHARS:
                text_key = f"{PREFIX}text/{did}.txt.gz"
                packed = gzip.compress(text.encode("utf-8"), compresslevel=9)
                self.storage.put(text_key, packed, "application/gzip")
                size += len(packed)
            else:
                stats.notext += 1
            d.key, d.text_key, d.sha256, d.mime = key, text_key, digest, (mime or ext)[:100]
            d.chars, d.bytes = (len(text) if text_key else 0), size
            d.state = "done" if text_key else "notext"
            s.commit()
        stats.saved += 1
        stats.bytes += size

    # ---- court acts from a lawful export (Smart Bridge, files saved by hand): never fetched from office.sud.kz
    def import_file(self, name: str, data: bytes, meta: dict[str, Any] | None = None) -> str:
        meta = dict(meta or {})
        url = meta.get("url") or f"import:{hashlib.sha256(data).hexdigest()}"
        did = doc_id(url)
        ext = (Path(name).suffix.lstrip(".") or "bin").lower()
        stats = RunStats()
        with self.sf() as s:
            if s.get(ZannCourtDoc, did) is None:
                text = extract_text(data, ext)
                cat = meta.get("category") or self.site.classify(meta.get("title", ""), text[:4000])
                date, number = self.site.date_and_number(meta.get("title", ""), None)
                s.add(ZannCourtDoc(id=did, source=IMPORTED, url=url[:1000], title=(meta.get("title") or name)[:1000],
                                   court=(meta.get("court") or "")[:200] or None, category=cat,
                                   doc_date=meta.get("date") or date, number=meta.get("number") or number,
                                   lang=meta.get("lang"), status=None, priority=self.site.priority(cat, IMPORTED),
                                   state="pending", attempts=0, discovered_at=self.now()))
                s.commit()
        self._store(did, data, ext, meta.get("mime", ""), stats)
        return did

    # ---- manifest: one JSON line per document (stays on our server like the originals)
    def manifest_rows(self) -> list[dict[str, Any]]:
        with self.sf() as s:
            q = select(ZannCourtDoc).where(ZannCourtDoc.key.is_not(None)).order_by(ZannCourtDoc.priority,
                                                                                  ZannCourtDoc.id)
            return [{"id": d.id, "source": d.source, "court": d.court, "category": d.category, "date": d.doc_date,
                     "number": d.number, "title": d.title, "lang": d.lang, "status": d.status, "url": d.url,
                     "key": d.key, "text_key": d.text_key, "mime": d.mime, "sha256": d.sha256, "chars": d.chars,
                     "bytes": d.bytes,
                     "fetched_at": _aware(d.fetched_at).isoformat(timespec="seconds") if d.fetched_at else None}
                    for d in s.scalars(q)]

    def write_manifest(self) -> int:
        rows = self.manifest_rows()
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        self.storage.put(MANIFEST_KEY, gzip.compress(body.encode("utf-8")), "application/gzip")
        return len(rows)


# ---------------------------------------------------------------------------------------------------- export
def export_anonymised(session_factory: sessionmaker[Session], storage: Any, rules: Rules, *,
                      sources: tuple[str, ...] = (),
                      categories: tuple[str, ...] = (), limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Anonymised texts for training or for transfer abroad (NVIDIA, Kaggle, Hugging Face): never an original
    file, never a storage key. Court acts lose their url and case number (they identify the people)."""
    with session_factory() as s:
        q = select(ZannCourtDoc).where(ZannCourtDoc.text_key.is_not(None))
        if sources:
            q = q.where(ZannCourtDoc.source.in_(sources))
        if categories:
            q = q.where(ZannCourtDoc.category.in_(categories))
        docs = list(s.scalars(q.order_by(ZannCourtDoc.priority, ZannCourtDoc.id).limit(limit)))
        s.expunge_all()
    for d in docs:
        text = gzip.decompress(storage.get(d.text_key)).decode("utf-8")
        # stored texts are masked already (Collector._store); masking again catches anything the rules learnt since
        clean, _ = anonymize_record({"title": d.title or "", "text": text}, rules)
        labels = Counter(m.group(1) for m in re.finditer(r"\[(\D+?)\d+\]", clean["title"] + clean["text"])
                         if rules.label_re.fullmatch(m.group()))
        acts = d.source == IMPORTED
        yield {"id": d.id[:16], "source": d.source, "court": d.court, "category": d.category, "date": d.doc_date,
               "number": None if acts else d.number, "lang": d.lang, "status": d.status,
               "url": None if acts else d.url, "title": clean["title"], "text": clean["text"],
               "anonymised": dict(labels)}


# ---------------------------------------------------------------------------------------------------- metrics, job
def court_metrics(session: Session) -> dict[str, Any]:
    """Counts for /v1/admin/metrics["zann_court"] and the serial console line «zanncourt …»."""
    states = dict(session.execute(select(ZannCourtDoc.state, func.count()).group_by(ZannCourtDoc.state)).all())
    by_source = dict(session.execute(select(ZannCourtDoc.source, func.count())
                                     .where(ZannCourtDoc.state.in_(("done", "notext")))
                                     .group_by(ZannCourtDoc.source)).all())
    by_cat = dict(session.execute(select(ZannCourtDoc.category, func.count())
                                  .where(ZannCourtDoc.state == "done").group_by(ZannCourtDoc.category)).all())
    gz, chars = session.execute(select(func.coalesce(func.sum(ZannCourtDoc.bytes), 0),
                                       func.coalesce(func.sum(ZannCourtDoc.chars), 0))).one()
    pages = dict(session.execute(select(ZannCourtPage.state, func.count()).where(ZannCourtPage.kind != STATUS_KIND)
                                 .group_by(ZannCourtPage.state)).all())
    last = session.scalar(select(func.max(ZannCourtDoc.fetched_at)))
    return {
        "docs": sum(states.values()),
        "done": states.get("done", 0),
        "notext": states.get("notext", 0),
        "pending": states.get("pending", 0),
        "missing": states.get("missing", 0),
        "error": states.get("error", 0),
        "by_source": by_source,
        "by_category": by_cat,
        "bytes": int(gz),
        "chars": int(chars),
        "pages": {"done": pages.get("done", 0), "pending": pages.get("pending", 0), "error": pages.get("error", 0)},
        "last_fetched_at": _aware(last).isoformat(timespec="seconds") if last else None,
        "status": court_status(session),
    }


# ---- the collector's state for the serial console line and /v1/admin/metrics: one row of zann_court_pages
STATUS_URL, STATUS_KIND = "#status", "status"
STATES = {  # how a run ended → what the status line says
    "idle": "waiting", "budget": "waiting", "limit": "waiting",
    "unreachable": "blocked(robots_unreachable)", "robots": "blocked(robots_closed)",
    "errors": "error(errors_in_a_row)",
}


def run_state(stopped: str, error: str = "") -> str:
    """running | waiting | blocked(robots_unreachable) | blocked(robots_closed) | no_sources | error(<reason>)."""
    if stopped == "running":
        return "running"
    if stopped == "failed":
        if error.startswith(NoSources.__name__):
            return "no_sources"
        return f"error({error.split(':', 1)[0] or 'failed'})"
    return STATES.get(stopped, f"error({stopped or 'unknown'})")


def save_status(session_factory: sessionmaker[Session], state: str, *, error: str = "", stats: Any = None,
                started: datetime | None = None, ended: datetime | None = None,
                next_run: datetime | None = None) -> None:
    """Keep the collector's state: «running» when a run starts (its last error and last run stay), the outcome when
    it ends. The details are JSON in ``label``, the last error in ``error``, the end of the last run in ``done_at``."""
    with session_factory() as s:
        row = s.get(ZannCourtPage, STATUS_URL)
        if row is None:
            row = ZannCourtPage(url=STATUS_URL, source="#", kind=STATUS_KIND, state="-", attempts=0, found=0)
            s.add(row)
        try:
            info = json.loads(row.label or "{}")
        except ValueError:
            info = {}
        info["state"] = state
        info["next"] = next_run.isoformat(timespec="seconds") if next_run else None
        if started is not None:
            info["started"] = started.isoformat(timespec="seconds")
        if state != "running":
            row.done_at = ended or utcnow()
            row.error = error[:500] or None
            if stats is not None:
                info["run"] = {"pages": stats.pages, "docs": stats.docs, "saved": stats.saved, "errors": stats.errors}
        row.label = json.dumps(info, ensure_ascii=False)[:300]
        s.commit()


def court_status(session: Session) -> dict[str, Any]:
    """{state, last_error, last_run, next_run, started, run}; state «never_run» before the first run."""
    row = session.get(ZannCourtPage, STATUS_URL)
    if row is None:
        return {"state": "never_run", "last_error": None, "last_run": None, "next_run": None}
    try:
        info = json.loads(row.label or "{}")
    except ValueError:
        info = {}
    return {"state": info.get("state", "unknown"), "last_error": row.error,
            "last_run": _aware(row.done_at).isoformat(timespec="seconds") if row.done_at else None,
            "next_run": info.get("next"), "started": info.get("started"), "run": info.get("run")}


def make_job(make_collector: Callable[[], Collector], tz: Any, *, hour: int = 4, minutes: int = 50,
             session_factory: sessionmaker[Session] | None = None) -> ZannCorpusJob:
    """The corpus job (konsilier/zann/corpus.py) driving this collector: nightly at ``hour`` or continuous (-1). With
    a session factory, every start and outcome is kept for the status line (``court_status``)."""
    def on_status(stopped: str, stats: Any, error: str, next_run: datetime | None) -> None:
        now = utcnow()
        save_status(session_factory, run_state(stopped, error), error=error, stats=stats,  # type: ignore[arg-type]
                    started=now if stopped == "running" else None, ended=now, next_run=next_run)

    return ZannCorpusJob(make_collector, tz, hour=hour, minutes=minutes,  # type: ignore[arg-type]
                         start=lambda fn: threading.Thread(target=fn, name="zann-court", daemon=True).start(),
                         name="zann court", on_status=on_status if session_factory is not None else None)


def build_collector(settings: Any, session_factory: sessionmaker[Session], storage: Any,
                    fetch: Callable[[str], Got] | None = None) -> Collector:
    """The collector of the configured country (ZANN_COURT_COUNTRY, else the only pack with zann/court.yaml)."""
    site = load_site(settings.packs_dir, pick_country(settings.packs_dir, settings.zann_court_country))
    sources = tuple(x.strip() for x in settings.zann_court_sources.split(",") if x.strip())
    # ≤ 1–2 requests a second at most; a site's robots.txt Crawl-delay is applied on top by allowed()
    fetch = fetch or CourtFetcher(delay=max(0.5, settings.zann_court_pause),
                                  max_bytes=int(settings.zann_court_max_mb * 1_000_000), user_agent=site.user_agent)
    country = site.country
    return Collector(session_factory, storage, fetch, site, load_rules(settings.packs_dir, country), sources=sources,
                     refresh_days=settings.zann_court_refresh_days)
