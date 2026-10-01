"""Zann law corpus: every act on the official legislation portal «Әділет», ru and kk texts (owner 30.09.2026,
option «В»). No LLM calls, no paid services: plain polite HTTP to the server-rendered mirror old.adilet.zan.kz,
gzip texts in the storage we already have (Object Storage or the local disk).

Discovery. The mirror's document index ``/rus/index/docs/…`` (open to robots; ``/rus/search/`` and ``/rus/list/docs/``
are closed by its robots.txt) takes the same filters as the search: status ``st=new|upd`` (in force: new and
updated) or ``st=yts|stp`` (lost force, stopped), act type ``va=КОД`` (code), ``ЗАК`` (law) …, issuing body
``kv=…``, and ``pagesize=100``. Every listing page gives the act's code, title, status and a line such as «Закон …
от 27 мая 2024 года № 87-VIII». The listings are walked in priority order — codes and constitutional acts, then
laws, then the normative resolutions of the Supreme Court (``va=НПОС&kv=1_105``, our type label ``НПВС``), then the
main by-laws (decrees, resolutions, orders), then one listing of everything else in force — 100 acts a page, and
the walk is resumable: each listing keeps its next page in ``zann_listings``.

Collection. Acts wait in ``zann_acts`` (state pending → busy → done | missing | error) and are fetched in priority
order by ``concurrency`` workers (owner 01.10.2026: the whole corpus by 04.10). A worker claims an act with a
conditional UPDATE (``state`` → ``busy``, ``fetched_at`` = the claim time; on PostgreSQL the candidate row is read
``FOR UPDATE SKIP LOCKED``), so no act is read twice — neither by two workers nor by two API containers; a claim
left by a crashed run expires after ``LEASE``. Every request of every worker goes through one ``RateLimiter``
(``rate`` requests a second in all, never above ``MAX_RATE``; the robots Crawl-delay if it is longer), and each
worker keeps its own pause between its requests; a 429 or 503 pauses every worker (Retry-After, else back-off).
Each language's text is stored as ``zann/corpus/<code>.<lang>.txt.gz`` and described in ``zann_files`` (sha256,
chars, gzip bytes). A run is time-boxed; the next run continues; three errors in a row (across the workers) end
the run. At the end of a run that changed anything the manifest ``zann/corpus/manifest.jsonl.gz`` is rewritten.

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
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import quote

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import ZannAct, ZannFile, ZannListing
from ..lawagent.sources import ActNotFound, page_text
from ..official.crawler import Robots

log = logging.getLogger(__name__)

BASE = "https://old.adilet.zan.kz"
USER_AGENT = "Konsilier.AI Zann corpus collector (+https://konsilier.com; research; polite, honours 429/Retry-After)"
ROBOTS_TOKEN = "konsilier.ai zann corpus collector"
LANGS = {"ru": "rus", "kk": "kaz"}  # our code → the portal's path segment
MIN_CHARS = 300  # a shorter body means the portal has no text in this language (or a stub page)
PAGE_SIZE = 100
PREFIX = "zann/corpus/"
MANIFEST_KEY = PREFIX + "manifest.jsonl.gz"
MAX_ATTEMPTS = 3
MAX_ERRORS_IN_A_ROW = 3  # the portal is down or refusing: stop the run, the next one tries again
MAX_RATE = 3.0  # requests a second in all, whatever the settings say (owner 01.10.2026: up to 2–3 a second)
MAX_PAUSE = 900.0  # the longest Retry-After / back-off waited for in one go
LEASE = timedelta(hours=1)  # a claim («busy») older than this was left by a crashed run: back to the queue
BUSY = "busy"
CLAIM_TRIES = 5  # candidates tried when other workers keep winning the same act
IDLE_WAIT = 0.2  # a worker with nothing to do waits while another one may still find work (a listing page)
# Listings walked before this marker row was written were parsed with a pattern that dropped every code ending in
# letters (P260000007S — the Supreme Court, H19EK000237 …): they are walked once more, from page 1.
LISTINGS_MARKER = "#codes-with-letters"

# Priority tiers of act types (the portal's «вид акта» codes; НПВС is ours). Lower is collected first.
TIERS: tuple[tuple[str, ...], ...] = (
    ("КОД", "КОНС", "КЗАК", "УКОН"),          # 0: codes, the Constitution, constitutional laws
    ("ЗАК", "УЗАК"),                         # 1: laws, decrees having the force of law
    ("НПВС",),                               # 2: normative resolutions of the Supreme Court (no personal data)
    ("УКАЗ", "ПОСТ", "НПОС", "ПРИК", "РАСП"),  # 3: main by-laws: decrees, resolutions, orders, directives
)
# The index filter of a type label when it is not simply ``va=<label>``. kv=1_105 is the issuing body «Верховный Суд»
# (the Supreme Court) among the index's filters: 215 normative resolutions in force on 01.10.2026.
FILTERS = {"НПВС": "va=НПОС&kv=1_105"}
REST_TIER = len(TIERS)  # 4: everything else, from one listing of the status
STATUSES = {"in_force": "new|upd", "lost": "yts|stp"}
LOST_OFFSET = REST_TIER + 1  # lost-force acts come after every act in force

ARTICLE_TAG_RE = re.compile(r"(?is)<article\b[^>]*>(.*?)</article>")
TITLE_RE = re.compile(r"(?is)<title>(.*?)</title>")
KK_TITLE_SUFFIX_RE = re.compile(r"\s*-\s*\"?Әділет\"?\s*АҚЖ.*$")
KK_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
FOUND_RE = re.compile(r"Найдено:\s*<strong>(\d+)</strong>")
# act codes: K1500000414, Z999999999_, P260000007S, P99000010S_, H19EK000237, G26GI00569M …
ITEM_RE = re.compile(
    r'(?s)<h4 class="post_header">.*?<a href="/rus/docs/([A-Za-z0-9_]{4,16})">(.*?)</a>\s*</h4>'
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


def _filter(label: str) -> str:
    """The index filter of a type label, URL-quoted: va=%D0%97%D0%90%D0%9A, or va=…&kv=1_105 for НПВС."""
    return quote(FILTERS.get(label, f"va={label}"), safe="=&_")


def listing_plan(statuses: list[str]) -> list[tuple[str, str, int]]:
    """[(listing key, act type, priority)] in walking order. The key is the index filter without the page."""
    plan: list[tuple[str, str, int]] = []
    for s in statuses:
        st = quote(STATUSES[s], safe="")
        offset = LOST_OFFSET if s == "lost" else 0
        for tier, types in enumerate(TIERS):
            for va in types:
                plan.append((f"st={st}&{_filter(va)}", va, offset + tier))
        plan.append((f"st={st}", "", offset + REST_TIER))
    return plan


def listing_url(key: str, page: int) -> str:
    return f"{BASE}/rus/index/docs/{key}&pagesize={PAGE_SIZE}&page={page}"


# ---------------------------------------------------------------------------------------------------- network
class RateLimiter:
    """One limit for every worker (and the robots.txt read): request starts are spaced at least ``interval``
    seconds apart — 1/rate, or the site's Crawl-delay when it is longer. ``pause`` holds every worker (a 429 or a
    503 from the portal); a worker that reserved a slot before the pause waits for its end too."""

    def __init__(self, rate: float, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rate = min(max(float(rate), 0.01), MAX_RATE)
        self.min_interval = 0.0  # the robots Crawl-delay
        self.clock, self.sleep = clock, sleep
        self.paused = 0  # how many times the portal made everyone wait
        self._lock = threading.Lock()
        self._next = 0.0
        self._paused_until = 0.0

    @property
    def interval(self) -> float:
        return max(1.0 / self.rate, self.min_interval)

    def acquire(self) -> float:
        """Wait for this request's turn; returns the clock time of the slot."""
        while True:
            with self._lock:
                now = self.clock()
                slot = max(now, self._next, self._paused_until)
                self._next = slot + self.interval
            if slot > now:
                self.sleep(slot - now)
            with self._lock:
                if self.clock() >= self._paused_until:
                    return slot

    def pause(self, seconds: float) -> None:
        with self._lock:
            until = self.clock() + min(max(seconds, 0.0), MAX_PAUSE)
            if until > self._paused_until:
                self._paused_until = until
                self.paused += 1
            self._next = max(self._next, self._paused_until)


