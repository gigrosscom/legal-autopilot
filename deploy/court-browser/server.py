"""court-browser: one real Chromium (Playwright) that opens public pages of court websites for konsilier/zann/court.py.

Owner 02–03.10.2026: court acts that the courts publish openly are read through a real browser, slowly (the collector
waits 5–10 s between requests and never less than the site's Crawl-delay), only from the allowed hosts. The browser is
not disguised (no stealth patches; its User-Agent is Chromium's own with our name and contact added) and never solves
or bypasses a captcha or a JS challenge: such a page is answered as {"blocked": ...} and the collector stops.

POST /fetch {"url": "https://…"} →
  {"status": 200, "url": final URL, "content_type": "…", "disposition": "…", "body_b64": "…"}
  {"blocked": "captcha" | "challenge", "status": …}     — a captcha or challenge instead of the page
  {"error": "…"} with HTTP 502                           — the site could not be reached (reset, timeout)
GET /health → {"ok": true, "user_agent": "…"}

Pages (HTML, robots.txt) are opened by navigation; files (PDF, DOC, DOCX, …) are fetched from inside a page of the
same site, so they go through the same browser with its cookies. One request at a time: a single-threaded server.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlsplit

log = logging.getLogger("court-browser")

HOSTS = {h.strip().lower() for h in os.environ.get("COURT_BROWSER_HOSTS", "sud.kz,www.sud.kz,sud.gov.kz").split(",")
         if h.strip()}
# Our name and contact, added to Chromium's own User-Agent (an honest browser, not a disguise)
UA_SUFFIX = os.environ.get("COURT_BROWSER_UA_SUFFIX", "Konsilier.AI/1.0 (+https://konsilier.com; info@konsilier.com)")
MAX_BYTES = int(os.environ.get("COURT_BROWSER_MAX_BYTES", "60000000"))
TIMEOUT_MS = int(float(os.environ.get("COURT_BROWSER_TIMEOUT_S", "90")) * 1000)
PORT = int(os.environ.get("COURT_BROWSER_PORT", "8090"))

# Files: fetched from inside a page of the same site (Chromium shows a PDF in its viewer and starts a download for
# a DOCX, neither gives the bytes back to a navigation)
FILE_RE = re.compile(r"\.(pdf|docx?|rtf|odt|zip)(?:$|[?#])|/download/", re.I)
# A captcha or challenge served instead of the page. Matched only together with a missing page body or an error
# status, so a page that merely mentions a captcha (a feedback form) is not mistaken for one.
CHALLENGE_RE = re.compile(r"g-recaptcha|www\.google\.com/recaptcha|hcaptcha\.com|challenges\.cloudflare\.com|"
                          r"cf-challenge|cf-turnstile|__cf_chl_|/cdn-cgi/challenge-platform", re.I)
CAPTCHA_RE = re.compile(r"g-recaptcha|recaptcha|hcaptcha|turnstile", re.I)
BODY_MARK = os.environ.get("COURT_BROWSER_BODY_MARK", 'id="page-title"')  # the page's own content is there

FETCH_JS = """async (u) => {
  const r = await fetch(u, {credentials: 'include', redirect: 'follow'});
  const len = Number(r.headers.get('content-length') || 0);
  if (len > %d) return {status: r.status, url: r.url, too_big: len};
  const b = new Uint8Array(await r.arrayBuffer());
  let s = '';
  for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode.apply(null, b.subarray(i, i + 32768));
  return {status: r.status, url: r.url, ct: r.headers.get('content-type') || '',
          cd: r.headers.get('content-disposition') || '', b64: btoa(s), size: b.length};
}""" % MAX_BYTES


def blocked_kind(status: int, body: bytes, content_type: str) -> str:
    """'captcha' / 'challenge' when the answer is a captcha or challenge page instead of the content, else ''."""
    if "html" not in content_type.lower():
        return ""
    text = body[:400_000].decode("utf-8", errors="replace")
    if not CHALLENGE_RE.search(text):
        return ""
    if status >= 400 or BODY_MARK not in text:
        return "captcha" if CAPTCHA_RE.search(text) else "challenge"
    return ""


class Browser:
    """Chromium started once; one page per site origin, reused (its cookies are the browser's own)."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        probe = self.browser.new_page()
        base_ua = probe.evaluate("navigator.userAgent")
        probe.close()
        self.user_agent = f"{base_ua} {UA_SUFFIX}".strip()
        self.context = self.browser.new_context(user_agent=self.user_agent, locale="ru-RU",
                                                accept_downloads=False, java_script_enabled=True)
        self.context.set_default_timeout(TIMEOUT_MS)
        self.pages: dict[str, Any] = {}

    def _page_on(self, origin: str):
        page = self.pages.get(origin)
        if page is None or page.is_closed():
            page = self.context.new_page()
            self.pages[origin] = page
        return page

    def fetch(self, url: str) -> dict[str, Any]:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or host not in HOSTS:
            return {"error": f"host not allowed: {host}", "status": 0}
        origin = f"{parts.scheme}://{parts.netloc}"
        page = self._page_on(origin)
        if FILE_RE.search(url):
            if not page.url.startswith(origin):  # a page of the site first: the file is fetched from its origin
                first = page.goto(origin + "/", wait_until="domcontentloaded")
                body = first.body() if first else b""
                kind = blocked_kind(first.status if first else 0, body,
                                    (first.headers.get("content-type", "") if first else ""))
                if kind:
                    return {"blocked": kind, "status": first.status if first else 0, "url": page.url}
            got = page.evaluate(FETCH_JS, url)
            if got.get("too_big"):
                return {"status": 413, "url": got.get("url", url), "content_type": "", "disposition": "",
                        "body_b64": ""}
            data = base64.b64decode(got.get("b64") or "")
            kind = blocked_kind(got["status"], data, got.get("ct", ""))
            if kind:
                return {"blocked": kind, "status": got["status"], "url": got.get("url", url)}
            return {"status": got["status"], "url": got.get("url", url), "content_type": got.get("ct", ""),
                    "disposition": got.get("cd", ""), "body_b64": got.get("b64") or ""}
        resp = page.goto(url, wait_until="domcontentloaded")
        if resp is None:
            return {"error": "no response", "status": 0}
        body = resp.body()  # the page as the server sent it (not the DOM after scripts)
        ctype = resp.headers.get("content-type", "")
        kind = blocked_kind(resp.status, body, ctype)
        if kind:
            return {"blocked": kind, "status": resp.status, "url": page.url}
        if len(body) > MAX_BYTES:
            return {"status": 413, "url": page.url, "content_type": ctype, "disposition": "", "body_b64": ""}
        return {"status": resp.status, "url": page.url, "content_type": ctype,
                "disposition": resp.headers.get("content-disposition", ""),
                "retry_after": resp.headers.get("retry-after", ""),
                "body_b64": base64.b64encode(body).decode()}


class Handler(BaseHTTPRequestHandler):
    browser: Browser | None = None

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ok": True, "user_agent": self.browser.user_agent if self.browser else None})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/fetch":
            self._send(404, {"error": "not found"})
            return
        try:
            url = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}").get("url", "")
        except ValueError:
            self._send(400, {"error": "bad json"})
            return
        try:
            out = self.browser.fetch(url)  # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001 — the site is unreachable: reset, timeout, DNS
            log.warning("fetch %s failed: %s", url, e)
            self._send(502, {"error": f"{e.__class__.__name__}: {str(e)[:300]}"})
            return
        log.info("fetch %s → %s%s", url, out.get("status"), f" blocked={out['blocked']}" if out.get("blocked") else "")
        self._send(502 if out.get("error") else 200, out)

    def log_message(self, fmt: str, *args: Any) -> None:  # requests are logged by do_POST
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Handler.browser = Browser()
    log.info("court-browser on :%d, hosts %s, user agent %s", PORT, sorted(HOSTS), Handler.browser.user_agent)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
