"""Zann law corpus (konsilier/zann/corpus.py): discovery from the adilet index, the priority queue, gzip texts in
the storage, resume, changed-only refresh, robots.txt, the nightly / continuous job — all without network."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from konsilier.core.adapters.storage import LocalStorage
from konsilier.core.db import make_engine, make_session_factory
from konsilier.core.models import Base, ZannAct, ZannFile, ZannListing
from konsilier.zann import corpus
from konsilier.zann.corpus import (MANIFEST_KEY, Collector, PoliteFetcher, ZannCorpusJob, corpus_metrics,
                                   listing_plan, parse_listing)

from .test_zann_collect_laws import BODY_KK, BODY_RU, page

TZ = ZoneInfo("Asia/Almaty")


def item(n: int, code: str, title: str, status: str = "upd", info: str = "") -> str:
    """One entry of an index page, in the portal's own markup (old.adilet.zan.kz/rus/index/docs/…)."""
    return (f'<div class="post_holder">\n<div class="hr"></div>\n<h4 class="post_header">\n'
            f'\t<span class="post_number">{n}.</span>\n\t<a href="/rus/docs/{code}">{title}</a>\n</h4>\n\n'
            f'<span class="status status_{status}">Статус</span>\n\n<p>{info}</p>\n</div>')


def listing_page(total: int, items: list[tuple]) -> str:
    body = "".join(item(i + 1, *it) for i, it in enumerate(items))
    return (f'<html><body><div class="gs_4 widget"><a href="/rus/docs/K1500000414">Трудовой кодекс</a></div>'
            f'<span class="onlyprint">Найдено: <strong>{total}</strong> документов</span>'
            f'<div class="serp">{body}</div><div class="wp-pagenavi"><a href="?page=2">2</a></div></body></html>')


CODES = [("K1500000414", "Трудовой кодекс Республики Казахстан", "upd", "Кодекс Республики Казахстан от 23 ноября 2015 года № 414-V ЗРК."),
         ("K1700000120", "О налогах (Налоговый кодекс)", "upd", "Кодекс Республики Казахстан от 25 декабря 2017 года № 120-VI.")]
CONST = [("K950001000_", "Конституция Республики Казахстан", "upd", "Конституция принята 30 августа 1995 года.")]
LAWS = [("Z1700000062", "О коллекторской деятельности", "new", "Закон Республики Казахстан от 6 мая 2017 года № 62-VI."),
        ("Z2400000106", "О государственных закупках", "new", "Закон Республики Казахстан от 1 июля 2024 года № 106-VIII."),
        ("Z999999999_", "Закон без текста на портале", "new", "Закон &quot;Об ином&quot;")]
OTHER = [("V2400035238", "Об утверждении Правил", "new", "Приказ Министра финансов от 9 октября 2024 года № 687")]


