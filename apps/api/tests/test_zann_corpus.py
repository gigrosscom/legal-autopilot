"""Zann law corpus (konsilier/zann/corpus.py): discovery from the adilet index, the priority queue, gzip texts in
the storage, resume, changed-only refresh, robots.txt, the nightly / continuous job — all without network."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any
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
    assert plan[-1] == ("st=new%7Cupd", "", 4)
    lost = listing_plan(["in_force", "lost"])
    assert lost[-1] == ("st=yts%7Cstp", "", 9) and len(lost) == 2 * len(plan)
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
    assert acts["V2400035238"].act_type == "" and acts["V2400035238"].priority == 4
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
    assert "requests_last_hour" in m["zann"] and "acts_last_hour" in m["zann"]
    assert set(asdict(corpus.RunStats())) >= {"saved", "bytes", "stopped", "requests", "requests_per_hour"}


# ------------------------------------------------------------------ speed (owner 01.10.2026: the corpus by 04.10)
SUPREME = [("P260000007S", "О судебной практике применения законодательства об административном надзоре", "new",
            "Нормативное постановление Верховного Суда Республики Казахстан от 25 июня 2026 года № 7"),
           ("P99000010S_", "О практике применения законодательства о сроках", "upd",
            "Нормативное постановление Верховного Суда Республики Казахстан от 1 июля 1999 года № 10")]
BYLAWS = [("P2400000123", "Об утверждении Правил", "new", "Постановление Правительства от 1 марта 2024 года № 123")]


def test_codes_ending_in_letters_are_read_from_the_index():
    raw = listing_page(3, [SUPREME[0], SUPREME[1], ("H19EK000237", "Решение Евразийской комиссии", "new", "")])
    assert [i.code for i in parse_listing(raw)[1]] == ["P260000007S", "P99000010S_", "H19EK000237"]


def test_supreme_court_resolutions_are_a_tier_of_their_own_after_laws_before_by_laws():
    plan = listing_plan(["in_force"])
    sc = next(p for p in plan if p[1] == "НПВС")
    assert unquote(sc[0]) == "st=new|upd&va=НПОС&kv=1_105" and sc[2] == 2
    assert unquote(corpus.listing_url(sc[0], 1)).endswith(
        "/rus/index/docs/st=new|upd&va=НПОС&kv=1_105&pagesize=100&page=1")
    assert max(p for k, va, p in plan if va in ("ЗАК", "УЗАК")) < sc[2] < min(p for k, va, p in plan if va == "ПОСТ")
    assert corpus.desired_priority("НПВС", "new") == 2 and corpus.desired_priority("", "yts") == 9


def sc_site() -> Site:
    site = Site()
    site.listings["st=new|upd&va=НПОС&kv=1_105"] = SUPREME
    site.listings["st=new|upd&va=ПОСТ"] = BYLAWS
    site.listings["st=new|upd"] = CODES + CONST + LAWS + OTHER + SUPREME + BYLAWS
    for c, t, *_ in SUPREME + BYLAWS:
        site.docs[f"rus/docs/{c}"] = page(t, BODY_RU)
    return site


def test_supreme_court_resolutions_are_collected_after_laws_and_before_other_by_laws(db, tmp_path, small_pages):
    site = sc_site()
    stats = collector(db, tmp_path, site).run()
    assert stats.stopped == "idle"
    req = site.requests
    last_law = max(req.index(f"/rus/docs/{c}") for c, *_ in LAWS)
    sc = [req.index(f"/rus/docs/{c}") for c, *_ in SUPREME]
    assert last_law < min(sc) and max(sc) < req.index("/rus/docs/P2400000123") < req.index("/rus/docs/V2400035238")
    with db() as s:
        a = s.get(ZannAct, "P260000007S")
        assert a.act_type == "НПВС" and a.priority == 2 and a.state == "done"
        assert corpus_metrics(s)["done_by_type"]["НПВС"] == 2
    assert stats.requests == len(req) and stats.workers == 1


def test_an_old_database_is_walked_again_and_gets_the_new_priorities(db, tmp_path, small_pages):
    with db() as s:  # the state left by the collector before the Supreme Court tier and the code fix
        s.add(ZannListing(key="st=new%7Cupd&va=%D0%9F%D0%9E%D0%A1%D0%A2", act_type="ПОСТ", priority=2, next_page=1,
                          done_at=datetime.now(timezone.utc)))
        s.add(ZannListing(key="st=new%7Cupd", act_type="", priority=3, next_page=7))
        s.add(ZannAct(code="P2400000123", act_type="ПОСТ", status="new", priority=2, state="pending", attempts=0))
        s.add(ZannAct(code="V2400035238", act_type="", status="new", priority=3, state="pending", attempts=0))
        s.add(ZannAct(code="K1500000414", act_type="КОД", status="upd", priority=0, state="done", attempts=0))
        s.commit()
    c = collector(db, tmp_path, sc_site())
    c._prepare()
    with db() as s:
        rows = {r.key: r for r in s.scalars(select(ZannListing))}
        acts = {a.code: a.priority for a in s.scalars(select(ZannAct))}
    assert acts == {"P2400000123": 3, "V2400035238": 4, "K1500000414": 0}
    assert all(r.done_at is None and r.next_page == 1 for k, r in rows.items() if k != corpus.LISTINGS_MARKER)
    assert rows["st=new%7Cupd"].priority == 4 and corpus.LISTINGS_MARKER in rows
    with db() as s:  # once only: a listing walked after the fix is not walked again on the next run
        s.get(ZannListing, "st=new%7Cupd").done_at = datetime.now(timezone.utc)
        s.commit()
    c._prepare()
    with db() as s:
        assert s.get(ZannListing, "st=new%7Cupd").done_at is not None
        assert corpus_metrics(s)["listings"]["started"] == 2  # the marker row is not a listing


class SlowSite(Site):
    """The fake portal answers after a short delay and counts how many requests are in flight at once."""

    def __init__(self, n: int = 24) -> None:
        super().__init__()
        self.many = [(f"V24{i:08d}", f"Приказ {i}", "new", "") for i in range(n)]
        self.listings["st=new|upd"] = CODES + CONST + LAWS + OTHER + self.many
        for c, t, *_ in self.many:
            self.docs[f"rus/docs/{c}"] = page(t, BODY_RU)
        self.broken = set()
        self.in_flight = self.max_in_flight = 0
        self.lock = threading.Lock()

    def __call__(self, request):
        with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            time.sleep(0.01)
            with self.lock:
                return super().__call__(request)
        finally:
            with self.lock:
                self.in_flight -= 1


def test_workers_read_in_parallel_and_never_read_an_act_twice(db, tmp_path, small_pages):
    site = SlowSite()
    stats = collector(db, tmp_path, site, concurrency=4).run()
    assert stats.stopped == "idle" and stats.errors == 0 and stats.workers == 4
    docs = [r for r in site.requests if r.startswith(("/rus/docs/", "/kaz/docs/"))]
    assert len(docs) == len(set(docs)) == 2 * (7 + len(site.many))  # every act once, in both languages
    assert site.max_in_flight > 1 and site.requests.count("/robots.txt") == 1
    with db() as s:
        states = {a.state for a in s.scalars(select(ZannAct))}
        assert s.query(ZannAct).count() == 7 + len(site.many) and "busy" not in states and "pending" not in states
    assert stats.acts == 7 + len(site.many) and stats.requests == len(site.requests)


def test_two_collectors_on_one_database_never_claim_the_same_act(db, tmp_path, small_pages):
    """Two API containers (or two runs) on one database: the claim is a conditional UPDATE, one wins."""
    site = SlowSite(n=30)
    collector(db, tmp_path, site).run(discover_only=True)
    site.requests.clear()
    a = collector(db, tmp_path, site, concurrency=3)
    b = collector(db, tmp_path, site, concurrency=3)
    out: dict[str, Any] = {}
    threads = [threading.Thread(target=lambda k=k, c=c: out.__setitem__(k, c.run())) for k, c in (("a", a), ("b", b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    docs = [r for r in site.requests if r.startswith("/rus/docs/")]
    assert len(docs) == len(set(docs)) == 7 + 30
    assert out["a"].acts + out["b"].acts == 7 + 30 and out["a"].acts and out["b"].acts


def test_a_claim_is_exclusive_and_a_stale_claim_expires(db, tmp_path):
    t = [datetime(2026, 10, 1, 12, tzinfo=timezone.utc)]
    with db() as s:
        for code, prio in (("K1500000414", 0), ("Z1700000062", 1)):
            s.add(ZannAct(code=code, act_type="", status="new", priority=prio, state="pending", attempts=0))
        s.commit()
    one = collector(db, tmp_path, Site(), now=lambda: t[0])
    two = collector(db, tmp_path, Site(), now=lambda: t[0])
    assert one._claim_act() == "K1500000414" and two._claim_act() == "Z1700000062" and two._claim_act() is None
    with db() as s:
        assert {a.state for a in s.scalars(select(ZannAct))} == {"busy"}
    t[0] += timedelta(minutes=30)
    one._prepare()  # a claim younger than the lease is another collector's work in progress
    with db() as s:
        assert s.get(ZannAct, "K1500000414").state == "busy"
    t[0] += corpus.LEASE
    one._prepare()  # … an older one was left by a crashed run
    with db() as s:
        assert {a.state for a in s.scalars(select(ZannAct))} == {"pending"}


def test_rate_limiter_spaces_every_workers_requests():
    clock = [0.0]

    def sleep(s):
        clock[0] += s
    lim = corpus.RateLimiter(2.0, clock=lambda: clock[0], sleep=sleep)
    assert [lim.acquire() for _ in range(4)] == [0.0, 0.5, 1.0, 1.5]
    lim.min_interval = 2.0  # the robots Crawl-delay, when longer, wins
    assert lim.acquire() == 2.0 and lim.acquire() == 4.0
    assert corpus.RateLimiter(50).rate == corpus.MAX_RATE == 3.0  # never above 3 a second, whatever the settings

    real = corpus.RateLimiter(3.0)  # threads: the slots handed out are never closer than 1/rate
    slots: list[float] = []
    lock = threading.Lock()

    def worker():
        for _ in range(2):
            got = real.acquire()
            with lock:
                slots.append(got)
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    slots.sort()
    assert len(slots) == 8 and all(b - a >= 1 / 3 - 1e-9 for a, b in zip(slots, slots[1:]))


def test_429_pauses_every_worker_for_retry_after():
    clock = [0.0]

    def sleep(s):
        clock[0] += s
    lim = corpus.RateLimiter(3.0, clock=lambda: clock[0], sleep=sleep)
    answers = [httpx.Response(429, headers={"Retry-After": "30"}), httpx.Response(200, text="ok")]
    client = httpx.Client(transport=httpx.MockTransport(lambda r: answers.pop(0)))
    fetch = PoliteFetcher(delay=0, retries=2, sleep=sleep, client=client, limiter=lim)
    assert fetch("https://old.adilet.zan.kz/rus/docs/K1500000414") == "ok"
    assert lim.paused == 1 and clock[0] >= 30  # this worker waited for the portal …
    lim.pause(60)
    assert lim.acquire() >= 90 and clock[0] >= 90  # … and every other worker sharing the limiter waits too
    assert corpus.retry_after("120") == 120 and corpus.retry_after("") is None
    assert corpus.retry_after("Wed, 01 Oct 2026 12:01:00 GMT",
                              now=lambda: datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)) == 60
    # a 500 is this worker's own back-off; a 503 holds everyone
    answers[:] = [httpx.Response(500), httpx.Response(503, headers={"Retry-After": "5"}),
                  httpx.Response(200, text="ok")]
    assert fetch("https://old.adilet.zan.kz/rus/docs/K1500000414") == "ok" and lim.paused == 3


def test_a_429_holds_the_other_workers_threads():
    lim = corpus.RateLimiter(3.0)
    lim.pause(0.5)  # one worker got a 429 with Retry-After: 0.5
    t0 = time.monotonic()
    done: list[float] = []
    threads = [threading.Thread(target=lambda: (lim.acquire(), done.append(time.monotonic() - t0)))
               for _ in range(3)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(done) == 3 and min(done) >= 0.45


def test_errors_in_a_row_across_workers_stop_the_run(db, tmp_path, small_pages):
    site = SlowSite()
    collector(db, tmp_path, site).run(discover_only=True)
    site.broken = {k for k in site.docs if k.startswith("rus/docs/")} | {f"kaz/docs/{c}" for c, *_ in site.many}
    site.docs = {}
    stats = collector(db, tmp_path, site, concurrency=4).run()
    assert stats.stopped == "errors" and corpus.MAX_ERRORS_IN_A_ROW <= stats.errors <= corpus.MAX_ERRORS_IN_A_ROW + 4
    with db() as s:
        assert s.query(ZannAct).filter(ZannAct.state == "busy").count() == 0  # no claim is left behind


def test_metrics_show_the_pace(db, tmp_path, small_pages):
    site = Site()
    before = corpus.requests_last_hour()
    stats = collector(db, tmp_path, site).run()
    with db() as s:
        m = corpus_metrics(s)
    assert m["requests_last_hour"] - before == len(site.requests) == stats.requests
    assert m["acts_last_hour"] == 7 and m["files_last_hour"] == 7 and m["acts_busy"] == 0


def test_settings_give_the_workers_and_the_rate(tmp_path, db):
    from types import SimpleNamespace

    settings = SimpleNamespace(zann_corpus_langs="ru,kk", zann_corpus_statuses="in_force", zann_corpus_pause=1.0,
                               zann_corpus_refresh_days=30, zann_corpus_concurrency=4, zann_corpus_rate=9.0)
    made = corpus.build_collector(settings, db, CountingStorage(tmp_path / "f"))
    assert made.concurrency == 4 and made.fetch.delay == 2.0 and made.fetch.limiter.rate == 3.0
    made.fetch.client.close()


# ------------------------------------------------------------------ the nightly pass over recently changed acts
RECENT = "sort_field=dl&sort_desc=true"
NEW1 = ("P2600000848", "О внесении изменений в постановление", "new",
        "Постановление Правительства от 28 сентября 2026 года № 848")
NEW2 = ("P2600000900", "Об утверждении Правил", "new", "Постановление Правительства от 1 октября 2026 года № 900")
LOST = ("V1500011722", "Утративший силу приказ", "yts", "Приказ от 24 февраля 2015 года № 197")


def test_nightly_pass_reads_recently_changed_acts_first_and_stops_where_the_last_pass_ended(db, tmp_path, small_pages):
    site = Site()
    storage = CountingStorage(tmp_path / "files")
    t = [datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)]  # 17:00 in Almaty
    collector(db, tmp_path, site, storage=storage, now=lambda: t[0]).run()  # the initial collection, pass off
    site.broken.clear()

    def nightly(**kw):
        return collector(db, tmp_path, site, storage=storage, now=lambda: t[0], recent_hour=2, recent_pages=5,
                         tz=TZ, **kw)

    # the next night, 02:30: a new act, a lost-force one we never kept, the Labour Code changed (same listing line)
    t[0] = datetime(2026, 10, 1, 21, 30, tzinfo=timezone.utc)
    site.listings[RECENT] = [NEW1, LOST, CODES[0], LAWS[0], CODES[1], LAWS[1]]
    site.docs["rus/docs/P2600000848"] = page("О внесении изменений", BODY_RU)
    site.docs["rus/docs/K1500000414"] = page("Трудовой кодекс", BODY_RU + "<p>Статья 999. Новая статья</p>")
    c = nightly()
    assert c.recent_due()
    site.requests.clear()
    storage.puts.clear()
    stats = c.run()
    assert stats.recent_pages == 3 and stats.recent_queued == 5 and stats.discovered == 1  # LOST is not kept
    req = site.requests
    assert [r for r in req if r.startswith("/rus/index/")] == [
        f"/rus/index/docs/{RECENT}&pagesize=2&page={n}" for n in (1, 2, 3)]  # no other listing (30 days not up)
    assert req.index("/rus/docs/P2600000848") < req.index("/rus/docs/V2400035238")  # recent acts before the rest
    assert "zann/corpus/K1500000414.ru.txt.gz" in storage.puts and "zann/corpus/P2600000848.ru.txt.gz" in storage.puts
    assert "/rus/docs/V1500011722" not in req
    with db() as s:
        new = s.get(ZannAct, "P2600000848")
        assert new.state == "done" and new.priority == corpus.REST_TIER  # back to its tier once read
        assert s.get(ZannAct, "K1500000414").priority == 0
        assert s.query(ZannAct).filter(ZannAct.priority == corpus.RECENT_PRIORITY).count() == 0
        m = corpus_metrics(s)
    assert m["recent_pass_at"] == "2026-10-01T21:30:00+00:00" and m["recent_pending"] == 0
    assert m["listings"]["done"] == len(listing_plan(["in_force"]))  # the progress row is not a listing

    # later the same night: no second pass
    t[0] += timedelta(hours=1)
    assert not nightly().recent_due()
    site.requests.clear()
    nightly().run()
    assert not [r for r in site.requests if RECENT in r]

    # the night after: one more new act on top; the page after it holds only acts read since the last pass
    t[0] = datetime(2026, 10, 2, 21, 15, tzinfo=timezone.utc)
    site.listings[RECENT] = [NEW2, CODES[0], NEW1, LAWS[0], CODES[1], LAWS[1], CONST[0], OTHER[0]]
    site.docs["rus/docs/P2600000900"] = page("Об утверждении Правил", BODY_RU)
    site.requests.clear()
    stats = nightly().run()
    assert [r for r in site.requests if RECENT in r] == [
        f"/rus/index/docs/{RECENT}&pagesize=2&page={n}" for n in (1, 2)]
    assert stats.recent_queued == 1 and "/rus/docs/P2600000900" in site.requests
    assert "/rus/docs/K1500000414" not in site.requests  # read last night, after the pass started


def test_nightly_pass_resumes_after_the_time_box_and_is_off_with_minus_one(db, tmp_path, small_pages):
    site = Site()
    site.listings[RECENT] = [NEW1, NEW2, LOST, OTHER[0]]
    site.docs["rus/docs/P2600000848"] = page("О внесении изменений", BODY_RU)
    t = [datetime(2026, 10, 1, 21, 5, tzinfo=timezone.utc)]  # 02:05 in Almaty
    ticks = iter(range(10_000))
    c = collector(db, tmp_path, site, now=lambda: t[0], recent_hour=2, tz=TZ, clock=lambda: float(next(ticks)))
    first = c.run(budget_seconds=2)  # one page of the pass, then the box is over
    assert first.stopped == "budget" and first.recent_pages == 1 and first.acts == 0
    with db() as s:
        row = s.get(ZannListing, corpus.RECENT_KEY)
        assert row.next_page == 2 and row.done_at is None
    second = collector(db, tmp_path, site, now=lambda: t[0], recent_hour=2, tz=TZ).run(limit=1)
    assert second.recent_pages == 1 and second.acts == 1  # page 2 (then the pass is over), then the queue
    with db() as s:
        assert s.get(ZannListing, corpus.RECENT_KEY).done_at is not None
    # before 02:00 the first pass of the day is not due; -1 turns it off
    t[0] = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)  # 01:00 in Almaty
    assert collector(db, tmp_path, Site(), now=lambda: t[0], recent_hour=-1, tz=TZ).recent_due() is False


def test_jobs_say_when_they_run_next():
    job = ZannCorpusJob(lambda: FakeCollector(), TZ, hour=2, minutes=50, start=lambda fn: None)
    assert job.next_run(datetime(2026, 10, 1, 15, 0, tzinfo=TZ)) == datetime(2026, 10, 2, 2, 0, tzinfo=TZ)
    assert job.next_run(datetime(2026, 10, 1, 1, 0, tzinfo=TZ)) == datetime(2026, 10, 1, 2, 0, tzinfo=TZ)
    heard: list = []
    job = ZannCorpusJob(lambda: FakeCollector("idle"), TZ, hour=-1, minutes=50, start=lambda fn: fn(),
                        on_status=lambda *a: heard.append(a))
    now = datetime(2026, 10, 1, 15, 0, tzinfo=TZ)
    job(None, now)
    assert [h[0] for h in heard] == ["running", "idle"]
    assert timedelta(minutes=59) < heard[-1][3] - now <= timedelta(minutes=61)  # idle: rests for an hour


def test_settings_turn_the_nightly_pass_on_at_two():
    from konsilier.config import Settings

    s = Settings()
    assert s.zann_corpus_recent_hour == 2 and s.zann_corpus_recent_pages == 20