def retry_after(value: str, now: Callable[[], datetime] = utcnow) -> float | None:
    """Seconds from a Retry-After header: «120» or an HTTP date. None when absent or unreadable."""
    value = (value or "").strip()
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, (parsedate_to_datetime(value) - now()).total_seconds())
    except (TypeError, ValueError, IndexError):
        return None


class PoliteFetcher:
    """A pause between the requests of each worker (thread), one ``RateLimiter`` for all of them, retries with
    back-off on 429/5xx and network errors. A 429 or 503 pauses every worker that shares the limiter."""

    def __init__(self, delay: float = 3.0, retries: int = 3, timeout: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep, client: httpx.Client | None = None,
                 user_agent: str = USER_AGENT, limiter: RateLimiter | None = None):
        self.delay, self.retries, self.sleep, self.limiter = delay, retries, sleep, limiter
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                             headers={"User-Agent": user_agent})
        self._local = threading.local()  # the last request of this worker

    def __call__(self, url: str) -> str:
        for attempt in range(self.retries + 1):
            wait = getattr(self._local, "last", 0.0) + self.delay - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            if self.limiter is not None:
                self.limiter.acquire()
            self._local.last = time.monotonic()
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
                after = retry_after(r.headers.get("Retry-After", ""))
                backoff = min(after if after is not None else self.delay * 2 ** (attempt + 1), MAX_PAUSE)
                everyone = self.limiter is not None and r.status_code in (429, 503)
                if everyone:  # the portal asks us to slow down: every worker waits, not only this one
                    self.limiter.pause(backoff)
                if attempt == self.retries:
                    r.raise_for_status()
                if not everyone:
                    self.sleep(backoff)
                continue
            r.raise_for_status()
            return r.text
        raise RuntimeError("unreachable")


