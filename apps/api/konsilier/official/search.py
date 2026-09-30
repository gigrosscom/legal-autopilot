"""Search of the official library: ``search(session, query, country, lang, limit) -> list[Hit]``.

PostgreSQL: the generated ``tsv`` column of official_chunks (the 'russian' configuration for Russian text, 'simple'
for other languages) with its GIN index picks up to 60 candidates; they are then ranked in Python by how many of
the question's words they contain, the same way SQLite (tests, local runs) ranks every chunk of the country. At
most one hit per page, so the chat sees several sources rather than one page repeated.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import OfficialChunk, OfficialPage
from .config import OfficialSources

log = logging.getLogger(__name__)

CANDIDATES = 60
SNIPPET = 360  # characters

# Words that carry no meaning for the search (function words and question words of the pack languages, Russian and the local one).
STOP = set("""
и в во на по с со к ко о об от до за из у же ли бы не ни но а или что чтобы как какой какая какие каких где когда куда
кто чем это этот эта эти тот та те то там тут мне меня мой моя мои нам нас наш вам вас ваш вы я он она они его ее их
для при без над под про через после если есть был была были будет можно нужно надо ли уже еще также только все всех
весь вся свой своя свои себя очень тоже так такой да нет ну вот ещё сколько почему зачем чего кому получить хочу
және мен бен пен да де та те ма ме ба бе па пе ғой қой ол бұл сол мына осы мен сен сіз біз олар оның менің сенің
сіздің қалай қандай қайда қашан кім не неге үшін туралы бойынша арқылы деген болады бар жоқ керек
""".split())


@dataclass(frozen=True)
class Hit:
    url: str
    title: str
    heading: str
    snippet: str
    score: float
    domain: str


def terms(query: str) -> list[str]:
    """Stems of the meaningful words: lower case, ё→е, a crude cut of the ending (enough to match
    «пособие / пособия / пособий» or «жалоба / жалобы»)."""
    out: list[str] = []
    for w in re.findall(r"[^\W_]{2,}", query.lower().replace("ё", "е")):
        if w in STOP or (len(w) < 3 and not w.isdigit()):
            continue
        stem = w if len(w) <= 4 else w[:max(4, min(len(w) - 1, 7))]
        if stem not in out:
            out.append(stem)
    return out[:12]


def _score(stems: list[str], title: str, heading: str, body: str) -> float:
    """Share of the question's words found, weighted by word length (longer words are rarer), squared, times 100.
    A word in the page title or the section heading, or repeated in the text, counts more, so a close match scores
    above 100; about 20 means roughly half of the question's words are there (OfficialLibrary's threshold)."""
    if not stems:
        return 0.0
    head = f"{title} {heading}".lower().replace("ё", "е")
    low = body.lower().replace("ё", "е")
    total = got = 0.0
    for st in stems:
        w = 1 + len(st) / 6
        total += w
        rx = r"(?<!\w)" + re.escape(st)
        in_head = st in head and re.search(rx, head) is not None
        n = len(re.findall(rx, low)) if st in low else 0
        if in_head or n:
            got += w * (1.6 if in_head else 1.0) * (1 + min(math.log1p(n), 2) / 4)
    coverage = got / total
    return round(coverage * coverage * 100, 2)


def snippet(body: str, stems: list[str], size: int = SNIPPET) -> str:
    """The window of ``size`` characters holding the most of the question's words, cut at word boundaries."""
    low = body.lower().replace("ё", "е")
    pos = sorted(m.start() for st in stems for m in re.finditer(r"(?<!\w)" + re.escape(st), low))
    if len(body) <= size or not pos:
        start = 0
    else:
        best, start = -1, 0
        for p in pos:
            n = sum(1 for q in pos if p <= q < p + size - 40)
            if n > best:
                best, start = n, max(0, p - 60)
    end = min(len(body), start + size)
    if start > 0:
        sp = body.find(" ", start)
        start = sp + 1 if 0 <= sp < start + 30 else start
    if end < len(body):
        sp = body.rfind(" ", start, end)
        end = sp if sp > start + size // 2 else end
    out = re.sub(r"\s+", " ", body[start:end]).strip()
    return ("…" if start > 0 else "") + out + ("…" if end < len(body) else "")


