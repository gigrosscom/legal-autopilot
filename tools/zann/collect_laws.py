"""Zann corpus collector: official texts of the Kazakhstan acts our KZ scenarios cite.

Scope is deliberately narrow. It takes only the act codes that packs/kz already links to (a few dozen, not the
Әділет database), opens each act's official page on old.adilet.zan.kz — the same server-rendered mirror the legal
agent reads (konsilier.lawagent.sources) — and saves the act's text, Russian and Kazakh, to

    data/zann/corpus/<code>.<lang>.txt        lang: ru | kk
    data/zann/manifest.jsonl                  one line per saved file

data/zann/ is git-ignored: the corpus is never committed. It is for internal RAG indexing and evaluation.
Using it to train a commercial model needs the lawyer's opinion on the Әділет terms first
(docs/legal-sources.md, «Не копируем базы»; docs/zann-llm-plan.md).

Polite by design: one request at a time, a pause between requests (default 3 s), a clear User-Agent, retries with
back-off on 429/5xx/network errors, a hard cap on codes per run, and files already on disk are skipped.

    python tools/zann/collect_laws.py --from-packs --limit 3
    python tools/zann/collect_laws.py --codes K1500000414 Z100000274_ --langs ru
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "api"))

from konsilier.lawagent.sources import CODE_RE, ActNotFound, page_text  # noqa: E402

BASE = "https://old.adilet.zan.kz"
USER_AGENT = "Konsilier.AI Zann corpus collector (+https://konsilier.com; research; 1 request / 3 s)"
LANGS = {"ru": "rus", "kk": "kaz"}  # our code → the portal's path segment
MAX_CODES = 5000  # a sanity limit per run (owner 30.09: laws from adilet are collected for Zann)
ADILET_LINK_RE = re.compile(r"adilet\.zan\.kz/(?:rus|kaz|eng)/docs/([A-Z]\d{9,10}_?)")
ARTICLE_TAG_RE = re.compile(r"(?is)<article\b[^>]*>(.*?)</article>")
TITLE_RE = re.compile(r"(?is)<title>(.*?)</title>")
KK_TITLE_SUFFIX_RE = re.compile(r"\s*-\s*\"?Әділет\"?\s*АҚЖ.*$")
KK_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
MIN_CHARS = 300  # a shorter body means the portal has no text in this language (or a stub page)

Fetch = Callable[[str], str]


@dataclass
class Record:
    code: str
    title: str
    lang: str
    url: str
    fetched_at: str
    sha256: str
    chars: int


# ---------- pure logic (tested without network) ----------

def codes_from_packs(packs_dir: Path) -> list[str]:
    """Every act code linked from the pack (yaml/md/json/txt), most-cited first, then by code."""
    counts: dict[str, int] = {}
    for p in sorted(packs_dir.rglob("*")):
        if p.is_file() and p.suffix in {".yaml", ".yml", ".md", ".json", ".txt"}:
            for code in ADILET_LINK_RE.findall(p.read_text("utf-8", errors="ignore")):
                counts[code] = counts.get(code, 0) + 1
    return sorted(counts, key=lambda c: (-counts[c], c))


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
    """True when Kazakh-specific letters are frequent enough (a Russian page mentions a few Kazakh names)."""
    letters = sum(ch.isalpha() for ch in text)
    return letters > 0 and sum(ch in KK_LETTERS for ch in text) / letters > 0.01


def make_record(code: str, title: str, lang: str, url: str, text: str, now: datetime | None = None) -> Record:
    return Record(
        code=code, title=title, lang=lang, url=url,
        fetched_at=(now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), chars=len(text),
    )


def load_manifest(path: Path) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out[(row["code"], row["lang"])] = row
    return out


def write_manifest(path: Path, rows: dict[tuple[str, str], dict]) -> None:
    """Rewrite atomically, one row per (code, lang), sorted: re-runs update rows instead of duplicating them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for key in sorted(rows):
            f.write(json.dumps(rows[key], ensure_ascii=False) + "\n")
    tmp.replace(path)


def validate_codes(codes: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for c in codes:
        c = c.strip()
        if not CODE_RE.match(c):
            raise SystemExit(f"not an adilet document code: {c!r}")
        if c not in seen:
            seen.append(c)
    if len(seen) > MAX_CODES:
        raise SystemExit(f"{len(seen)} codes > {MAX_CODES}: split the list into several runs")
    return seen


# ---------- network ----------

class PoliteFetcher:
    """One request at a time, a pause between requests, retries with back-off on 429/5xx and network errors."""

    def __init__(self, delay: float = 3.0, retries: int = 3, timeout: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep, client: httpx.Client | None = None):
        self.delay, self.retries, self.sleep = delay, retries, sleep
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                             headers={"User-Agent": USER_AGENT})
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
            if r.status_code == 404:
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


def collect(codes: list[str], langs: list[str], out_dir: Path, manifest_path: Path, fetch: Fetch,
            force: bool = False, log: Callable[[str], None] = print) -> dict[str, int]:
    rows = load_manifest(manifest_path)
    stats = {"saved": 0, "skipped": 0, "missing": 0, "failed": 0}
    out_dir.mkdir(parents=True, exist_ok=True)
    for code in codes:
        for lang in langs:
            path = out_dir / f"{code}.{lang}.txt"
            if path.exists() and (code, lang) in rows and not force:
                stats["skipped"] += 1
                continue
            url = f"{BASE}/{LANGS[lang]}/docs/{code}"
            try:
                title, text = extract_act(fetch(url))
            except ActNotFound:
                log(f"{code} {lang}: not on the portal")
                stats["missing"] += 1
                continue
            except Exception as e:  # keep going: one bad act must not stop the run
                log(f"{code} {lang}: failed ({type(e).__name__}: {e})")
                stats["failed"] += 1
                continue
            if len(text) < MIN_CHARS or (lang == "kk" and not looks_kazakh(text)):
                log(f"{code} {lang}: no text in this language ({len(text)} chars)")
                stats["missing"] += 1
                continue
            path.write_text(text, encoding="utf-8")
            rows[(code, lang)] = asdict(make_record(code, title, lang, url, text))
            write_manifest(manifest_path, rows)  # after every file, so an interrupted run keeps its progress
            stats["saved"] += 1
            log(f"{code} {lang}: {len(text):,} chars — {title}")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--codes", nargs="*", default=[], help="adilet document codes, e.g. K1500000414")
    ap.add_argument("--from-packs", action="store_true", help="take the codes linked from packs/kz")
    ap.add_argument("--packs", type=Path, default=REPO / "packs" / "kz")
    ap.add_argument("--limit", type=int, default=0, help="only the first N codes")
    ap.add_argument("--langs", default="ru,kk", help="ru,kk (default) or one of them")
    ap.add_argument("--out", type=Path, default=REPO / "data" / "zann" / "corpus")
    ap.add_argument("--manifest", type=Path, default=REPO / "data" / "zann" / "manifest.jsonl")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between requests (min 1)")
    ap.add_argument("--force", action="store_true", help="re-download files already on disk")
    a = ap.parse_args(argv)

    codes = list(a.codes) + (codes_from_packs(a.packs) if a.from_packs else [])
    codes = validate_codes(codes)
    if a.limit:
        codes = codes[: a.limit]
    langs = [x.strip() for x in a.langs.split(",") if x.strip()]
    if not codes or any(x not in LANGS for x in langs):
        ap.error("give --codes and/or --from-packs; --langs from ru,kk")
    stats = collect(codes, langs, a.out, a.manifest, PoliteFetcher(delay=max(1.0, a.delay)), force=a.force)
    print(json.dumps(stats))
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