_REQUESTS: deque[float] = deque()  # monotonic times of this process's requests to the portal, the last hour
_REQUESTS_LOCK = threading.Lock()


def _note_request(t: float | None = None) -> None:
    t = time.monotonic() if t is None else t
    with _REQUESTS_LOCK:
        _REQUESTS.append(t)
        while _REQUESTS and _REQUESTS[0] < t - 3600:
            _REQUESTS.popleft()


def requests_last_hour(t: float | None = None) -> int:
    t = time.monotonic() if t is None else t
    with _REQUESTS_LOCK:
        return sum(1 for x in _REQUESTS if x >= t - 3600)


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
    requests: int = 0       # requests to the portal (robots.txt, listing pages, act pages; retries not counted)
    seconds: float = 0.0    # how long the run took
    requests_per_hour: int = 0
    workers: int = 1
    stopped: str = ""       # why the run ended: budget | limit | idle | robots | errors (the portal is failing)

    def add(self, other: RunStats) -> None:
        for f in ("listing_pages", "discovered", "requeued", "acts", "saved", "unchanged", "missing", "errors",
                  "bytes"):
            setattr(self, f, getattr(self, f) + getattr(other, f))


def desired_priority(act_type: str, status: str) -> int:
    """The tier of an act from the listing that found it (its type label) and its status."""
    tier = next((i for i, types in enumerate(TIERS) if act_type in types), REST_TIER)
    return tier + (LOST_OFFSET if status in STATUSES["lost"].split("|") else 0)