def _tsquery(stems: list[str]) -> str:
    return " | ".join(re.sub(r"[^\w]", "", s) + ":*" for s in stems if re.sub(r"[^\w]", "", s))


def _candidates(session: Session, stems: list[str], country: str) -> list[tuple[Any, ...]]:
    """(heading, text, lang, url, title, domain) of chunks that may answer."""
    base = (select(OfficialChunk.heading, OfficialChunk.text, OfficialChunk.lang, OfficialPage.url,
                   OfficialPage.title, OfficialPage.domain)
            .join(OfficialPage, OfficialPage.id == OfficialChunk.page_id)
            .where(OfficialChunk.country == country, OfficialPage.status == "ok"))
    if session.get_bind().dialect.name == "postgresql":
        q = _tsquery(stems)
        rows = session.execute(text(
            "SELECT c.heading, c.text, c.lang, p.url, p.title, p.domain FROM official_chunks c "
            "JOIN official_pages p ON p.id = c.page_id, "
            "(SELECT to_tsquery('russian', :q) || to_tsquery('simple', :q) AS q) AS t "
            "WHERE c.country = :country AND p.status = 'ok' AND c.tsv @@ t.q "
            "ORDER BY ts_rank_cd(c.tsv, t.q) DESC LIMIT :n"), {"q": q, "country": country, "n": CANDIDATES}).all()
        return [tuple(r) for r in rows]
    return [tuple(r) for r in session.execute(base).all()]  # SQLite: every chunk of the country, ranked below


def search(session: Session, query: str, country: str, lang: str | None = None, limit: int = 5) -> list[Hit]:
    stems = terms(query)
    if not stems:
        return []
    scored: list[tuple[float, Any]] = []
    for row in _candidates(session, stems, country):
        heading, body, chunk_lang, _, title, _ = row
        score = _score(stems, title or "", heading or "", body)
        if score <= 0:
            continue
        if lang and chunk_lang and chunk_lang != lang:
            score *= 0.8  # the person's language first, others still count
        scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    out: list[Hit] = []
    for score, (heading, body, _, url, title, domain) in scored:
        if any(h.url == url for h in out):  # one hit per page
            continue
        out.append(Hit(url, title or "", heading or "", snippet(body, stems), round(score, 2), domain))
        if len(out) >= limit:
            break
    return out


class OfficialLibrary:
    """What the chat holds: search of the stored pages and the portals of each country (from the pack's sources).
    Knows, cheaply, whether a country has any pages at all (checked at most every few minutes)."""

    def __init__(self, session_factory: sessionmaker[Session], sources: dict[str, OfficialSources],
                 min_score: float = 20.0):
        self.session_factory, self.sources, self.min_score = session_factory, sources, min_score
        self._pages: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def available(self, country: str | None) -> bool:
        if not country or country not in self.sources:
            return False
        with self._lock:
            hit = self._pages.get(country)
        if hit and time.monotonic() - hit[0] < 300:
            return hit[1] > 0
        try:
            with self.session_factory() as s:
                n = s.scalar(select(func.count()).select_from(OfficialPage).where(
                    OfficialPage.country == country, OfficialPage.status == "ok")) or 0
        except Exception:  # table missing on an old database: no library, the chat carries on
            log.exception("official library unavailable")
            n = 0
        with self._lock:
            self._pages[country] = (time.monotonic(), n)
        return n > 0

    def search(self, query: str, country: str, lang: str | None = None, limit: int = 5) -> list[Hit]:
        t0 = time.perf_counter()
        with self.session_factory() as s:
            hits = [h for h in search(s, query, country, lang, limit) if h.score >= self.min_score]
        ms = (time.perf_counter() - t0) * 1000
        if ms > 100:
            log.warning("official search took %.0f ms", ms)
        return hits

    def portals(self, country: str | None, lang: str) -> list[dict[str, str]]:
        src = self.sources.get(country or "")
        if not src:
            return []
        return [{"domain": d.domain, "name": d.name.get(lang) or d.name.get("ru") or d.domain,
                 "about": d.about.get(lang) or d.about.get("ru") or ""} for d in src.domains]
