"""Zann law corpus: every act on the official legislation portal «Әділет», ru and kk texts (owner 30.09.2026,
option «В»). No LLM calls, no paid services: plain polite HTTP to the server-rendered mirror old.adilet.zan.kz,
gzip texts in the storage we already have (Object Storage or the local disk).

Discovery. The mirror's document index ``/rus/index/docs/…`` (open to robots; ``/rus/search/`` and ``/rus/list/docs/``
are closed by its robots.txt) takes the same filters as the search: status ``st=new|upd`` (in force: new and
updated) or ``st=yts|stp`` (lost force, stopped), act type ``va=КОД`` (code), ``ЗАК`` (law) …, and ``pagesize=100``.
Every listing page gives the act's code, title, status and a line such as «Закон … от 27 мая 2024 года № 87-VIII».
The listings are walked in priority order — codes and constitutional acts, then laws, then the main by-laws (decrees,
resolutions, orders), then one listing of everything else in force — 100 acts a page, and the walk is resumable:
each listing keeps its next page in ``zann_listings``.

Collection. Acts wait in ``zann_acts`` (state pending → done | missing | error) and are fetched in priority order,
one request at a time with a pause; each language's text is stored as ``zann/corpus/<code>.<lang>.txt.gz`` and
described in ``zann_files`` (sha256, chars, gzip bytes). A run is time-boxed; the next run continues. At the end
of a run that changed anything the manifest ``zann/corpus/manifest.jsonl.gz`` is rewritten from the tables.

Refresh. Listings are walked again every ``refresh_days``; an act whose status, title or listing line changed goes
back to the queue, and when the queue is empty the oldest texts (older than ``refresh_days``) are re-read. A text
whose sha256 did not change is not uploaded again.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import logging
import math
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import ZannAct, ZannFile, ZannListing
from ..lawagent.sources import ActNotFound, page_text
from ..official.crawler import Robots

log = logging.getLogger(__name__)

BASE = "https://old.adilet.zan.kz"
USER_AGENT = "Konsilier.AI Zann corpus collector (+https://konsilier.com; research; 1 request / 3 s)"
ROBOTS_TOKEN = "konsilier.ai zann corpus collector"
LANGS = {"ru": "rus", "kk": "kaz"}  # our code → the portal's path segment
MIN_CHARS = 300  # a shorter body means the portal has no text in this language (or a stub page)
PAGE_SIZE = 100
PREFIX = "zann/corpus/"
MANIFEST_KEY = PREFIX + "manifest.jsonl.gz"
MAX_ATTEMPTS = 3
MAX_ERRORS_IN_A_ROW = 3  # the portal is down or refusing: stop the run, the next one tries again

# Priority tiers of act types (the portal's «вид акта» codes). Lower is collected first.
TIERS: tuple[tuple[str, ...], ...] = (
    ("КОД", "КОНС", "КЗАК", "УКОН"),          # 0: codes, the Constitution, constitutional laws
    ("ЗАК", "УЗАК"),                         # 1: laws, decrees having the force of law
    ("УКАЗ", "ПОСТ", "НПОС", "ПРИК", "РАСП"),  # 2: main by-laws: decrees, resolutions, orders, directives
)
REST_TIER = len(TIERS)  # 3: everything else, from one listing of the status
STATUSES = {"in_force": "new|upd", "lost": "yts|stp"}
LOST_OFFSET = REST_TIER + 1  # lost-force acts come after every act in force

ARTICLE_TAG_RE = re.compile(r"(?is)<article\b[^>]*>(.*?)</article>")
TITLE_RE = re.compile(r"(?is)<title>(.*?)</title>")
KK_TITLE_SUFFIX_RE = re.compile(r"\s*-\s*\"?Әділет\"?\s*АҚЖ.*$")
KK_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
FOUND_RE = re.compile(r"Найдено:\s*<strong>(\d+)</strong>")
ITEM_RE = re.compile(
    r'(?s)<h4 class="post_header">.*?<a href="/rus/docs/([A-Z]\d{9,10}_?)">(.*?)</a>\s*</h4>'
    r'(.*?)(?=<h4 class="post_header">|<div class="wp-pagenavi"|$)')
STATUS_RE = re.compile(r'class="status status_(\w+)"')
INFO_RE = re.compile(r"(?s)<p>(.*?)</p>")
TAG_RE = re.compile(r"<[^>]+>")

Fetch = Callable[[str], str]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d  # SQLite drops the zone


# ---------------------------------------------------------------------------------------------------- act pages
def extract_act(raw: str) -> tuple[str, str]:
    """(title, text) of the act from a portal page: only the <article> body, not menus and banners."""
    m = TITLE_RE.search(raw)
    head = f"<title>{m.group(1)}</title>" if m else ""
    bodies = ARTICLE_TAG_RE.findall(raw)
    if not bodies:
        return page_text(raw)[0], ""
    title, text = page_text(f"<html><head>{head}</head><body>{''.join(bodies)}</body></html>")
    title = KK_TITLE_SUFFIX_RE.sub("", title).strip()  # page_text strips the ru suffix «- ИПС "Әділет"»
    lines = [ln.strip() for ln in text.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return title, text + "\n"


def looks_kazakh(text: str) -> bool:
    """True when kk-specific letters (ә ғ қ ң ө ұ ү һ і) are frequent enough: a ru page only has a few kk names."""
    letters = sum(ch.isalpha() for ch in text)
    return letters > 0 and sum(ch in KK_LETTERS for ch in text) / letters > 0.01


def doc_url(code: str, lang: str) -> str:
    return f"{BASE}/{LANGS[lang]}/docs/{code}"


def file_key(code: str, lang: str) -> str:
    return f"{PREFIX}{code}.{lang}.txt.gz"


class CorpusTexts:
    """The collected text of an act for the chat and the legal agent (``Adilet(local=CorpusTexts(...))``): an
    article is cut from our copy in milliseconds instead of opening the portal live (≈1–8 s). None when the act is
    not collected yet in that language; the portal is then read live."""

    PORTAL_LANGS = {v: k for k, v in LANGS.items()}  # rus → ru, kaz → kk

    def __init__(self, session_factory: sessionmaker[Session], storage: Any):
        self.sf, self.storage = session_factory, storage

    def __call__(self, code: str, lang: str) -> tuple[str, str] | None:
        ours = self.PORTAL_LANGS.get(lang, lang)
        with self.sf() as s:
            f = s.get(ZannFile, (code, ours))
            if f is None:
                return None
            key, title = f.key, f.title or ""
        text = gzip.decompress(self.storage.get(key)).decode("utf-8")
        return title, text


# ---------------------------------------------------------------------------------------------------- listings
@dataclass(frozen=True)
class Listed:
    code: str
    title: str
    status: str  # new | upd | yts | stp …
    info: str    # the listing line: act kind, date and number


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", fragment))).strip()


def parse_listing(raw: str) -> tuple[int | None, list[Listed]]:
    """(total found, the acts of this page) from an index page of the mirror."""
    m = FOUND_RE.search(raw)
    items = []
    for code, title, rest in ITEM_RE.findall(raw):
        st = STATUS_RE.search(rest)
        info = INFO_RE.search(rest)
        items.append(Listed(code, _clean(title)[:1000], st.group(1) if st else "",
                            _clean(info.group(1))[:1000] if info else ""))
    return (int(m.group(1)) if m else None), items


def listing_plan(statuses: list[str]) -> list[tuple[str, str, int]]:
    """[(listing key, act type, priority)] in walking order. The key is the index filter without the page."""
    plan: list[tuple[str, str, int]] = []
    for s in statuses:
        st = quote(STATUSES[s], safe="")
        offset = LOST_OFFSET if s == "lost" else 0
        for tier, types in enumerate(TIERS):
            for va in types:
                plan.append((f"st={st}&va={quote(va, safe='')}", va, offset + tier))
        plan.append((f"st={st}", "", offset + REST_TIER))
    return plan


def listing_url(key: str, page: int) -> str:
    return f"{BASE}/rus/index/docs/{key}&pagesize={PAGE_SIZE}&page={page}"


# ---------------------------------------------------------------------------------------------------- network
class PoliteFetcher:
    """One request at a time, a pause between requests, retries with back-off on 429/5xx and network errors."""

    def __init__(self, delay: float = 3.0, retries: int = 3, timeout: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep, client: httpx.Client | None = None,
                 user_agent: str = USER_AGENT):
        self.delay, self.retries, self.sleep = delay, retries, sleep
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                             headers={"User-Agent": user_agent})
        self._last = 0.0

    def __call__(self, url: str) -> str:
        for attempt in range(self.retries + 1):
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.client.get(url)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                self.sleep(self.delay * 2 ** (attempt + 1))
                continue
            if r.status_code in (404, 410):
                raise ActNotFound(url)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.retries:
                    r.raise_for_status()
                retry_after = r.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else self.delay * 2 ** (attempt + 1))
                continue
            r.raise_for_status()
            return r.text
        raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------------------------------- collector
@dataclass
class RunStats:
    listing_pages: int = 0
    discovered: int = 0     # acts seen for the first time
    requeued: int = 0       # known acts whose listing entry changed
    acts: int = 0           # acts read (every language tried)
    saved: int = 0          # files uploaded (new or changed text)
    unchanged: int = 0      # files re-read with the same sha256: not uploaded
    missing: int = 0        # (act, language) pairs with no text on the portal
    errors: int = 0
    bytes: int = 0          # gzip bytes uploaded
    stopped: str = ""       # why the run ended: budget | limit | idle | robots | errors (the portal is failing)


class Collector:
    """Discovery and collection, one step at a time, state in the database, texts in the storage."""

    def __init__(self, session_factory: sessionmaker[Session], storage: Any, fetch: Fetch, *,
                 langs: tuple[str, ...] = ("ru", "kk"), statuses: tuple[str, ...] = ("in_force",),
                 refresh_days: int = 30, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = utcnow):
        bad = [x for x in langs if x not in LANGS] + [x for x in statuses if x not in STATUSES]
        if bad or not langs or not statuses:
            raise ValueError(f"zann corpus: unknown languages or statuses {bad or (langs, statuses)}")
        self.sf, self.storage, self.fetch = session_factory, storage, fetch
        self.langs, self.plan = langs, listing_plan(list(statuses))
        self.refresh = timedelta(days=refresh_days) if refresh_days > 0 else None
        self.clock, self.now = clock, now
        self._robots: Any = None
        self._failed: set[str] = set()  # acts that failed in this run: retried by a later run, not at once

    # ---- robots.txt of the mirror, read once per run
    def allowed(self, url: str) -> bool:
        if self._robots is None:
            try:
                self._robots = Robots.parse(self.fetch(f"{BASE}/robots.txt"), ROBOTS_TOKEN)
            except ActNotFound:
                self._robots = Robots()
            if self._robots.crawl_delay and hasattr(self.fetch, "delay"):  # the site's Crawl-delay, if longer
                self.fetch.delay = max(self.fetch.delay, self._robots.crawl_delay)
        return self._robots.allowed(url)

    def run(self, budget_seconds: float | None = None, limit: int | None = None,
            discover_only: bool = False) -> RunStats:
        stats = RunStats()
        deadline = self.clock() + budget_seconds if budget_seconds else None
        self._robots, self._failed = None, set()
        self._restart_stale_listings()
        in_a_row = 0
        try:
            while True:
                if in_a_row >= MAX_ERRORS_IN_A_ROW:
                    stats.stopped = "errors"
                    break
                if deadline is not None and self.clock() >= deadline:
                    stats.stopped = "budget"
                    break
                if limit is not None and stats.acts >= limit:
                    stats.stopped = "limit"
                    break
                step = self._next_step(discover_only)
                if step is None:
                    stats.stopped = "idle"
                    break
                kind, arg = step
                before = stats.errors
                ok = self._listing_page(arg, stats) if kind == "listing" else self._act(arg, stats)
                if not ok:
                    stats.stopped = "robots"
                    break
                in_a_row = in_a_row + 1 if stats.errors > before else 0
        finally:
            if stats.saved or stats.discovered or stats.requeued:
                try:
                    self.write_manifest()
                except Exception:
                    log.exception("zann corpus: manifest not written")
        return stats

    # ---- what to do next: a listing page of a tier not below the queue's head, else the queue's head
    def _next_step(self, discover_only: bool) -> tuple[str, Any] | None:
        with self.sf() as s:
            done = {k for (k,) in s.execute(select(ZannListing.key).where(ZannListing.done_at.is_not(None)))}
            listing = next(((k, va, prio) for k, va, prio in self.plan if k not in done), None)
            if discover_only:
                return ("listing", listing) if listing else None
            head = s.scalar(select(ZannAct.priority).where(ZannAct.state == "pending")
                            .order_by(ZannAct.priority, ZannAct.code).limit(1))
            if listing and (head is None or listing[2] <= head):
                return "listing", listing
            code = self._next_act(s)
            if code:
                return "act", code
            return ("listing", listing) if listing else None

    def _next_act(self, s: Session) -> str | None:
        code = s.scalar(select(ZannAct.code).where(ZannAct.state == "pending")
                        .order_by(ZannAct.priority, ZannAct.code).limit(1))
        if code:
            return code
        q = select(ZannAct.code).where(ZannAct.state == "error", ZannAct.attempts < MAX_ATTEMPTS)
        if self._failed:
            q = q.where(ZannAct.code.not_in(self._failed))
        code = s.scalar(q.order_by(ZannAct.priority, ZannAct.code).limit(1))
        if code or self.refresh is None:
            return code
        old = self.now() - self.refresh
        return s.scalar(select(ZannAct.code).where(ZannAct.state == "done", ZannAct.fetched_at < old)
                        .order_by(ZannAct.fetched_at, ZannAct.code).limit(1))

    def _restart_stale_listings(self) -> None:
        """Walk a listing again once it is older than refresh_days: new acts, and changed ones back to the queue."""
        if self.refresh is None:
            return
        old = self.now() - self.refresh
        with self.sf() as s:
            for row in s.scalars(select(ZannListing).where(ZannListing.done_at.is_not(None))):
                if _aware(row.done_at) < old:
                    row.done_at, row.next_page = None, 1
            s.commit()

    def _listing_page(self, listing: tuple[str, str, int], stats: RunStats) -> bool:
        key, va, prio = listing
        with self.sf() as s:
            row = s.get(ZannListing, key) or ZannListing(key=key, act_type=va, priority=prio, next_page=1)
            page = row.next_page or 1
        url = listing_url(key, page)
        if not self.allowed(url):
            log.warning("zann corpus: robots.txt closes %s", url)
            return False
        try:
            total, items = parse_listing(self.fetch(url))
        except Exception as e:  # the listing is retried on the next step or the next run
            log.warning("zann corpus: listing %s page %s failed: %s", key, page, e)
            stats.errors += 1
            with self.sf() as s:  # count the failure so a broken listing does not stall the run forever
                row = s.get(ZannListing, key) or ZannListing(key=key, act_type=va, priority=prio, next_page=page)
                row.errors = (row.errors or 0) + 1
                if row.errors >= MAX_ATTEMPTS:
                    row.next_page, row.errors = page + 1, 0
                s.merge(row)
                s.commit()
            return True
        stats.listing_pages += 1
        now = self.now()
        with self.sf() as s:
            row = s.get(ZannListing, key) or ZannListing(key=key, act_type=va, priority=prio)
            if total is not None:
                row.total = total
            pages = math.ceil((row.total or 0) / PAGE_SIZE)
            codes = [it.code for it in items]
            known = {a.code: a for a in s.scalars(select(ZannAct).where(ZannAct.code.in_(codes)))} if codes else {}
            for it in items:
                act = known.get(it.code)
                if act is None:
                    act = ZannAct(code=it.code, title=it.title, act_type=va, status=it.status, info=it.info,
                                  priority=prio, state="pending", attempts=0, discovered_at=now)
                    s.add(act)
                    known[it.code] = act
                    stats.discovered += 1
                else:
                    changed = (act.status, act.title, act.info) != (it.status, it.title, it.info)
                    if changed and act.state in ("done", "missing"):
                        act.state, act.attempts = "pending", 0
                        stats.requeued += 1
                    act.status, act.title, act.info = it.status, it.title, it.info
                    if prio < act.priority:
                        act.priority = prio
                    if not act.act_type and va:
                        act.act_type = va
                act.listed_at = now
            row.pages, row.errors = pages, 0
            if not items or (row.total is not None and page >= pages):
                row.done_at, row.next_page = now, 1
            else:
                row.next_page = page + 1
            s.merge(row)
            s.commit()
        return True

    def _act(self, code: str, stats: RunStats) -> bool:
        results: dict[str, tuple[str, str, str] | None] = {}  # lang → (url, title, text) or None
        error = ""
        for lang in self.langs:
            url = doc_url(code, lang)
            if not self.allowed(url):
                log.warning("zann corpus: robots.txt closes %s", url)
                return False
            try:
                title, text = extract_act(self.fetch(url))
            except ActNotFound:
                results[lang] = None
                continue
            except Exception as e:  # keep going: one bad act must not stop the run
                error = f"{lang}: {type(e).__name__}: {e}"[:500]
                continue
            ok = len(text) >= MIN_CHARS and (lang != "kk" or looks_kazakh(text))
            results[lang] = (url, title, text) if ok else None
        stats.acts += 1
        now = self.now()
        with self.sf() as s:
            act = s.get(ZannAct, code)
            if act is None:
                return True
            act.fetched_at = now
            for lang, got in results.items():
                if got is None:
                    stats.missing += 1
                    continue
                url, title, text = got
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                f = s.get(ZannFile, (code, lang))
                if f is not None and f.sha256 == digest:
                    f.fetched_at = now
                    stats.unchanged += 1
                    continue
                data = gzip.compress(text.encode("utf-8"), compresslevel=9)
                key = file_key(code, lang)
                self.storage.put(key, data, "application/gzip")
                if f is None:
                    f = ZannFile(code=code, lang=lang)
                    s.add(f)
                f.key, f.url, f.title, f.sha256 = key, url, title[:1000], digest
                f.chars, f.bytes, f.fetched_at, f.changed_at = len(text), len(data), now, now
                stats.saved += 1
                stats.bytes += len(data)
            if error and not any(results.values()):
                act.state, act.attempts, act.error = "error", (act.attempts or 0) + 1, error
                stats.errors += 1
                self._failed.add(code)
            else:
                act.state = "done" if any(results.values()) or s.scalar(
                    select(func.count()).select_from(ZannFile).where(ZannFile.code == code)) else "missing"
                act.error = error or None
            s.commit()
        return True

    # ---- manifest: one JSON line per stored file
    def manifest_rows(self) -> list[dict[str, Any]]:
        with self.sf() as s:
            q = (select(ZannFile, ZannAct).join(ZannAct, ZannAct.code == ZannFile.code)
                 .order_by(ZannFile.code, ZannFile.lang))
            return [{"code": f.code, "title": f.title or a.title, "type": a.act_type, "status": a.status,
                     "info": a.info, "lang": f.lang, "url": f.url, "key": f.key,
                     "fetched_at": _aware(f.fetched_at).isoformat(timespec="seconds") if f.fetched_at else None,
                     "sha256": f.sha256, "chars": f.chars, "bytes": f.bytes} for f, a in s.execute(q)]

    def write_manifest(self) -> int:
        rows = self.manifest_rows()
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        self.storage.put(MANIFEST_KEY, gzip.compress(body.encode("utf-8")), "application/gzip")
        return len(rows)


def corpus_metrics(session: Session) -> dict[str, Any]:
    """Counts for /v1/admin/metrics["zann"]: acts known and by state, files, bytes, discovery progress."""
    states = dict(session.execute(select(ZannAct.state, func.count()).group_by(ZannAct.state)).all())
    by_lang = dict(session.execute(select(ZannFile.lang, func.count()).group_by(ZannFile.lang)).all())
    files, gz, chars = session.execute(select(func.count(), func.coalesce(func.sum(ZannFile.bytes), 0),
                                              func.coalesce(func.sum(ZannFile.chars), 0))).one()
    done_types = dict(session.execute(select(ZannAct.act_type, func.count()).where(ZannAct.state == "done")
                                      .group_by(ZannAct.act_type)).all())
    listings = session.execute(select(func.count(), func.count(ZannListing.done_at))).one()
    last = session.scalar(select(func.max(ZannFile.fetched_at)))
    return {
        "acts": sum(states.values()),
        "acts_done": states.get("done", 0),
        "acts_pending": states.get("pending", 0),
        "acts_missing": states.get("missing", 0),
        "acts_error": states.get("error", 0),
        "done_by_type": {k or "другое": v for k, v in done_types.items()},
        "files": files,
        "files_by_lang": by_lang,
        "bytes": int(gz),
        "chars": int(chars),
        "listings": {"started": listings[0], "done": listings[1]},
        "last_fetched_at": _aware(last).isoformat(timespec="seconds") if last else None,
    }


# ---------------------------------------------------------------------------------------------------- the job
class ZannCorpusJob:
    """A job of the scheduler tick (konsilier/core/deadlines.py), modelled on konsilier.official.job.NightlyCrawl.

    hour >= 0: once a night, at that local hour, one time-boxed run (``minutes``) in a background thread.
    hour < 0: continuous — a new time-boxed run starts on the first tick after the last one ended, so the corpus
    fills around the clock (the pause between requests still applies). When a run finds nothing to do, the job
    rests for an hour. Discovery and the queue live in the database, so every run continues the last one.
    """

    def __init__(self, make_collector: Callable[[], Collector], tz: Any, *, hour: int = 2, minutes: int = 50,
                 start: Callable[[Callable[[], None]], None] | None = None):
        self.make_collector, self.tz, self.hour, self.minutes = make_collector, tz, hour, max(1, minutes)
        self.start = start or (lambda fn: threading.Thread(target=fn, name="zann-corpus", daemon=True).start())
        self._done_day: Any = None
        self._rest_until: datetime | None = None
        self._running = False
        self._lock = threading.Lock()
        self.last: RunStats | None = None

    def __call__(self, session: Session, now: datetime | None) -> int:
        now = now or utcnow()
        local = now.astimezone(self.tz)
        with self._lock:
            if self._running:
                return 0
            if self.hour >= 0:
                if local.hour != self.hour or self._done_day == local.date():
                    return 0
                self._done_day = local.date()
            elif self._rest_until and now < self._rest_until:
                return 0
            self._running = True
        self.start(lambda: self._run(now))
        return 0  # no messages sent

    def _run(self, started: datetime) -> None:
        t0 = time.monotonic()

        def rest(delta: timedelta) -> None:  # counted from the end of the run
            self._rest_until = started + timedelta(seconds=time.monotonic() - t0) + delta
        try:
            collector = self.make_collector()
            try:
                stats = collector.run(budget_seconds=self.minutes * 60)
            finally:
                close = getattr(getattr(collector.fetch, "client", None), "close", None)
                if close:
                    close()
            self.last = stats
            if stats.stopped in ("idle", "robots"):
                rest(timedelta(hours=1))
            elif stats.stopped == "errors":
                rest(timedelta(minutes=15))
            log.info("zann corpus: run done %s", asdict(stats))
        except Exception:
            log.exception("zann corpus: run failed")
            rest(timedelta(minutes=15))
        finally:
            self._running = False


def build_collector(settings: Any, session_factory: sessionmaker[Session], storage: Any,
                    fetch: Fetch | None = None) -> Collector:
    langs = tuple(x.strip() for x in settings.zann_corpus_langs.split(",") if x.strip())
    statuses = tuple(x.strip() for x in settings.zann_corpus_statuses.split(",") if x.strip())
    return Collector(session_factory, storage, fetch or PoliteFetcher(delay=max(2.0, settings.zann_corpus_pause)),
                     langs=langs, statuses=statuses, refresh_days=settings.zann_corpus_refresh_days)