class Collector:
    """Discovery and collection by one or more workers, state in the database, texts in the storage."""

    def __init__(self, session_factory: sessionmaker[Session], storage: Any, fetch: Fetch, *,
                 langs: tuple[str, ...] = ("ru", "kk"), statuses: tuple[str, ...] = ("in_force",),
                 refresh_days: int = 30, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = utcnow, concurrency: int = 1):
        bad = [x for x in langs if x not in LANGS] + [x for x in statuses if x not in STATUSES]
        if bad or not langs or not statuses:
            raise ValueError(f"zann corpus: unknown languages or statuses {bad or (langs, statuses)}")
        self.sf, self.storage, self.fetch = session_factory, storage, fetch
        self.langs, self.plan = langs, listing_plan(list(statuses))
        self.refresh = timedelta(days=refresh_days) if refresh_days > 0 else None
        self.clock, self.now = clock, now
        self.concurrency = max(1, int(concurrency))
        self._robots: Any = None
        self._robots_lock = threading.Lock()
        self._mu = threading.Lock()  # the run's shared state below
        self._failed: set[str] = set()  # acts that failed in this run: retried by a later run, not at once
        self._claims: dict[str, tuple[str, datetime | None]] = {}  # code → its state and fetched_at before the claim
        self._reset_run_state(None)

    def _reset_run_state(self, limit: int | None) -> None:
        self._stop = ""
        self._in_a_row = 0
        self._claimed = 0
        self._limit = limit
        self._listing_busy = False
        self._active = 0
        self._requests = 0

    # ---- requests to the portal, counted
    def _get(self, url: str) -> str:
        with self._mu:
            self._requests += 1
        _note_request()
        return self.fetch(url)

    # ---- robots.txt of the mirror, read once per run
    def allowed(self, url: str) -> bool:
        with self._robots_lock:
            if self._robots is None:
                try:
                    self._robots = Robots.parse(self._get(f"{BASE}/robots.txt"), ROBOTS_TOKEN)
                except ActNotFound:
                    self._robots = Robots()
                delay = self._robots.crawl_delay
                if delay and hasattr(self.fetch, "delay"):  # the site's Crawl-delay, if longer
                    self.fetch.delay = max(self.fetch.delay, delay)
                limiter = getattr(self.fetch, "limiter", None)
                if delay and limiter is not None:  # … and for every worker together
                    limiter.min_interval = max(limiter.min_interval, delay)
            robots = self._robots
        return robots.allowed(url)

    def run(self, budget_seconds: float | None = None, limit: int | None = None,
            discover_only: bool = False) -> RunStats:
        stats = RunStats()
        t0 = self.clock()
        deadline = t0 + budget_seconds if budget_seconds else None
        self._robots, self._failed, self._claims = None, set(), {}
        self._reset_run_state(limit)
        workers = 1 if discover_only else self.concurrency
        stats.workers = workers
        started = time.monotonic()
        try:
            self._prepare()
            if workers == 1:
                self._work(stats, deadline, discover_only)
            else:
                threads = [threading.Thread(target=self._work, args=(stats, deadline, discover_only),
                                            name=f"zann-corpus-{i + 1}", daemon=True) for i in range(workers)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
        finally:
            stats.stopped = self._stop or "idle"
            stats.requests = self._requests
            stats.seconds = round(time.monotonic() - started, 1)
            stats.requests_per_hour = round(stats.requests * 3600 / stats.seconds) if stats.seconds >= 1 else 0
            if stats.saved or stats.discovered or stats.requeued:
                try:
                    self.write_manifest()
                except Exception:
                    log.exception("zann corpus: manifest not written")
        return stats

    # ---- one worker: steps until the run stops or there is nothing left for it
    def _work(self, stats: RunStats, deadline: float | None, discover_only: bool) -> None:
        while True:
            with self._mu:
                if not self._stop:
                    if self._in_a_row >= MAX_ERRORS_IN_A_ROW:
                        self._stop = "errors"
                    elif deadline is not None and self.clock() >= deadline:
                        self._stop = "budget"
                    elif self._limit is not None and self._claimed >= self._limit:
                        self._stop = "limit"
                if self._stop:
                    return
                self._active += 1
            step: tuple[str, Any] | None = None
            st = RunStats()
            ok = True
            try:
                step = self._next_step(discover_only)
                if step is not None:
                    kind, arg = step
                    if kind == "listing":
                        ok = self._listing_page(arg, st)
                    else:
                        try:
                            ok = self._act(arg, st)
                        except Exception as e:  # the storage or the database failed: the act goes back to retry
                            log.exception("zann corpus: act %s failed", arg)
                            self._fail(arg, f"{type(e).__name__}: {e}"[:500])
                            st.errors += 1
                        if not ok:
                            self._release(arg)
            except Exception:
                log.exception("zann corpus: step failed")
                st.errors += 1
            finally:
                with self._mu:
                    self._active -= 1
                    if step is not None and step[0] == "listing":
                        self._listing_busy = False
                    stats.add(st)
                    if not ok and not self._stop:
                        self._stop = "robots"
                    if step is not None:
                        self._in_a_row = self._in_a_row + 1 if st.errors else 0
                    others = self._active > 0
            if step is None:
                if self.concurrency > 1 and others:
                    time.sleep(IDLE_WAIT)  # another worker may still discover acts (a listing page)
                    continue
                return

    # ---- before the first step: one-time fixes, stale listings and claims
    def _prepare(self) -> None:
        now = self.now()
        with self.sf() as s:
            if s.get(ZannListing, LISTINGS_MARKER) is None:
                # the listings were walked with the old code pattern, and the tiers changed (НПВС): walk them all
                # again from page 1 and give the known acts and listings their new priorities
                for row in s.scalars(select(ZannListing)):
                    row.done_at, row.next_page, row.errors = None, 1, 0
                    row.priority = desired_priority(row.act_type, "yts" if row.key.startswith("st=yts") else "new")
                for act_type, status, prio in s.execute(select(ZannAct.act_type, ZannAct.status, ZannAct.priority)
                                                        .distinct()).all():
                    want = desired_priority(act_type, status)
                    if want != prio:
                        s.execute(update(ZannAct).where(ZannAct.act_type == act_type, ZannAct.status == status,
                                                        ZannAct.priority == prio).values(priority=want))
                s.add(ZannListing(key=LISTINGS_MARKER, act_type="", priority=-1, next_page=1, done_at=now))
                try:
                    s.commit()
                except IntegrityError:  # another container did it at the same moment
                    s.rollback()
            # a claim older than LEASE was left by a run that crashed: the act goes back to the queue
            s.execute(update(ZannAct).where(ZannAct.state == BUSY, or_(ZannAct.fetched_at.is_(None),
                                                                       ZannAct.fetched_at < now - LEASE))
                      .values(state="pending").execution_options(synchronize_session=False))
            s.commit()
        self._restart_stale_listings()

    # ---- what to do next: a listing page of a tier not below the queue's head, else the queue's head
    def _next_step(self, discover_only: bool) -> tuple[str, Any] | None:
        with self.sf() as s:
            done = {k for (k,) in s.execute(select(ZannListing.key).where(ZannListing.done_at.is_not(None)))}
            listing = next(((k, va, prio) for k, va, prio in self.plan if k not in done), None)
            if discover_only:
                return ("listing", listing) if listing and self._take_listing() else None
            head = s.scalar(select(ZannAct.priority).where(ZannAct.state == "pending")
                            .order_by(ZannAct.priority, ZannAct.code).limit(1))
        if listing and (head is None or listing[2] <= head) and self._take_listing():
            return "listing", listing
        code = self._claim_act()
        if code:
            return "act", code
        return ("listing", listing) if listing and self._take_listing() else None

    def _take_listing(self) -> bool:
        """One worker of this run walks the index at a time (the next page depends on the last one)."""
        with self._mu:
            if self._listing_busy:
                return False
            self._listing_busy = True
            return True

    def _claim_act(self) -> str | None:
        with self._mu:
            if self._limit is not None and self._claimed >= self._limit:
                return None
            self._claimed += 1  # reserved: a run with a limit never reads more acts than that
            failed = list(self._failed)
        code = None
        try:
            code = self._claim_from_db(failed)
        finally:
            if code is None:
                with self._mu:
                    self._claimed -= 1
        return code

    def _candidate(self, s: Session, failed: list[str], now: datetime) -> tuple[Any, ...] | None:
        """(code, state, fetched_at) of the next act to read: the queue, then failed acts, then old texts."""
        def first(q: Any) -> Any:
            return s.execute(q.limit(1).with_for_update(skip_locked=True)).first()  # SKIP LOCKED: PostgreSQL only
        cols = (ZannAct.code, ZannAct.state, ZannAct.fetched_at)
        row = first(select(*cols).where(ZannAct.state == "pending").order_by(ZannAct.priority, ZannAct.code))
        if row:
            return tuple(row)
        q = select(*cols).where(ZannAct.state == "error", ZannAct.attempts < MAX_ATTEMPTS)
        if failed:
            q = q.where(ZannAct.code.not_in(failed))
        row = first(q.order_by(ZannAct.priority, ZannAct.code))
        if row or self.refresh is None:
            return tuple(row) if row else None
        row = first(select(*cols).where(ZannAct.state == "done", ZannAct.fetched_at < now - self.refresh)
                    .order_by(ZannAct.fetched_at, ZannAct.code))
        return tuple(row) if row else None

    def _claim_from_db(self, failed: list[str]) -> str | None:
        """Mark one act «busy» for this worker. The conditional UPDATE is the claim: of two workers (or two
        containers) that picked the same candidate, only one changes the row; the other tries the next one."""
        now = self.now()
        with self.sf() as s:
            for _ in range(CLAIM_TRIES):
                cand = self._candidate(s, failed, now)
                if cand is None:
                    s.rollback()
                    return None
                code, state, fetched_at = cand
                q = update(ZannAct).where(ZannAct.code == code, ZannAct.state == state)
                if state == "error":
                    q = q.where(ZannAct.attempts < MAX_ATTEMPTS)
                if state == "done" and self.refresh is not None:
                    q = q.where(ZannAct.fetched_at < now - self.refresh)
                res = s.execute(q.values(state=BUSY, fetched_at=now).execution_options(synchronize_session=False))
                s.commit()
                if res.rowcount == 1:
                    with self._mu:
                        self._claims[code] = (state, fetched_at)
                    return code
        return None

    def _release(self, code: str) -> None:
        """Give a claimed act back as it was (the run stopped before reading it)."""
        with self._mu:
            prev = self._claims.pop(code, None)
        if prev is None:
            return
        with self.sf() as s:
            s.execute(update(ZannAct).where(ZannAct.code == code, ZannAct.state == BUSY)
                      .values(state=prev[0], fetched_at=prev[1]).execution_options(synchronize_session=False))
            s.commit()

    def _fail(self, code: str, error: str) -> None:
        with self._mu:
            self._claims.pop(code, None)
            self._failed.add(code)
        with self.sf() as s:
            act = s.get(ZannAct, code)
            if act is not None:
                act.state, act.attempts, act.error = "error", (act.attempts or 0) + 1, error
                s.commit()

    def _restart_stale_listings(self) -> None:
        """Walk a listing again once it is older than refresh_days: new acts, and changed ones back to the queue."""
        if self.refresh is None:
            return
        old = self.now() - self.refresh
        with self.sf() as s:
            for row in s.scalars(select(ZannListing).where(ZannListing.done_at.is_not(None),
                                                           ZannListing.key != LISTINGS_MARKER)):
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
            total, items = parse_listing(self._get(url))
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
                        if va:
                            act.act_type = va  # the type of the listing that gives the act its tier
                    if not act.act_type and va:
                        act.act_type = va
                act.listed_at = now
            row.pages, row.errors = pages, 0
            if not items or (row.total is not None and page >= pages):
                row.done_at, row.next_page = now, 1
            else:
                row.next_page = page + 1
            s.merge(row)
            try:
                s.commit()
            except IntegrityError:  # another container added the same act a moment ago: the page is read again
                s.rollback()
                log.info("zann corpus: listing %s page %s raced with another collector", key, page)
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
                title, text = extract_act(self._get(url))
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
                with self._mu:
                    self._claims.pop(code, None)
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
                with self._mu:
                    self._failed.add(code)
            else:
                act.state = "done" if any(results.values()) or s.scalar(
                    select(func.count()).select_from(ZannFile).where(ZannFile.code == code)) else "missing"
                act.error = error or None
            s.commit()
        with self._mu:
            self._claims.pop(code, None)
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


def corpus_metrics(session: Session, now: datetime | None = None) -> dict[str, Any]:
    """Counts for /v1/admin/metrics["zann"]: acts known and by state, files, bytes, discovery progress, and the
    pace: acts and files read in the last hour (database) and requests to the portal in the last hour (this
    process — the collector runs in the API process)."""
    now = now or utcnow()
    hour_ago = now - timedelta(hours=1)
    states = dict(session.execute(select(ZannAct.state, func.count()).group_by(ZannAct.state)).all())
    by_lang = dict(session.execute(select(ZannFile.lang, func.count()).group_by(ZannFile.lang)).all())
    files, gz, chars = session.execute(select(func.count(), func.coalesce(func.sum(ZannFile.bytes), 0),
                                              func.coalesce(func.sum(ZannFile.chars), 0))).one()
    done_types = dict(session.execute(select(ZannAct.act_type, func.count()).where(ZannAct.state == "done")
                                      .group_by(ZannAct.act_type)).all())
    listings = session.execute(select(func.count(), func.count(ZannListing.done_at))
                               .where(ZannListing.key != LISTINGS_MARKER)).one()
    last = session.scalar(select(func.max(ZannFile.fetched_at)))
    acts_hour = session.scalar(select(func.count()).select_from(ZannAct).where(
        ZannAct.state.in_(("done", "missing", "error")), ZannAct.fetched_at >= hour_ago))
    files_hour = session.scalar(select(func.count()).select_from(ZannFile).where(ZannFile.fetched_at >= hour_ago))
    return {
        "acts": sum(states.values()),
        "acts_done": states.get("done", 0),
        "acts_pending": states.get("pending", 0),
        "acts_busy": states.get(BUSY, 0),
        "acts_missing": states.get("missing", 0),
        "acts_error": states.get("error", 0),
        "done_by_type": {k or "другое": v for k, v in done_types.items()},
        "files": files,
        "files_by_lang": by_lang,
        "bytes": int(gz),
        "chars": int(chars),
        "listings": {"started": listings[0], "done": listings[1]},
        "last_fetched_at": _aware(last).isoformat(timespec="seconds") if last else None,
        "acts_last_hour": int(acts_hour or 0),
        "files_last_hour": int(files_hour or 0),
        "requests_last_hour": requests_last_hour(),
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
    concurrency = max(1, int(getattr(settings, "zann_corpus_concurrency", 1)))
    if fetch is None:
        limiter = RateLimiter(min(float(getattr(settings, "zann_corpus_rate", 0.5)), MAX_RATE))
        fetch = PoliteFetcher(delay=max(2.0, settings.zann_corpus_pause), limiter=limiter)
    return Collector(session_factory, storage, fetch, langs=langs, statuses=statuses,
                     refresh_days=settings.zann_corpus_refresh_days, concurrency=concurrency)
