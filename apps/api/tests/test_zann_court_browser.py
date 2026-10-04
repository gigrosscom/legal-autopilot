"""Court practice through a real browser (konsilier/zann/court.py BrowserFetcher + deploy/court-browser/server.py,
owner 02–03.10.2026): the collector talks to the court-browser service, which is faked here over httpx.MockTransport
around the same sud.kz fake as test_zann_court.py. A saved real sud.kz page (01.10.2026) is the HTML fixture for the
parser and for the captcha detector. No network, no Chromium."""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from konsilier.core.adapters.storage import LocalStorage
from konsilier.zann import court
from konsilier.zann.court import Blocked, BrowserFetcher, Collector, run_state

from .test_zann_court import RULES, SITE, Site, db  # noqa: F401 — the sud.kz fake and the db fixture

FIXTURE = Path(__file__).parent / "fixtures" / "court" / "sud_kz_obzory_2026-10-01.html"
SERVER = Path(__file__).resolve().parents[3] / "deploy" / "court-browser" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("court_browser_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # playwright is imported only when the browser starts
    return mod


class FakeService:
    """The court-browser service: POST /fetch {url} → the site's answer as JSON, like server.py."""

    def __init__(self, site: Site, blocked: dict[str, str] | None = None, down: int = 0):
        self.client = httpx.Client(transport=httpx.MockTransport(site), follow_redirects=True)
        self.blocked = blocked or {}  # path → "captcha" | "challenge"
        self.down = down  # requests answered with a connection error first (the service restarting)
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down > 0:
            self.down -= 1
            raise httpx.ConnectError("court-browser restarting", request=request)
        url = json.loads(request.content)["url"]
        self.urls.append(url)
        path = urlsplit(url).path
        if path in self.blocked:
            return httpx.Response(200, json={"blocked": self.blocked[path], "status": 403, "url": url})
        try:
            r = self.client.get(url)
        except httpx.TransportError as e:
            return httpx.Response(502, json={"error": f"{e.__class__.__name__}: {e}"})
        return httpx.Response(200, json={
            "status": r.status_code, "url": str(r.url), "content_type": r.headers.get("Content-Type", ""),
            "disposition": r.headers.get("Content-Disposition", ""), "retry_after": r.headers.get("Retry-After", ""),
            "body_b64": base64.b64encode(r.content).decode()})


def browser_collector(db, tmp_path, service: FakeService, sleeps: list[float] | None = None, **kw) -> Collector:  # noqa: F811
    client = httpx.Client(transport=httpx.MockTransport(service))
    fetch = BrowserFetcher("http://court-browser:8090", delay=kw.pop("delay", 5.0), jitter=kw.pop("jitter", 5.0),
                           retries=kw.pop("retries", 2), sleep=(sleeps if sleeps is not None else []).append,
                           client=client, rand=lambda: 0.5)
    return Collector(db, LocalStorage(tmp_path / "files"), fetch, SITE, RULES, **kw)


# ------------------------------------------------------------------ the collector through the browser
def test_collects_the_open_sources_through_the_browser(db, tmp_path):  # noqa: F811
    site = Site()
    service = FakeService(site)
    stats = browser_collector(db, tmp_path, service).run()
    assert stats.stopped == "idle" and stats.docs == 6 and stats.saved >= 4 and stats.errors == 0
    assert service.urls[0] == "https://sud.kz/robots.txt"
    assert not [u for u in service.urls if "office.sud.kz" in u]  # the bank of acts (captcha) is never asked for


def test_pause_is_5_to_10_seconds_and_never_below_crawl_delay(db, tmp_path):  # noqa: F811
    site = Site()
    sleeps: list[float] = []
    c = browser_collector(db, tmp_path, FakeService(site), sleeps=sleeps, sources=("review",))
    c.run(limit=1)
    assert c.fetch.delay == 10  # robots.txt Crawl-delay: 10 raised the 5 s pause
    assert sleeps and all(s >= 10 for s in sleeps[1:])
    fetch = BrowserFetcher("http://x", sleep=[].append)
    assert (fetch.delay, fetch.jitter) == (5.0, 5.0)


def test_captcha_stops_the_run_and_is_never_bypassed(db, tmp_path):  # noqa: F811
    site = Site()
    service = FakeService(site, blocked={"/rus/content/obzory-sudebnoy-praktiki": "captcha"})
    stats = browser_collector(db, tmp_path, service, sources=("review",)).run()
    assert stats.stopped == "captcha" and "captcha at https://sud.kz/rus/content/obzory" in stats.error
    assert run_state(stats.stopped, stats.error) == "blocked(captcha)"
    assert service.urls.count("https://sud.kz/rus/content/obzory-sudebnoy-praktiki") == 1  # not retried


def test_captcha_on_robots_txt_is_blocked_not_unreachable(db, tmp_path):  # noqa: F811
    site = Site()
    service = FakeService(site, blocked={"/robots.txt": "challenge"})
    stats = browser_collector(db, tmp_path, service).run()
    assert stats.stopped == "captcha" and stats.pages == 0


def test_site_dropping_the_browser_too_stops_as_unreachable(db, tmp_path):  # noqa: F811
    site = Site()
    site.busy["/robots.txt"] = 99  # 503 every time
    stats = browser_collector(db, tmp_path, FakeService(site), retries=1).run()
    assert stats.stopped == "unreachable" and stats.pages == 0


def test_service_restart_is_retried(db, tmp_path):  # noqa: F811
    site = Site()
    stats = browser_collector(db, tmp_path, FakeService(site, down=2), retries=3, sources=("review",)).run()
    assert stats.stopped == "idle" and stats.docs >= 1


def test_404_is_missing_and_429_backs_off():
    answers = iter([httpx.Response(200, json={"status": 429, "retry_after": "30"}),
                    httpx.Response(200, json={"status": 200, "content_type": "text/plain",
                                              "body_b64": base64.b64encode(b"ok").decode()}),
                    httpx.Response(200, json={"status": 404})])
    sleeps: list[float] = []
    fetch = BrowserFetcher("http://b", delay=0, jitter=0, sleep=sleeps.append,
                           client=httpx.Client(transport=httpx.MockTransport(lambda r: next(answers))))
    assert fetch("https://sud.kz/a").text == "ok" and 30 in sleeps
    with pytest.raises(court.ActNotFound):
        fetch("https://sud.kz/b")
    with pytest.raises(Blocked):
        BrowserFetcher("http://b", delay=0, jitter=0, sleep=sleeps.append, client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"blocked": "captcha"}))))("https://x")


