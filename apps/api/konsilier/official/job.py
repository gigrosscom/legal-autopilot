"""The nightly refresh of the official library, as a job of the scheduler tick (konsilier/core/deadlines.py).

The tick runs every minute; this job only looks at the clock. In the configured hour of each country's local
night (03:00 by default) it starts one crawl of that country in a background thread, time-boxed (20 minutes by
default), so deadline reminders are never held up. A crawl that another API worker started minutes ago (pages
fetched in the last half hour) is not started twice; a run cut by its time box is continued the next night.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..core.models import OfficialPage
from .config import OfficialSources
from .crawler import Crawler, _aware

log = logging.getLogger(__name__)


class NightlyCrawl:
    def __init__(self, session_factory: sessionmaker[Session], packs: Any, sources: dict[str, OfficialSources], *,
                 hour: int = 3, minutes: int = 20, max_pages: int | None = None,
                 start: Callable[[Callable[[], None]], None] | None = None):
        self.session_factory, self.packs, self.sources = session_factory, packs, sources
        self.hour, self.minutes, self.max_pages = hour, minutes, max_pages
        self.start = start or (lambda fn: threading.Thread(target=fn, name="official-crawl", daemon=True).start())
        self._done: dict[str, date] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def __call__(self, session: Session, now: datetime | None) -> int:
        now = now or datetime.now(timezone.utc)
        for cc, src in self.sources.items():
            local = now.astimezone(self.packs.pack(cc).tz)
            if local.hour != self.hour or self._done.get(cc) == local.date():
                continue
            with self._lock:
                if cc in self._running:
                    continue
                self._done[cc] = local.date()
            last = _aware(session.scalar(select(func.max(OfficialPage.fetched_at))
                                         .where(OfficialPage.country == cc)))
            if last and now - last < timedelta(minutes=30):
                log.info("official: %s crawl already running elsewhere", cc)
                continue
            self._running.add(cc)
            self.start(lambda cc=cc, src=src: self._run(cc, src))
        return 0  # no messages sent

    def _run(self, cc: str, src: OfficialSources) -> None:
        try:
            stats = Crawler(self.session_factory, src, max_pages=self.max_pages).run(
                budget_seconds=self.minutes * 60)
            log.info("official: %s crawl done %s", cc, {d: vars(s) for d, s in stats.items()})
        except Exception:
            log.exception("official: %s crawl failed", cc)
        finally:
            self._running.discard(cc)
