"""Work started by a request that must not hold up its answer (writing a document's text ahead, preparing a paid
document, making the PDF). It runs once the request's transaction is committed, in its own session."""
from __future__ import annotations

import logging
import threading
from typing import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

from ..container import Container

log = logging.getLogger(__name__)


def after_commit(session: Session, container: Container, job: Callable[[Session], object], name: str) -> None:
    """Run ``job(new_session)`` after ``session`` commits. BACKGROUND_JOBS: thread (default), inline (tests that
    check the result), off (other tests: the job is skipped)."""
    mode = container.settings.background_jobs
    if mode == "off":
        return

    def run() -> None:
        with container.session_factory() as s:
            try:
                job(s)
                s.commit()
            except Exception:  # noqa: BLE001 — the scheduler and the page retry what matters
                s.rollback()
                log.exception("background job %s failed", name)

    def fire(_session: Session) -> None:
        if mode == "inline":
            run()
        else:
            threading.Thread(target=run, name=f"bg-{name}", daemon=True).start()

    event.listen(session, "after_commit", fire, once=True)
