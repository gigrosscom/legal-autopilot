"""Zann article index: the collected adilet acts (konsilier/zann/corpus.py) split into articles for the search.

Splitting reuses the legal agent's parser (konsilier/lawagent/sources.split_articles: «Статья N.» / «N-бап.»
headings, a body runs to the next article or chapter). An act without such headings (resolutions, orders) is cut
into pieces of about PIECE_CHARS at paragraph breaks, with an empty article number. A very long article is cut into
parts that keep its number. Each row carries the act code, title, type and status, the language and the adilet URL
with a text fragment (``#:~:text=Статья%20113.``) that makes the browser scroll to the article — the mirror has no
per-article anchors we could derive from the text.

Incremental: zann_indexed keeps the sha256 (and the act status) of every indexed file; a run re-splits only files
that are new or whose sha256 / status changed, oldest change first, within a time budget. The job runs every
ZANN_INDEX_EVERY_MINUTES and right after each corpus run. With ZANN_EMBEDDINGS on, the same run then fills the
vectors of rows that have none (or of another model), in batches, within the same budget.
"""

from __future__ import annotations

import gzip
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import ZannAct, ZannArticle, ZannFile, ZannIndexed
from ..lawagent.sources import split_articles
from .corpus import doc_url
from .embed import Embedder, pack

log = logging.getLogger(__name__)

PIECE_CHARS = 4000     # a piece of an act without articles
MAX_ARTICLE = 30000    # a longer article is stored in parts (PostgreSQL tsvector and the chat's context stay small)
BATCH_FILES = 50
EMBED_BATCH = 32


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Chunk:
    ord: int
    number: str   # "113", "113-1"; "" for a piece of an act without articles
    heading: str  # the article's title («Порядок …»), or the first line of a piece
    text: str


def article_url(code: str, lang: str, number: str) -> str:
    """The act on the mirror, scrolled to the article by a text fragment (Chrome, Edge, Safari, Firefox 131+)."""
    url = doc_url(code, lang)
    if not number:
        return url
    head = f"{number}-бап." if lang == "kk" else f"Статья {number}."
    return f"{url}#:~:text={quote(head)}"


def _parts(text: str, size: int) -> list[str]:
    """Cut at paragraph breaks into parts of at most ``size`` characters (a longer paragraph is cut at a space)."""
    out, cur = [], ""
    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > size:
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            if cur:
                out.append(cur)
                cur = ""
            out.append(para[:cut].strip())
            para = para[cut:].strip()
        if cur and len(cur) + len(para) + 1 > size:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def split_act(text: str) -> list[Chunk]:
    articles = split_articles(text)
    out: list[Chunk] = []
    if articles:
        for number, (title, body) in articles.items():
            body = body.strip()
            if not body and not title:
                continue
            parts = _parts(body, MAX_ARTICLE) if len(body) > MAX_ARTICLE else [body]
            for i, part in enumerate(parts):
                head = title if i == 0 else f"{title} (ч. {i + 1})"
                out.append(Chunk(len(out), number, head[:500], part))
        return out
    for part in _parts(text, PIECE_CHARS):
        first = part.split("\n", 1)[0]
        out.append(Chunk(len(out), "", first[:200], part))
    return out


@dataclass
class IndexStats:
    files: int = 0       # files (re-)split
    articles: int = 0    # rows written
    removed: int = 0     # rows of files that are gone
    embedded: int = 0    # vectors computed
    errors: int = 0
    stopped: str = ""    # idle | budget | limit