class Site:
    """old.adilet.zan.kz behind httpx.MockTransport: robots.txt, the index (page size 2) and the act pages."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.robots = "User-Agent: *\nDisallow: /rus/search/\nDisallow: /rus/list/docs/\n"
        self.listings = {"st=new|upd&va=КОД": CODES, "st=new|upd&va=КОНС": CONST, "st=new|upd&va=ЗАК": LAWS,
                         "st=new|upd": CODES + CONST + LAWS + OTHER}
        self.docs = {f"rus/docs/{c}": page(f"{t} - ИПС &quot;Әділет&quot;", BODY_RU)
                     for c, t, *_ in CODES + CONST + LAWS + OTHER if c != "Z999999999_"}
        self.docs["kaz/docs/K1500000414"] = page('Еңбек кодексі - "Әділет" АҚЖ', BODY_KK)
        self.docs["kaz/docs/Z1700000062"] = page("Коллекторлық қызмет туралы", BODY_KK)
        self.docs["kaz/docs/K1700000120"] = page("Налоговый кодекс", BODY_RU)  # Russian text on the kk page
        self.broken = {"rus/docs/V2400035238"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.raw_path.decode())
        self.requests.append(path)
        if path == "/robots.txt":
            return httpx.Response(200, text=self.robots)
        if path.startswith("/rus/index/docs/"):
            filt, _, rest = path[len("/rus/index/docs/"):].partition("&pagesize=")
            size, _, pg = rest.partition("&page=")
            rows = self.listings.get(filt, [])
            n, size = int(pg), int(size)
            return httpx.Response(200, text=listing_page(len(rows), rows[(n - 1) * size: n * size]))
        key = path.lstrip("/")
        if key in self.broken:
            return httpx.Response(500, text="busy")
        if key in self.docs:
            return httpx.Response(200, text=self.docs[key])
        return httpx.Response(404)


@pytest.fixture
def db(tmp_path):
    engine = make_engine(os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/zann.db")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def small_pages(monkeypatch):
    monkeypatch.setattr(corpus, "PAGE_SIZE", 2)


class CountingStorage(LocalStorage):
    def __init__(self, root) -> None:
        super().__init__(root)
        self.puts: list[str] = []

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.puts.append(key)
        return super().put(key, data, content_type)


def collector(db, tmp_path, site: Site, **kw) -> Collector:
    client = httpx.Client(transport=httpx.MockTransport(site), headers={"User-Agent": corpus.USER_AGENT})
    fetch = PoliteFetcher(delay=0, retries=0, sleep=lambda s: None, client=client)
    storage = kw.pop("storage", None) or CountingStorage(tmp_path / "files")
    return Collector(db, storage, fetch, **kw)


# ------------------------------------------------------------------ parsing
def test_parse_listing_reads_code_title_status_and_line():
    raw = listing_page(964, [("Z2400000088", "О ратификации &laquo;Протокола&raquo;", "new",
                              "Закон Республики Казахстан от 27 мая 2024 года № 88-VIII ЗРК"),
                             ("K100000296_", "О таможенном деле", "yts", "Кодекс. <b>Утратил силу</b>")])
    total, items = parse_listing(raw)
    assert total == 964
    assert [(i.code, i.status) for i in items] == [("Z2400000088", "new"), ("K100000296_", "yts")]
    assert items[0].title == "О ратификации «Протокола»" and items[1].info == "Кодекс. Утратил силу"
    assert parse_listing("<html>nothing</html>") == (None, [])  # the footer's popular acts are not entries


def test_listing_plan_puts_codes_first_then_laws_then_by_laws_then_the_rest():
    plan = listing_plan(["in_force"])
    assert [unquote(k) for k, _, _ in plan[:5]] == ["st=new|upd&va=КОД", "st=new|upd&va=КОНС", "st=new|upd&va=КЗАК",
                                                    "st=new|upd&va=УКОН", "st=new|upd&va=ЗАК"]
    assert [p for _, _, p in plan] == sorted(p for _, _, p in plan)
    assert plan[-1] == ("st=new%7Cupd", "", 3)
    lost = listing_plan(["in_force", "lost"])
    assert lost[-1] == ("st=yts%7Cstp", "", 7) and len(lost) == 2 * len(plan)
    with pytest.raises(ValueError):
        Collector(None, None, None, statuses=("everything",))


# ------------------------------------------------------------------ collection
def test_collects_codes_first_stores_gzip_texts_and_a_manifest(db, tmp_path, small_pages):
    site = Site()
    c = collector(db, tmp_path, site)
    stats = c.run()
    assert stats.stopped == "idle" and stats.errors == 1  # the act whose page always answers 500
    req = site.requests
    assert req[0] == "/robots.txt" and req.count("/robots.txt") == 1
    # codes (and the Constitution) are read before the laws' listing is even opened, laws before the rest
    first_law_listing = next(i for i, r in enumerate(req) if "va=ЗАК" in r)
    assert req.index("/rus/docs/K1500000414") < first_law_listing
    assert req.index("/rus/docs/K950001000_") < first_law_listing
    first_rest = next(i for i, r in enumerate(req) if r.startswith("/rus/index/docs/st=new|upd&pagesize"))
    assert req.index("/rus/docs/Z1700000062") < first_rest < req.index("/rus/docs/V2400035238")
    assert not any("/search/" in r or "/list/docs/" in r for r in req)

    with db() as s:
        acts = {a.code: a for a in s.scalars(select(ZannAct))}
        files = {(f.code, f.lang): f for f in s.scalars(select(ZannFile))}
    assert len(acts) == 7  # the catch-all listing found one more act, and no duplicates
    assert acts["K1500000414"].act_type == "КОД" and acts["K1500000414"].priority == 0
    assert acts["Z1700000062"].act_type == "ЗАК" and acts["Z1700000062"].priority == 1
    assert acts["V2400035238"].act_type == "" and acts["V2400035238"].priority == 3
    assert acts["Z999999999_"].state == "missing" and acts["Z999999999_"].info == 'Закон "Об ином"'
    assert acts["V2400035238"].state == "error" and acts["V2400035238"].attempts == 1
    assert acts["K1500000414"].state == "done" and acts["K1500000414"].status == "upd"
    assert set(files) == {("K1500000414", "ru"), ("K1500000414", "kk"), ("K1700000120", "ru"), ("K950001000_", "ru"),
                          ("Z1700000062", "ru"), ("Z1700000062", "kk"), ("Z2400000106", "ru")}

    f = files[("K1500000414", "kk")]
    text = gzip.decompress((tmp_path / "files" / "zann/corpus/K1500000414.kk.txt.gz").read_bytes()).decode()
    assert f.key == "zann/corpus/K1500000414.kk.txt.gz" and f.url == "https://old.adilet.zan.kz/kaz/docs/K1500000414"
    assert f.sha256 == hashlib.sha256(text.encode()).hexdigest() and f.chars == len(text) and "1-бап." in text
    assert f.bytes == (tmp_path / "files" / f.key).stat().st_size and f.title == "Еңбек кодексі"

    rows = [json.loads(x) for x in gzip.decompress((tmp_path / "files" / MANIFEST_KEY).read_bytes()).splitlines()]
    assert len(rows) == 7 and {"code", "title", "type", "status", "lang", "url", "fetched_at", "sha256",
                               "chars"} <= set(rows[0])
    labour = next(r for r in rows if r["code"] == "K1500000414" and r["lang"] == "ru")
    assert labour["type"] == "КОД" and labour["title"] == "Трудовой кодекс Республики Казахстан"

    with db() as s:
        m = corpus_metrics(s)
    assert m["acts"] == 7 and m["acts_done"] == 5 and m["acts_missing"] == 1 and m["acts_error"] == 1
    assert m["files"] == 7 and m["files_by_lang"] == {"ru": 5, "kk": 2} and m["bytes"] > 0
    assert m["done_by_type"] == {"КОД": 2, "КОНС": 1, "ЗАК": 2}
    assert m["listings"]["done"] == len(listing_plan(["in_force"])) and m["last_fetched_at"]


def test_runs_are_time_boxed_and_resume_where_they_stopped(db, tmp_path, small_pages):
    site = Site()
    ticks = iter(range(10_000))
    c = collector(db, tmp_path, site, clock=lambda: float(next(ticks)))
    first = c.run(budget_seconds=4)  # a few steps only
    assert first.stopped == "budget"
    with db() as s:
        started = {r.key: r.next_page for r in s.scalars(select(ZannListing))}
    assert started  # the listing progress is kept in the database
    second = collector(db, tmp_path, site).run(limit=2)
    assert second.stopped == "limit" and second.acts == 2
    rest = collector(db, tmp_path, site).run()
    assert rest.stopped == "idle"
    with db() as s:
        assert s.query(ZannAct).count() == 7 and s.query(ZannFile).count() == 7
    docs = [r for r in site.requests if r.startswith("/rus/docs/")]
    others = [r for r in docs if "V2400035238" not in r]  # the act answering 500 is retried on the next runs
    assert len(others) == len(set(others))  # nothing else is read twice


def test_refresh_uploads_only_changed_texts_and_requeues_changed_listings(db, tmp_path, small_pages):
    site = Site()
    storage = CountingStorage(tmp_path / "files")
    t = [datetime(2026, 10, 1, tzinfo=timezone.utc)]
    c = collector(db, tmp_path, site, storage=storage, now=lambda: t[0], refresh_days=30)
    c.run()
    uploads = [k for k in storage.puts if k != MANIFEST_KEY]
    assert len(uploads) == 7

    # same day: nothing to do, nothing uploaded
    storage.puts.clear()
    assert c.run().stopped == "idle" and storage.puts == []

    # a month later: the listings are walked again; the Labour Code is «updated» with a new text
    t[0] += timedelta(days=31)
    site.listings["st=new|upd&va=КОД"] = [("K1500000414", CODES[0][1], "upd", CODES[0][3] + " Изменения от 01.11.2026"),
                                          CODES[1]]
    site.docs["rus/docs/K1500000414"] = page("Трудовой кодекс", BODY_RU + "<p>Статья 999. Новая статья</p>")
    site.broken.clear()
    stats = c.run()
    assert stats.requeued >= 1
    uploads = [k for k in storage.puts if k != MANIFEST_KEY]
    assert "zann/corpus/K1500000414.ru.txt.gz" in uploads and "zann/corpus/V2400035238.ru.txt.gz" in uploads
    assert stats.unchanged >= 5  # every other text re-read (older than 30 days) and left as it was
    assert "zann/corpus/Z1700000062.ru.txt.gz" not in uploads
    text = gzip.decompress((tmp_path / "files/zann/corpus/K1500000414.ru.txt.gz").read_bytes()).decode()
    assert "Статья 999" in text


def test_robots_txt_is_obeyed(db, tmp_path, small_pages):
    site = Site()
    site.robots = "User-agent: *\nDisallow: /rus/index/\n"
    stats = collector(db, tmp_path, site).run()
    assert stats.stopped == "robots" and site.requests == ["/robots.txt"]
    site2 = Site()
    site2.robots = "User-agent: *\nDisallow:\nCrawl-delay: 7\n"
    c = collector(db, tmp_path, site2)
    assert c.allowed(corpus.doc_url("K1500000414", "ru"))
    assert c.fetch.delay == 7  # the site's Crawl-delay wins over a shorter pause


def test_a_failing_portal_stops_the_run_and_a_broken_page_is_skipped_later(db, tmp_path, small_pages):
    site = Site()
    site.broken = {"rus/index/docs/st=new|upd&va=КОД&pagesize=2&page=1"}
    original = site.__call__

    class Down(Site):
        def __call__(self, request):
            path = unquote(request.url.raw_path.decode())
            if path.lstrip("/") in site.broken:
                site.requests.append(path)
                return httpx.Response(503)
            return original(request)
    stats = collector(db, tmp_path, Down()).run()
    assert stats.stopped == "errors" and stats.errors == 3 and stats.acts == 0
    with db() as s:
        row = s.get(ZannListing, "st=new%7Cupd&va=%D0%9A%D0%9E%D0%94")
        assert row.next_page == 2 and row.done_at is None  # three failures: the page is skipped, not retried forever


def test_discover_only_reads_the_index_and_no_texts(db, tmp_path, small_pages):
    site = Site()
    stats = collector(db, tmp_path, site).run(discover_only=True)
    assert stats.stopped == "idle" and stats.discovered == 7 and stats.acts == 0
    assert not any(r.startswith(("/rus/docs/", "/kaz/docs/")) for r in site.requests)
    with db() as s:
        assert {a.state for a in s.scalars(select(ZannAct))} == {"pending"}


# ------------------------------------------------------------------ the job
class FakeCollector:
    def __init__(self, stopped: str = "budget") -> None:
        self.runs, self.stopped = [], stopped
        self.fetch = None

    def run(self, budget_seconds=None, **kw):
        self.runs.append(budget_seconds)
        return corpus.RunStats(stopped=self.stopped)


def test_nightly_job_runs_once_at_the_local_hour():
    started, fake = [], FakeCollector()
    job = ZannCorpusJob(lambda: fake, TZ, hour=2, minutes=50, start=started.append)
    assert job(None, datetime(2026, 10, 1, 1, 59, tzinfo=TZ)) == 0 and started == []
    job(None, datetime(2026, 10, 1, 2, 0, tzinfo=TZ))
    job(None, datetime(2026, 10, 1, 2, 1, tzinfo=TZ))  # still running
    assert len(started) == 1
    started[0]()
    assert fake.runs == [50 * 60] and job.last.stopped == "budget"
    job(None, datetime(2026, 10, 1, 2, 30, tzinfo=TZ))
    assert len(started) == 1  # once a night
    job(None, datetime(2026, 10, 2, 2, 5, tzinfo=TZ))
    assert len(started) == 2


def test_continuous_job_runs_back_to_back_and_rests_when_idle():
    started, fake = [], FakeCollector()
    job = ZannCorpusJob(lambda: fake, TZ, hour=-1, minutes=30, start=started.append)
    t = datetime(2026, 9, 30, 18, 0, tzinfo=TZ)
    job(None, t)
    job(None, t + timedelta(minutes=1))
    assert len(started) == 1  # a run is going
    started[0]()
    job(None, t + timedelta(minutes=31))
    assert len(started) == 2  # the next slice starts on the next tick, at any hour
    fake.stopped = "idle"
    started[1]()
    job(None, t + timedelta(minutes=62))
    assert len(started) == 2  # nothing to do: rest for an hour
    job(None, t + timedelta(minutes=31 + 61))
    assert len(started) == 3


def test_container_wires_the_job_only_when_enabled(ctx):
    from konsilier.config import Settings
    from konsilier.container import build_container
    from konsilier.core.documents import NullPdfConverter
    from konsilier.core.llm.mock import HeuristicMockProvider

    assert not any(isinstance(j, ZannCorpusJob) for j in ctx.container.scheduler.extra_jobs)  # off by default
    s = ctx.settings.model_copy(update={"zann_corpus_enabled": True, "zann_corpus_hour": -1})
    c = build_container(Settings(**s.model_dump()), llm=HeuristicMockProvider(), pdf=NullPdfConverter())
    job = next(j for j in c.scheduler.extra_jobs if isinstance(j, ZannCorpusJob))
    assert job.hour == -1 and job.minutes == 50 and str(job.tz) == "Asia/Almaty"
    made = job.make_collector()
    assert made.langs == ("ru", "kk") and made.fetch.delay == 3.0
    made.fetch.client.close()
    c.engine_db.dispose()


def test_admin_metrics_include_the_corpus(ctx):
    from tests.test_e2e import ADMIN

    m = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()
    assert m["zann"]["acts"] == 0 and m["zann"]["files"] == 0 and m["zann"]["bytes"] == 0
    assert set(asdict(corpus.RunStats())) >= {"saved", "bytes", "stopped"}
