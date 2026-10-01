"""Zann search («ищет и цитирует»): the articles of the collected acts that answer a question, with citations.

Hybrid, free, on our own server:
1. A direct reference in the question («ст. 113 ТК», «статья 9 Закона о защите прав потребителей», «113-бап»)
   is looked up by number and act first.
2. Full-text: PostgreSQL — the generated ``tsv`` column of zann_articles (the 'russian' configuration for ru,
   'simple' for kk) with its GIN index picks candidates: first articles holding every word of the question, then,
   if too few, any of them (bounded scan); they are ranked in Python by the official library's word-coverage score
   (konsilier/official/search.py), with codes and laws ahead of by-laws and acts in force ahead of lost ones.
   SQLite (tests, local runs) ranks every row the same way.
3. Semantic (only with ZANN_EMBEDDINGS on): cosine of the question's vector with the stored article vectors.
4. Reciprocal rank fusion of 2 and 3 (k = 60); direct references stay on top.

A hit is one article: act code and title, article number and heading, language, the adilet URL scrolled to the
article, a snippet, and the citation «ст. 113, Трудовой кодекс …» (kk: «113-бап, …»).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import ZannArticle, ZannFile
from ..official.search import STOP, snippet
from .embed import Embedder, VectorTable

log = logging.getLogger(__name__)

CANDIDATES = 60
OR_SCAN = 500       # a tier looks at no more than this many matching rows (keeps a common word fast)
RANK_CHARS = 8000   # of an article's text read for ranking
ENOUGH = 12         # a stricter tier that found this many is enough: the looser ones are not run
RRF_K = 60
SEM_TOP = 50
STATEMENT_MS = 400  # PostgreSQL gives up a search query after this (the chat never waits on the index)

# act type → weight: codes and the Constitution first, then laws, by-laws last
TYPE_WEIGHT = {"КОД": 1.3, "КОНС": 1.3, "КЗАК": 1.2, "УКОН": 1.2, "ЗАК": 1.15, "УЗАК": 1.1}
LOST = {"yts", "stp"}  # lost force

# Short names people use → a fragment of the act's official title (lower case). Several acts may match
# (the Civil Code has a general and a special part).
ACT_ALIASES: dict[str, tuple[str, ...]] = {
    "тк": ("трудовой кодекс",), "трудового кодекса": ("трудовой кодекс",), "трудовой кодекс": ("трудовой кодекс",),
    "еңбек кодекс": ("еңбек кодексі",), "азаматтық процестік кодекс": ("азаматтық процестік кодексі",),
    "салық кодекс": ("салық кодексі",), "әкімшілік құқық бұзушылық": ("әкімшілік құқық бұзушылық",),
    "қылмыстық кодекс": ("қылмыстық кодексі",), "жер кодекс": ("жер кодексі",),
    "кәсіпкерлік кодекс": ("кәсіпкерлік кодексі",), "тұтынушылардың құқықтарын қорғау": ("тұтынушылардың құқықтарын",),
    "гк": ("гражданский кодекс",), "гражданского кодекса": ("гражданский кодекс",),
    "гражданский кодекс": ("гражданский кодекс",), "азаматтық кодекс": ("азаматтық кодекс",),
    "гпк": ("гражданский процессуальный кодекс",),
    "гражданского процессуального кодекса": ("гражданский процессуальный кодекс",),
    "коап": ("об административных правонарушениях",), "кодекса об административных правонарушениях":
        ("об административных правонарушениях",),
    "нк": ("налоговый кодекс",), "налогового кодекса": ("налоговый кодекс",),
    "ук": ("уголовный кодекс",), "уголовного кодекса": ("уголовный кодекс",),
    "упк": ("уголовно-процессуальный кодекс",),
    "аппк": ("административный процедурно-процессуальный кодекс",),
    "зк": ("земельный кодекс",), "земельного кодекса": ("земельный кодекс",),
    "пк": ("предпринимательский кодекс",), "предпринимательского кодекса": ("предпринимательский кодекс",),
    "кобс": ("о браке (супружестве) и семье",), "кодекса о браке": ("о браке (супружестве) и семье",),
    "конституции": ("конституция",), "конституция": ("конституция",),
    "зозпп": ("о защите прав потребителей",), "закона о защите прав потребителей": ("о защите прав потребителей",),
}
REF_RE = re.compile(
    r"(?i)(?:\bст(?:атья|атьи|атье|атьей|атью)?\.?\s*(\d+(?:-\d+)?)|(\d+(?:-\d+)?)\s*-?\s*ба[пб]\w*)"
    r"(?P<rest>[^\n.;]{0,90})")
CODE_IN_TEXT = re.compile(r"\b([A-Z]\d{9,10}_?)\b")


@dataclass(frozen=True)
class Hit:
    code: str
    lang: str
    number: str
    heading: str
    act_title: str
    act_type: str
    status: str
    url: str
    snippet: str
    score: float
    citation: str
    text: str = field(default="", repr=False)  # the whole article: for the chat's check of cited norms
    match: str = "words"  # ref | words | semantic | hybrid

    def public(self, full: bool = False) -> dict[str, Any]:
        out = {"citation": self.citation, "act_code": self.code, "act_title": self.act_title,
               "act_type": self.act_type, "in_force": self.status not in LOST, "article": self.number,
               "heading": self.heading, "lang": self.lang, "url": self.url, "snippet": self.snippet,
               "score": self.score, "match": self.match}
        if full:
            out["text"] = self.text
        return out


def citation(number: str, act_title: str, lang: str) -> str:
    title = act_title or ""
    if not number:
        return title
    return f"{number}-бап, {title}" if lang == "kk" else f"ст. {number}, {title}"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def references(query: str) -> list[tuple[str, tuple[str, ...]]]:
    """(article number, title fragments or act codes) for each direct reference in the question."""
    out = []
    for m in REF_RE.finditer(query):
        num = m.group(1) or m.group(2)
        rest = _norm(m.group("rest"))
        if m.group(2):  # kk puts the act first: «Еңбек кодексінің 113-бабы»
            rest = _norm(query[max(0, m.start() - 80):m.start()]) + " " + rest
        codes = tuple(CODE_IN_TEXT.findall(m.group("rest")))
        frags: tuple[str, ...] = codes
        if not frags:
            for alias in sorted(ACT_ALIASES, key=len, reverse=True):
                # short names must stand alone (ТК, ГК); longer ones may take a case ending (кодекс-інің)
                end = r"(?!\w)" if len(alias) <= 5 else ""
                if re.search(r"(?<!\w)" + re.escape(alias) + end, rest):
                    frags = ACT_ALIASES[alias]
                    break
        if not frags:  # «статья 9 Закона «О …»» — the words after «закона о»
            m2 = re.search(r"закона\s+(?:рк\s+|республики казахстан\s+)?[«\"]?(о[б]?\s+[^«»\"]{4,60})", rest)
            if m2:
                frags = (m2.group(1).strip(" »\""),)
        if frags:
            out.append((num, frags))
    return out


class _Acts:
    """code → (title per language) of the indexed acts, for direct references; reloaded every few minutes."""

    def __init__(self) -> None:
        self.at = 0.0
        self.rows: list[tuple[str, str, str]] = []  # (code, lang, lower title)

    def get(self, session: Session) -> list[tuple[str, str, str]]:
        if time.monotonic() - self.at > 300 or not self.rows:
            self.rows = [(c, lg, _norm(t or "")) for c, lg, t in session.execute(
                select(ZannFile.code, ZannFile.lang, ZannFile.title)).all()]
            self.at = time.monotonic()
        return self.rows


def _row_hit(r: Any, stems: list[str], score: float, match: str) -> Hit:
    return Hit(r.code, r.lang, r.number or "", r.heading or "", r.act_title or "", r.act_type or "", r.status or "",
               r.url, snippet(r.text, stems) if stems else re.sub(r"\s+", " ", r.text[:360]).strip(),
               round(score, 2), citation(r.number or "", r.act_title or "", r.lang), r.text, match)


COLS = (ZannArticle.id, ZannArticle.code, ZannArticle.lang, ZannArticle.number, ZannArticle.heading,
        ZannArticle.act_title, ZannArticle.act_type, ZannArticle.status, ZannArticle.url, ZannArticle.text)
SQL_COLS = "a.id, a.code, a.lang, a.number, a.heading, a.act_title, a.act_type, a.status, a.url, a.text"


def _by_reference(session: Session, query: str, lang: str | None, acts: _Acts) -> list[Any]:
    refs = references(query)
    if not refs:
        return []
    rows: list[Any] = []
    known = acts.get(session)
    for num, frags in refs[:3]:
        codes = {c for c, lg, t in known if (not lang or lg == lang)
                 and any(f == c or f in t for f in frags)}
        if not codes:
            continue
        q = select(*COLS).where(ZannArticle.number == num, ZannArticle.code.in_(sorted(codes)[:20]))
        if lang:
            q = q.where(ZannArticle.lang == lang)
        rows += session.execute(q.order_by(ZannArticle.code, ZannArticle.ord)).all()
    return rows


KK_LETTERS = set("әғқңөұүһі")


def query_lang(query: str) -> str:
    """kk when kk-only letters (ә ғ қ ң ө ұ ү һ і) are there, else ru."""
    return "kk" if any(ch in KK_LETTERS for ch in query.lower()) else "ru"


def words(query: str) -> list[str]:
    """Meaningful words of the question (no function words, no bare numbers), at most 8."""
    out: list[str] = []
    for w in re.findall(r"[^\W\d_]{3,}", query.lower().replace("ё", "е")):
        if w not in STOP and w not in out:
            out.append(w)
    return out[:8]


def stem(w: str) -> str:
    """A crude prefix that matches the word's forms in ru and kk («увольнении» → «увольн»,
    «босатылған» → «босаты»): Python ranking and the 'simple' configuration (kk)."""
    return w if len(w) <= 4 else w[:max(4, min(len(w) - 2, 6))]


def _clean(w: str) -> str:
    return re.sub(r"[^\w]", "", w)


def _tiers(ws: list[str], qlang: str) -> list[str]:
    """tsquery strings from strict to loose: every word; all but one (3+ words); any word."""
    toks = [_clean(stem(w)) + ":*" for w in ws]
    toks = [t for t in toks if t.strip(":*")]
    if not toks:
        return []
    tiers = [" & ".join(toks)]
    if len(toks) >= 3:
        tiers.append(" | ".join("(" + " & ".join(t for j, t in enumerate(toks) if j != i) + ")"
                                for i in range(len(toks))))
    if len(toks) >= 2:
        tiers.append(" | ".join(toks))
    return tiers


def _fulltext(session: Session, ws: list[str], lang: str | None) -> list[Any]:
    if session.get_bind().dialect.name != "postgresql":
        q = select(*COLS)
        if lang:
            q = q.where(ZannArticle.lang == lang)
        return list(session.execute(q).all())  # SQLite: every row, ranked in Python
    qlang = lang or query_lang(" ".join(ws))
    cfg = "russian" if qlang == "ru" else "simple"
    lang_sql = " AND a.lang = :lang" if lang else ""
    # a bounded scan of the matches, ranked by cover density normalised by length (long articles do not win)
    sql = text(f"SELECT * FROM (SELECT {SQL_COLS}, ts_rank_cd(a.tsv, t.q, 1) AS rk FROM zann_articles a, "
               f"(SELECT to_tsquery('{cfg}', :q) AS q) t WHERE a.tsv @@ t.q{lang_sql} LIMIT :scan) s "
               f"ORDER BY rk DESC LIMIT :n")
    rows: list[Any] = []
    seen: set[int] = set()
    try:
        session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_MS}"))
        for q in _tiers(ws, qlang):
            for r in session.execute(sql, {"q": q, "lang": lang or "", "n": CANDIDATES, "scan": OR_SCAN}).all():
                if r.id not in seen:
                    seen.add(r.id)
                    rows.append(r)
            if len(rows) >= ENOUGH:
                break
    except Exception:  # statement timeout or a malformed query: what was found so far
        log.exception("zann full-text query failed")
        session.rollback()
    return rows


def _rank(stems: list[str], r: Any) -> float:
    """Words in the article's heading count most; words in its text count with saturation and length
    normalisation (BM25-like), so a long article mentioning everything once does not beat the right short one.
    Squared share of the question's words found, times 100: ≈100 when every word is in the heading and text."""
    if not stems:
        return 0.0
    head = (r.heading or "").lower().replace("ё", "е")
    title = (r.act_title or "").lower().replace("ё", "е")
    body = r.text[:RANK_CHARS].lower().replace("ё", "е")
    norm = 0.25 + 0.75 * len(r.text) / 1500
    total = got = found = 0.0
    for st in stems:
        w = 1 + len(st) / 6
        total += w
        h = 1.0 if st in head else 0.0
        t = 0.3 if st in title else 0.0
        tf = body.count(st)  # substring count: fast, and a stem is long enough to rarely hit inside other words
        b = tf / (tf + 1.2 * norm) if tf else 0.0
        if h or t or tf:
            found += w
        got += w * min(1.0, 0.6 * h + t + 0.7 * b)
    coverage = found / total
    return round(100 * coverage * coverage * (0.4 + 0.6 * got / total), 2)