class Indexer:
    def __init__(self, session_factory: sessionmaker[Session], storage: Any, *, embedder: Embedder | None = None,
                 clock: Callable[[], float] = time.monotonic, now: Callable[[], datetime] = utcnow):
        self.sf, self.storage, self.embedder, self.clock, self.now = session_factory, storage, embedder, clock, now

    def run(self, budget_seconds: float | None = None, limit: int | None = None,
            embed_only: bool = False) -> IndexStats:
        stats = IndexStats()
        deadline = self.clock() + budget_seconds if budget_seconds else None

        def over() -> bool:
            if deadline is not None and self.clock() >= deadline:
                stats.stopped = "budget"
                return True
            if limit is not None and stats.files >= limit:
                stats.stopped = "limit"
                return True
            return False

        if not embed_only:
            stats.removed = self._remove_gone()
            failed: set[tuple[str, str]] = set()
            while not over():
                todo = [t for t in self._todo() if (t[0], t[1]) not in failed]
                if not todo:
                    break
                for code, lang in todo:
                    if over():
                        break
                    try:
                        stats.articles += self._index_file(code, lang)
                        stats.files += 1
                    except Exception:  # one unreadable file must not stop the run
                        log.exception("zann index: %s %s failed", code, lang)
                        stats.errors += 1
                        failed.add((code, lang))
        if self.embedder is not None and not stats.stopped:
            while not over():
                n = self._embed_batch()
                stats.embedded += n
                if not n:
                    break
        stats.stopped = stats.stopped or "idle"
        return stats

    # ---- what changed: files never indexed, or with another sha256 / act status, oldest change first
    def _todo(self) -> list[tuple[str, str]]:
        with self.sf() as s:
            q = (select(ZannFile.code, ZannFile.lang)
                 .join(ZannAct, ZannAct.code == ZannFile.code, isouter=True)
                 .join(ZannIndexed, (ZannIndexed.code == ZannFile.code) & (ZannIndexed.lang == ZannFile.lang),
                       isouter=True)
                 .where(or_(ZannIndexed.code.is_(None), ZannIndexed.sha256 != ZannFile.sha256,
                            ZannIndexed.status != ZannAct.status))
                 .order_by(ZannFile.changed_at, ZannFile.code, ZannFile.lang).limit(BATCH_FILES))
            return [(c, lang) for c, lang in s.execute(q).all()]

    def _remove_gone(self) -> int:
        with self.sf() as s:
            gone = s.execute(select(ZannIndexed.code, ZannIndexed.lang)
                             .join(ZannFile, (ZannFile.code == ZannIndexed.code) & (ZannFile.lang == ZannIndexed.lang),
                                   isouter=True).where(ZannFile.code.is_(None))).all()
            n = 0
            for code, lang in gone:
                n += s.execute(delete(ZannArticle).where(ZannArticle.code == code, ZannArticle.lang == lang)).rowcount
                s.execute(delete(ZannIndexed).where(ZannIndexed.code == code, ZannIndexed.lang == lang))
            s.commit()
            return n

    def _index_file(self, code: str, lang: str) -> int:
        with self.sf() as s:
            f = s.get(ZannFile, (code, lang))
            act = s.get(ZannAct, code)
            if f is None:
                return 0
            key, sha, title = f.key, f.sha256, (f.title or (act.title if act else "") or "")
            act_type, status = (act.act_type or "", act.status or "") if act else ("", "")
        text = gzip.decompress(self.storage.get(key)).decode("utf-8")
        chunks = split_act(text)
        with self.sf() as s:
            s.execute(delete(ZannArticle).where(ZannArticle.code == code, ZannArticle.lang == lang))
            s.add_all([ZannArticle(code=code, lang=lang, ord=c.ord, number=c.number, heading=c.heading or None,
                                   act_title=title[:1000], act_type=act_type, status=status,
                                   url=article_url(code, lang, c.number)[:512], text=c.text) for c in chunks])
            row = s.get(ZannIndexed, (code, lang)) or ZannIndexed(code=code, lang=lang)
            row.sha256, row.status, row.articles, row.indexed_at = sha, status, len(chunks), self.now()
            s.merge(row)
            s.commit()
        return len(chunks)

    def _embed_batch(self) -> int:
        assert self.embedder is not None
        name = self.embedder.name
        with self.sf() as s:
            rows = s.execute(select(ZannArticle.id, ZannArticle.heading, ZannArticle.text, ZannArticle.act_title)
                             .where(or_(ZannArticle.emb_model.is_(None), ZannArticle.emb_model != name))
                             .order_by(ZannArticle.id).limit(EMBED_BATCH)).all()
        if not rows:
            return 0
        vecs = self.embedder.passages([f"{t or ''}. {h or ''}\n{x}" for _, h, x, t in rows])
        with self.sf() as s:
            for (rid, *_), v in zip(rows, vecs):
                a = s.get(ZannArticle, rid)
                if a is not None:
                    a.embedding, a.emb_model = pack(v), name
            s.commit()
        return len(rows)


def index_metrics(session: Session) -> dict[str, Any]:
    from sqlalchemy import func

    files, articles = session.execute(select(func.count(), func.coalesce(func.sum(ZannIndexed.articles), 0))).one()
    embedded = session.scalar(select(func.count()).select_from(ZannArticle).where(ZannArticle.emb_model.is_not(None)))
    last = session.scalar(select(func.max(ZannIndexed.indexed_at)))
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return {"files": files, "articles": int(articles), "embedded": embedded or 0,
            "last_indexed_at": last.isoformat(timespec="seconds") if last else None}


class ZannIndexJob:
    """A job of the scheduler tick: an incremental run every ``every_minutes`` (and at once after a corpus run, via
    ``kick``), in a background thread, time-boxed to ``minutes``. A run that finds nothing new costs one query."""

    def __init__(self, make_indexer: Callable[[], Indexer], *, every_minutes: int = 30, minutes: int = 10,
                 start: Callable[[Callable[[], None]], None] | None = None):
        self.make_indexer, self.every, self.minutes = make_indexer, timedelta(minutes=max(1, every_minutes)), minutes
        self.start = start or (lambda fn: threading.Thread(target=fn, name="zann-index", daemon=True).start())
        self._next: datetime | None = None
        self._running = False
        self._lock = threading.Lock()
        self.last: IndexStats | None = None

    def kick(self) -> None:
        """Run on the next tick (a corpus run just ended)."""
        self._next = None

    def __call__(self, session: Session, now: datetime | None) -> int:
        now = now or utcnow()
        with self._lock:
            if self._running or (self._next is not None and now < self._next):
                return 0
            self._running = True
            self._next = now + self.every
        self.start(self._run)
        return 0

    def _run(self) -> None:
        try:
            stats = self.make_indexer().run(budget_seconds=self.minutes * 60)
            self.last = stats
            if stats.files or stats.removed or stats.embedded or stats.errors:
                log.info("zann index: run done %s", asdict(stats))
        except Exception:
            log.exception("zann index: run failed")
        finally:
            self._running = False
