"""Library of official pages: extraction, polite crawling (robots.txt, allow-list, pace, conditional GET, hashes),
search ranking, and the chat grounded in it."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from konsilier.chat import ChatAgent
from konsilier.core.db import make_engine, make_session_factory
from konsilier.core.models import Base, OfficialChunk, OfficialPage
from konsilier.lawagent.sources import Adilet
from konsilier.official import load_all
from konsilier.official.config import OfficialSources, load_sources
from konsilier.official.crawler import USER_AGENT, Crawler, Robots, detect_lang, extract
from konsilier.official.job import NightlyCrawl
from konsilier.official.search import OfficialLibrary, search, terms

from .test_chat import StreamingClient, _sse
from .test_lawagent import fake_fetch, tool_use

FIX = Path(__file__).parent / "fixtures" / "official"
REPO = Path(__file__).resolve().parents[3]
SITUATION = "https://www.portal.example/situations/148/intro?lang=ru"
PAYMENT = "https://fund.example/ru/socpayments/по-уходу/"

SOURCES = {
    "country": "XX", "max_depth": 2,
    "domains": [
        {"domain": "www.portal.example", "keep_query": ["lang"], "default_query": {"lang": "ru"},
         "include": [r"^/situations/\d+/intro", r"^/services/\d+"],
         "link_patterns": [{"match": r'"source_id"\s*:\s*"?(\d+)',
                            "url": "https://www.portal.example/services/{1}?lang=ru"}]},
        {"domain": "fund.example", "include": ["^/ru/socpayments/"]},
    ],
    "seeds": {"family": [SITUATION], "benefits": [PAYMENT]},
}


def fixture(name: str) -> str:
    return (FIX / name).read_text("utf-8")


@pytest.fixture
def db(tmp_path):
    # TEST_DATABASE_URL=postgresql+psycopg://… runs the search through the full-text index instead
    engine = make_engine(os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/official.db")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


# ------------------------------------------------------------------ extraction
def test_extracts_main_text_headings_and_links_without_chrome():
    ext = extract(fixture("situation.html"), SITUATION)
    assert ext.title == "Как получить алименты на ребенка" and ext.lang == "ru"
    headings = [s.heading for s in ext.sections]
    assert "Введение" in headings and "Как подать на алименты через суд" in headings
    court = next(s for s in ext.sections if s.heading == "Как подать на алименты через суд")
    assert "течение 3 рабочих дней" in court.text and "удостоверение личности" in court.text
    # the service card written as data becomes its title; scripts, menus, cookie banner and footer are dropped
    assert "«Выдача судебного приказа о взыскании алиментов»" in ext.text and "source_id" not in ext.text
    for chrome in ("window.__STATE__", "Поиск", "cookie", "© 2006", "Контакты", "display:flex"):
        assert chrome not in ext.text
    assert "/services/3187?lang=ru" in ext.links and "https://office.sud.kz/" in ext.links


def test_keeps_only_the_marked_main_content():
    ext = extract(fixture("payment.html"), "https://fund.example/ru/socpayments/по-уходу/")
    assert ext.title == "ПО УХОДУ ЗА РЕБЕНКОМ ДО ПОЛУТОРА ЛЕТ"  # the site name after " | " is cut
    assert "Право на СВур возникает" in [s.heading for s in ext.sections]
    assert "с даты рождения ребенка" in ext.text and "Государственную корпорацию" in ext.text
    for chrome in ("О фонде", "Найти", "Главная", "Новости", "Все права защищены"):
        assert chrome not in ext.text


def test_language_from_address_or_letters():
    assert extract(fixture("kk_page.html"), "https://fund.example/page").lang == "kk"
    assert detect_lang("https://x.example/a?lang=kk", "текст") == "kk"
    assert detect_lang("https://x.example/rus/docs/1", "") == "ru"
    assert detect_lang("https://x.example/cms/page", "Обычный русский текст о пособиях") == "ru"


# ------------------------------------------------------------------ robots.txt and the allow-list
def test_robots_rules():
    rules = Robots.parse("User-agent: *\nDisallow: /\n\nUser-agent: KonsilierBot\nDisallow: /private/\n"
                         "Disallow: /*?print=1$\nAllow: /private/open\n\nUser-agent: GPTBot\nDisallow: /\n")
    assert rules.allowed("https://x.example/situations/1")
    assert not rules.allowed("https://x.example/private/a")
    assert rules.allowed("https://x.example/private/open/a")  # the longer rule wins
    assert not rules.allowed("https://x.example/page?print=1") and rules.allowed("https://x.example/page?print=12")
    star = Robots.parse("User-agent: *\nCrawl-delay: 5\nDisallow: /search\nDisallow:\n")
    assert star.crawl_delay == 5 and not star.allowed("https://x.example/search?q=1")
    assert star.allowed("https://x.example/ru/")
    assert Robots.parse("").allowed("https://x.example/anything")


def test_allow_list_and_normalization():
    src = OfficialSources.model_validate(SOURCES)
    assert src.normalize("/situations/1/intro?utm_source=x", base=SITUATION) == \
        "https://www.portal.example/situations/1/intro?lang=ru"
    assert src.normalize("https://evil.example/situations/1/intro") is None
    assert src.normalize("https://sub.fund.example/ru/socpayments/") is None  # exact host only
    assert src.normalize("https://fund.example/ru/socpayments/%D0%BF%D0%BE/") == "https://fund.example/ru/socpayments/по/"
    assert src.follow("https://www.portal.example/services/12?lang=ru")
    assert not src.follow("https://www.portal.example/news/1?lang=ru")
    bad = dict(SOURCES, seeds={"x": ["https://not-allowed.example/page"]})
    with pytest.raises(ValueError, match="not on an allowed domain"):
        OfficialSources.model_validate(bad)


def test_pack_sources_file_is_valid():
    src = load_sources(REPO / "packs" / "kz")
    assert src is not None and src.country == "KZ"
    hosts = {d.domain for d in src.domains}
    assert "www.gov.kz" in hosts and "egov.kz" not in hosts  # a script-only site gives no text to keep
    assert {"social_benefits", "business_support", "education", "procurement", "consumer_protection", "labour",
            "housing", "fines", "family", "egov_howto"} <= set(src.seeds)
    assert all(src.domain_of(u) for _, u in src.seed_list())
    assert src.normalize("/services/3042", base="https://www.gov.kz/situations/1/intro?lang=ru") == \
        "https://www.gov.kz/services/3042?lang=ru"


# ------------------------------------------------------------------ the crawler, offline
class Site:
    """Two fake sites behind httpx.MockTransport; records every request with the (fake) time it was made."""

    def __init__(self, clock):
        self.clock, self.requests = clock, []
        self.payment = fixture("payment.html")

    def __call__(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        self.requests.append((url, self.clock(), dict(req.headers)))
        assert req.headers["user-agent"] == USER_AGENT
        html = {"content-type": "text/html; charset=utf-8"}
        if url == "https://www.portal.example/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n\nUser-agent: KonsilierBot\n"
                                            "Disallow: /services/3187\n")
        if url == "https://fund.example/robots.txt":
            return httpx.Response(404, text="not found")
        if req.url.path == "/situations/148/intro":
            if req.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, text=fixture("situation.html"), headers={**html, "etag": '"v1"'})
        if req.url.path == "/ru/socpayments/по-уходу/":
            return httpx.Response(200, text=self.payment, headers=html)  # no validators: the hash decides
        if req.url.path == "/ru/socpayments/по-беременности-и-родам-усыновлениюудочерению-ребенка/":
            return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})
        return httpx.Response(404, text="not found")


def make_crawler(db, fresh_hours=20.0):
    now = [1000.0]

    def sleep(s):
        now[0] += s

    site = Site(lambda: now[0])
    http = httpx.Client(transport=httpx.MockTransport(site), follow_redirects=True,
                        headers={"User-Agent": USER_AGENT})
    crawler = Crawler(db, OfficialSources.model_validate(SOURCES), http=http, fresh_hours=fresh_hours,
                      sleep=sleep, clock=lambda: now[0])
    return crawler, site


def test_crawl_respects_robots_allow_list_and_pace(db):
    crawler, site = make_crawler(db)
    stats = crawler.run()
    urls = [u for u, _, _ in site.requests]
    assert not any("3187" in u for u in urls)  # disallowed for our bot by robots.txt
    assert not any("office.sud.kz" in u or "example.org" in u or ".pdf" in u for u in urls)  # off the allow-list
    for domain in ("www.portal.example", "fund.example"):  # one request per second per domain
        times = [t for u, t, _ in site.requests if f"//{domain}/" in u]
        assert len(times) >= 2 and all(b - a >= 1.0 for a, b in zip(times, times[1:]))
    with db() as s:
        pages = {p.url: p for p in s.scalars(select(OfficialPage))}
        assert pages[SITUATION].status == "ok" and pages[SITUATION].etag == '"v1"'
        assert pages[PAYMENT].status == "ok" and pages[PAYMENT].title.startswith("ПО УХОДУ")
        lost = "https://fund.example/ru/socpayments/по-потере-работы/"  # linked percent-encoded, stored once
        assert pages[lost].status == "gone" and pages[lost].depth == 1
        pdf = next(p for u, p in pages.items() if "беременности" in u)
        assert pdf.status == "skipped" and "not HTML" in pdf.error
        assert not any("3187" in u for u in pages)
        chunks = s.scalars(select(OfficialChunk).where(OfficialChunk.page_id == pages[SITUATION].id)).all()
        assert len(chunks) >= 2 and all(c.country == "XX" and c.lang == "ru" for c in chunks)
    assert stats["www.portal.example"].changed == 1 and stats["fund.example"].changed == 1


def test_unchanged_pages_cost_nothing_and_changes_are_stored(db):
    crawler, site = make_crawler(db, fresh_hours=0)
    crawler.run()
    with db() as s:
        before = {c.id for c in s.scalars(select(OfficialChunk))}
        changed_at = s.scalar(select(OfficialPage.changed_at).where(OfficialPage.url == SITUATION))
    site.requests.clear()
    stats = crawler.run()
    sent = {u: h for u, _, h in site.requests}
    assert sent[SITUATION].get("if-none-match") == '"v1"'  # conditional GET → 304
    assert stats["www.portal.example"].unchanged == 1 and stats["fund.example"].unchanged == 1  # hash unchanged
    assert stats["www.portal.example"].changed == stats["fund.example"].changed == 0
    with db() as s:
        assert {c.id for c in s.scalars(select(OfficialChunk))} == before  # nothing rewritten
        assert s.scalar(select(OfficialPage.changed_at).where(OfficialPage.url == SITUATION)) == changed_at
    site.payment = site.payment.replace("Государственную корпорацию", "центр обслуживания населения")
    stats = crawler.run()
    assert stats["fund.example"].changed == 1
    with db() as s:
        page = s.scalar(select(OfficialPage).where(OfficialPage.url == PAYMENT))
        assert "центр обслуживания населения" in page.text


def test_a_fresh_run_resumes_where_the_last_one_stopped(db):
    crawler, site = make_crawler(db)
    crawler.run(limit=1)
    first = [u for u, _, _ in site.requests if not u.endswith("robots.txt")]
    site.requests.clear()
    crawler.run()
    second = [u for u, _, _ in site.requests if not u.endswith("robots.txt")]
    assert len(first) == 1 and first[0] not in second  # fetched within fresh_hours: not fetched again
    with db() as s:
        assert s.scalar(select(OfficialPage).where(OfficialPage.status == "pending")) is None


# ------------------------------------------------------------------ search
def add_page(s, url, title, sections, country="XX", lang="ru", status="ok"):
    page = OfficialPage(country=country, url=url, domain=url.split("/")[2], title=title, lang=lang, status=status,
                        text="\n".join(t for _, t in sections))
    s.add(page)
    s.flush()
    for i, (heading, body) in enumerate(sections):
        s.add(OfficialChunk(page_id=page.id, country=country, lang=lang, ord=i, heading=heading, text=body))
    return page


def seed_library(s):
    add_page(s, "https://fund.example/birth", "Пособие при рождении ребенка", [
        ("Кому назначается", "Единовременное государственное пособие в связи с рождением ребенка назначается "
                             "одному из родителей независимо от дохода семьи."),
        ("Куда обращаться", "Заявление подаётся через портал электронного правительства или в Государственную "
                            "корпорацию в течение двенадцати месяцев со дня рождения ребёнка.")])
    add_page(s, "https://fund.example/care", "Выплата по уходу за ребенком", [
        ("", "Социальная выплата по уходу за ребенком до полутора лет назначается участникам системы страхования.")])
    add_page(s, "https://business.example/damu", "Программы фонда «Даму»", [
        ("Субсидирование", "Фонд Даму субсидирует часть ставки вознаграждения по кредитам предпринимателей. "
                           "Грант на реализацию новых бизнес-идей выдаётся на конкурсной основе.")])
    add_page(s, "https://tenders.example/complaint", "Обжалование в государственных закупках", [
        ("Жалоба на итоги", "Жалоба на итоги госзакупок подаётся потенциальным поставщиком в уполномоченный орган "
                            "через веб-портал в течение пяти рабочих дней.")])
    add_page(s, "https://portal.example/passport", "Как получить паспорт", [
        ("", "Паспорт гражданина выдаётся через Государственную корпорацию по заявлению.")])
    add_page(s, "https://fund.example/old", "Пособие при рождении ребенка (архив)", [
        ("", "Пособие при рождении ребенка")], status="gone")
    add_page(s, "https://other.example/birth", "Пособие при рождении ребенка", [
        ("", "Пособие при рождении ребенка в другой стране.")], country="YY")


def test_search_ranks_the_answering_page_first(db):
    with db() as s:
        seed_library(s)
        s.commit()
        top = {q: search(s, q, "XX", "ru", 5) for q in
               ("пособие при рождении ребёнка", "грант Даму", "жалоба на итоги госзакупок")}
    assert top["пособие при рождении ребёнка"][0].url == "https://fund.example/birth"
    assert top["грант Даму"][0].url == "https://business.example/damu"
    assert top["жалоба на итоги госзакупок"][0].url == "https://tenders.example/complaint"
    birth = top["пособие при рождении ребёнка"]
    assert len({h.url for h in birth}) == len(birth)  # one hit per page
    assert all(h.url not in ("https://fund.example/old", "https://other.example/birth") for h in birth)
    assert "рождением ребенка" in birth[0].snippet and birth[0].domain == "fund.example"
    assert birth[0].score > birth[-1].score


def test_search_terms_and_empty_queries(db):
    assert terms("Как получить пособие при рождении ребёнка?") == ["пособи", "рождени", "ребенк"]
    with db() as s:
        seed_library(s)
        s.commit()
        assert search(s, "как и где", "XX") == [] and search(s, "", "XX") == []
        assert search(s, "пособие", "ZZ") == []


def test_search_is_fast_enough_for_the_chat(db):
    with db() as s:
        seed_library(s)
        for i in range(300):
            add_page(s, f"https://portal.example/p{i}", f"Услуга номер {i}", [
                (f"Раздел {j}", "Государственная услуга оказывается через портал и Государственную корпорацию. " * 8)
                for j in range(3)])
        s.commit()
    lib = OfficialLibrary(db, {"XX": OfficialSources.model_validate(SOURCES)})
    lib.search("пособие при рождении ребёнка", "XX", "ru")  # warm up
    t0 = time.perf_counter()
    hits = lib.search("пособие при рождении ребёнка", "XX", "ru", 3)
    assert (time.perf_counter() - t0) < 0.25  # the PostgreSQL index is faster still
    assert hits[0].url == "https://fund.example/birth"


# ------------------------------------------------------------------ the chat
def chat_with_library(db, turns):
    with db() as s:
        seed_library(s)
        add_page(s, SITUATION, "Как получить алименты на ребенка", [
            ("Как подать на алименты через суд", "Приказ об алиментах выносится судом в течение 3 рабочих дней. "
                                                 "Иск подаётся по месту жительства истца.")])
        s.commit()
    client = StreamingClient(turns)
    lib = OfficialLibrary(db, {"XX": OfficialSources.model_validate(SOURCES)})
    agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch), library=lib)
    events = list(agent.stream([{"role": "user", "text": "Как подать на алименты через суд?"}],
                               context={"pack": NS(country="XX", add_days=lambda *a: None), "forums": [],
                                        "case": {}, "lang": "ru"},
                               language="ru", country="X", use_portal=True))
    return events, client


def test_chat_gets_excerpts_before_the_model_and_cites_the_page(db):
    answer = f"По данным www.portal.example: приказ выносится в течение 3 рабочих дней. Подробнее: {SITUATION}"
    events, client = chat_with_library(db, [
        (["Проверю на официальном портале."], "tool_use",
         [tool_use("t1", "official_sources", {"query": "алименты суд приказ"})]),
        ([answer], "end_turn", []),
    ])
    system = client.calls[0]["system"]
    assert SITUATION in system and "течение 3 рабочих дней" in system  # pre-retrieved for every provider
    assert "«По данным <domain>: …»" in system and "www.portal.example — " in system  # rule and portal list
    assert "official_sources" in {t.get("name") for t in client.calls[0]["tools"]}
    tool_result = client.calls[1]["messages"][2]["content"][0]
    hits = json.loads(tool_result["content"])
    assert hits[0]["url"] == SITUATION and hits[0]["domain"] == "www.portal.example"
    res = events[-1]["result"]
    assert res.sources == [{"url": SITUATION, "title": "Как получить алименты на ребенка",
                            "domain": "www.portal.example"}]
    assert {"type": "tool", "name": "official_sources"} in events


def test_chat_says_so_when_the_library_has_nothing(db):
    events, client = chat_with_library(db, [
        ([], "tool_use", [tool_use("t1", "official_sources", {"query": "квоты на вылов рыбы"})]),
        (["В библиотеке этого нет, проверьте на портале."], "end_turn", []),
    ])
    assert "nothing found" in client.calls[1]["messages"][2]["content"][0]["content"]
    assert events[-1]["result"].sources == []


def test_chat_without_pages_offers_no_library_tool(db):
    client = StreamingClient([(["Уточните, пожалуйста, детали."], "end_turn", [])])
    lib = OfficialLibrary(db, {"XX": OfficialSources.model_validate(SOURCES)})
    agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch), library=lib)
    list(agent.stream([{"role": "user", "text": "Пособие?"}], context={"pack": NS(country="XX"), "forums": [],
                                                                       "case": {}, "lang": "ru"},
                      language="ru", country="X", use_portal=False))
    assert "official_sources" not in {t.get("name") for t in client.calls[0]["tools"]}
    assert "must be checked in the official service standard" in client.calls[0]["system"]


def test_chat_endpoint_saves_cited_sources(ctx):
    from .test_e2e import web_user

    url = "https://www.gov.kz/situations/1/intro?lang=ru"
    with ctx.container.session_factory() as s:
        add_page(s, url, "Рождение ребенка", [("Как оформить выплаты и пособия",
                                               "Единовременное пособие на рождение ребенка назначается по заявлению "
                                               "через портал электронного правительства.")], country="KZ")
        s.commit()
    assert ctx.container.official_library.available("KZ")
    client = StreamingClient([([f"По данным www.gov.kz: пособие назначается по заявлению. {url}"], "end_turn", [])])
    ctx.container.chat_agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch),
                                         library=ctx.container.official_library)
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Хочу получить пособие на рождение ребенка",
                                                   "country": "KZ"})["case"]["id"]
    done = _sse(ctx.client.post(f"/v1/cases/{cid}/chat", headers=api.h,
                                json={"text": "Как получить пособие при рождении ребёнка?"}))[-1]
    assert done["type"] == "done" and done["message"]["sources"][0]["url"] == url
    assert url in client.calls[0]["system"]


# ------------------------------------------------------------------ the nightly job
def test_nightly_job_starts_once_in_the_local_night(db):
    started = []
    packs = NS(pack=lambda cc: NS(tz=ZoneInfo("Asia/Almaty")))
    job = NightlyCrawl(db, packs, {"XX": OfficialSources.model_validate(SOURCES)}, start=started.append)
    tz = ZoneInfo("Asia/Almaty")
    with db() as s:
        assert job(s, datetime(2026, 9, 30, 2, 59, tzinfo=tz)) == 0 and started == []
        job(s, datetime(2026, 9, 30, 3, 0, tzinfo=tz))
        job(s, datetime(2026, 9, 30, 3, 1, tzinfo=tz))
        assert len(started) == 1  # once a night
        job._running.clear()
        s.add(OfficialPage(country="XX", url="https://fund.example/x", domain="fund.example",
                           fetched_at=datetime(2026, 10, 1, 3, 0, tzinfo=tz).astimezone(timezone.utc)
                           - timedelta(minutes=5)))
        s.commit()
        job(s, datetime(2026, 10, 1, 3, 0, tzinfo=tz))
        assert len(started) == 1  # another worker is crawling right now
        job(s, datetime(2026, 10, 2, 3, 30, tzinfo=tz))
        assert len(started) == 2


def test_container_wires_library_and_job(ctx, packs_dir):
    from konsilier.config import Settings
    from konsilier.container import build_container
    from konsilier.core.documents import NullPdfConverter
    from konsilier.core.llm.mock import HeuristicMockProvider

    assert "KZ" in ctx.container.official_sources and ctx.container.official_library is not None
    assert not any(isinstance(j, NightlyCrawl) for j in ctx.container.scheduler.extra_jobs)  # off in tests
    s = ctx.settings.model_copy(update={"official_crawl_enabled": True})
    c = build_container(Settings(**s.model_dump()), llm=HeuristicMockProvider(), pdf=NullPdfConverter())
    assert any(isinstance(j, NightlyCrawl) for j in c.scheduler.extra_jobs)
    assert set(load_all(c.packs)) == {"KZ"}
    c.engine_db.dispose()


def test_extraction_handles_text_before_headings():
    html = "<html><body><p>" + "Вступление о госуслуге. " * 12 + "</p><h2>Шаги</h2><p>" + "Подайте заявление. " * 5 + \
        "</p></body></html>"
    ext = extract(html, "https://x.example/p")
    assert ext.sections[0].heading == "" and ext.sections[1].heading == "Шаги"