def _weight(r: Any) -> float:
    w = TYPE_WEIGHT.get(r.act_type or "", 1.0)
    return w * (0.5 if (r.status or "") in LOST else 1.0)


def search(session: Session, query: str, *, lang: str | None = None, prefer_lang: str | None = None,
           limit: int = 5, embedder: Embedder | None = None, vectors: VectorTable | None = None,
           acts: _Acts | None = None, min_score: float = 0.0) -> list[Hit]:
    """Articles answering ``query``. ``lang`` filters (ru | kk); ``prefer_lang`` only ranks that language first."""
    query = (query or "")[:500]
    ws = words(query)
    stems = [stem(w) for w in ws]
    found: list[tuple[float, Any, str]] = []  # (score, row, match) best first
    seen: set[int] = set()
    qlang = lang or prefer_lang or query_lang(query)
    refs = sorted(_by_reference(session, query, lang, acts or _Acts()), key=lambda r: r.lang != qlang)
    for r in refs:
        if r.id not in seen:
            seen.add(r.id)
            found.append((1000.0, r, "ref"))
    # full-text ranking
    ft: list[tuple[float, Any]] = []
    if stems:
        for r in _fulltext(session, ws, lang):
            if r.id in seen:
                continue
            s = _rank(stems, r)
            if s <= 0:
                continue
            s *= _weight(r)
            if prefer_lang and r.lang != prefer_lang:
                s *= 0.8
            ft.append((s, r))
        ft.sort(key=lambda x: (-x[0], x[1].code, x[1].id))
        ft = [x for x in ft if x[0] >= min_score]
    # semantic ranking
    sem: list[tuple[float, Any]] = []
    if embedder is not None and vectors is not None and vectors.count > 0:
        try:
            top = vectors.top(embedder.query(query), SEM_TOP)
            ids = [i for i, _ in top if i not in seen]
            rows = {r.id: r for r in session.execute(select(*COLS).where(ZannArticle.id.in_(ids))).all()} if ids else {}
            sem = [(s, rows[i]) for i, s in top if i in rows and (not lang or rows[i].lang == lang)]
        except Exception:  # the model failed: words search still answers
            log.exception("zann semantic search failed")
    if sem:  # reciprocal rank fusion
        fused: dict[int, list[Any]] = {}
        for rank, (_, r) in enumerate(ft[:CANDIDATES]):
            fused.setdefault(r.id, [0.0, r, False, False])[0] += 1 / (RRF_K + rank + 1)
            fused[r.id][2] = True
        for rank, (_, r) in enumerate(sem):
            e = fused.setdefault(r.id, [0.0, r, False, False])
            e[0] += 1 / (RRF_K + rank + 1)
            e[3] = True
        for rrf, r, by_words, by_vec in sorted(fused.values(), key=lambda e: -e[0]):
            found.append((rrf * 1000, r, "hybrid" if by_words and by_vec else ("words" if by_words else "semantic")))
    else:
        found += [(s, r, "words") for s, r in ft]
    # one hit per article (a long article is stored in parts); snippets only for what is returned
    out: list[Hit] = []
    keys: set[tuple[str, str, str]] = set()
    for score, r, match in found:
        k = (r.code, r.lang, r.number or f"#{r.id}")
        if k in keys:
            continue
        keys.add(k)
        out.append(_row_hit(r, stems, score, match))
        if len(out) >= limit:
            break
    return out