def test_build_uses_the_browser_when_its_url_is_set(db, tmp_path):  # noqa: F811
    from konsilier.config import Settings

    s = Settings()
    assert s.zann_court_browser_url == "" and isinstance(court.build_collector(s, db, None).fetch, court.CourtFetcher)
    s = Settings(zann_court_browser_url="http://court-browser:8090/")
    fetch = court.build_collector(s, db, LocalStorage(tmp_path / "f")).fetch
    assert isinstance(fetch, BrowserFetcher) and fetch.base_url == "http://court-browser:8090"
    assert (fetch.delay, fetch.jitter) == (5.0, 5.0)


# ------------------------------------------------------------------ the saved real page and the captcha detector
def test_real_sud_kz_page_parses_through_the_browser_path():
    raw = FIXTURE.read_bytes()
    got = court.Got(raw, "text/html; charset=utf-8")
    found = SITE.parse_leaf("review", got.text, "https://sud.kz/rus/content/obzory-sudebnoy-praktiki")
    assert len(found) == 80
    assert all(f.url.startswith("https://sud.kz/sites/default/files/pagefiles/") for f in found)
    assert all(court.DOC_EXT_RE.search(f.url) for f in found)


def test_captcha_detector_passes_a_page_that_only_embeds_a_feedback_captcha():
    srv = load_server()
    raw = FIXTURE.read_bytes()
    assert b"recaptcha/api.js" in raw  # sud.kz loads reCAPTCHA for its feedback form on every page
    assert srv.blocked_kind(200, raw, "text/html; charset=utf-8") == ""


def test_captcha_detector_reports_captcha_and_challenge_pages():
    srv = load_server()
    captcha = b'<html><body><form><div class="g-recaptcha" data-sitekey="x"></div></form></body></html>'
    assert srv.blocked_kind(200, captcha, "text/html") == "captcha"
    challenge = (b'<html><head><title>Just a moment...</title></head><body>'
                 b'<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1"></script></body></html>')
    assert srv.blocked_kind(403, challenge, "text/html") == "challenge"
    assert srv.blocked_kind(200, b"%PDF-1.7 g-recaptcha", "application/pdf") == ""


def test_server_is_honest_and_only_opens_allowed_hosts():
    srv = load_server()
    assert "Konsilier.AI" in srv.UA_SUFFIX and "konsilier.com" in srv.UA_SUFFIX
    assert srv.HOSTS == {"sud.kz", "www.sud.kz", "sud.gov.kz"} and "office.sud.kz" not in srv.HOSTS
    assert "stealth" not in SERVER.read_text().lower().replace("no stealth", "")
    assert srv.FILE_RE.search("https://sud.gov.kz/library/download/188419")
    assert srv.FILE_RE.search("https://sud.kz/sites/default/files/pagefiles/a.PDF")
    assert not srv.FILE_RE.search("https://sud.kz/rus/content/obzory-sudebnoy-praktiki")