class LawIndex:
    """What the API and the chat hold: search over zann_articles; knows cheaply whether the index has rows."""

    def __init__(self, session_factory: sessionmaker[Session], embedder: Embedder | None = None,
                 min_score: float = 20.0):
        self.sf, self.embedder, self.min_score = session_factory, embedder, min_score
        self.vectors = VectorTable() if embedder else None
        self._acts = _Acts()
        self._count: tuple[float, int] | None = None
        self._vec_checked = 0.0
        self._lock = threading.Lock()

    def available(self) -> bool:
        hit = self._count
        if hit and time.monotonic() - hit[0] < 300:
            return hit[1] > 0
        try:
            with self.sf() as s:
                n = 1 if s.scalar(select(ZannArticle.id).limit(1)) is not None else 0
        except Exception:  # table missing on an old database: no index, the chat carries on
            log.exception("zann index unavailable")
            n = 0
        self._count = (time.monotonic(), n)
        return n > 0

    def _refresh_vectors(self, session: Session) -> None:
        if self.vectors is None or self.embedder is None or time.monotonic() - self._vec_checked < 300:
            return
        with self._lock:
            self._vec_checked = time.monotonic()
            n = session.scalar(select(func.count()).select_from(ZannArticle)
                               .where(ZannArticle.emb_model == self.embedder.name)) or 0
            if n != self.vectors.count:
                items = session.execute(select(ZannArticle.id, ZannArticle.embedding)
                                        .where(ZannArticle.emb_model == self.embedder.name)
                                        .order_by(ZannArticle.id)).all()
                self.vectors.load([(i, b) for i, b in items if b])

    def search(self, query: str, *, lang: str | None = None, prefer_lang: str | None = None,
               limit: int = 5, min_score: float | None = None, semantic: bool = True) -> list[Hit]:
        t0 = time.perf_counter()
        with self.sf() as s:
            if semantic:
                self._refresh_vectors(s)
            hits = search(s, query, lang=lang, prefer_lang=prefer_lang, limit=limit,
                          embedder=self.embedder if semantic else None,
                          vectors=self.vectors, acts=self._acts,
                          min_score=self.min_score if min_score is None else min_score)
            s.rollback()  # ends the transaction of SET LOCAL
        ms = (time.perf_counter() - t0) * 1000
        if ms > 100:
            log.warning("zann search took %.0f ms", ms)
        return hits
