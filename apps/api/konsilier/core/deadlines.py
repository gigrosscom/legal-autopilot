"""Deadlines and reminders.

``DeadlineScheduler`` is the seam for durable workflows: the MVP keeps state in
the DB and polls it (``tick``) from APScheduler; a Temporal implementation can
replace it by starting a workflow in ``schedule`` and sleeping until each reminder.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Action, Case, Deadline
from .notify import Notifier
from .packs import PackRegistry

log = logging.getLogger(__name__)

# PostgreSQL advisory lock key of the scheduler tick ("konsilie" in ASCII). Only the `api` container runs the
# periodic tick (deploy/docker-compose.prod.yml: `api2` has SCHEDULER_INTERVAL_SECONDS=0), and this lock is the second
# guard: two processes (a manual POST /v1/admin/scheduler/tick landing on api2, `konsilier tick`, a future replica)
# never run a tick at the same time, so a reminder is never sent twice. Transaction-level (pg_try_advisory_xact_lock):
# released at the tick's commit or rollback, and it works behind a transaction-pooling Odyssey/PgBouncer (port 6432),
# where a session-level lock would not.
TICK_LOCK_KEY = 0x6B6F6E73696C6965


def tick_lock(session: Session) -> bool:
    """Take the tick lock for this transaction; False when another process is ticking right now (SQLite: always True,
    a single process)."""
    if session.get_bind().dialect.name != "postgresql":
        return True
    return bool(session.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": TICK_LOCK_KEY}))


class DeadlineScheduler(Protocol):
    def schedule(self, session: Session, case: Case, action: Action, due: date, norm_ref: str | None,
                 remind_before_days: list[int]) -> Deadline: ...

    def cancel_for_action(self, session: Session, action: Action, status: str = "met") -> None: ...

    def tick(self, now: datetime | None = None) -> int: ...


class DbDeadlineScheduler:
    def __init__(self, session_factory: sessionmaker[Session], packs: PackRegistry, notifier: Notifier):
        self.session_factory = session_factory
        self.packs = packs
        self.notifier = notifier
        self._apscheduler = None
        # more periodic jobs sharing the tick and its session (e.g. case reports): fn(session, now) -> sent
        self.extra_jobs: list = []

    # ---- API used by the engine -------------------------------------
    def schedule(self, session: Session, case: Case, action: Action, due: date, norm_ref: str | None,
                 remind_before_days: list[int]) -> Deadline:
        dl = Deadline(case_id=case.id, action_id=action.id, due_date=due, norm_ref=norm_ref,
                      remind_before_days=sorted(set(remind_before_days), reverse=True), reminders_sent=[])
        session.add(dl)
        return dl

    def cancel_for_action(self, session: Session, action: Action, status: str = "met") -> None:
        for dl in session.scalars(select(Deadline).where(Deadline.action_id == action.id,
                                                         Deadline.status == "active")):
            dl.status = status

    # ---- polling ----------------------------------------------------
    def tick(self, now: datetime | None = None) -> int:
        """Send due reminders; mark overdue deadlines expired. Returns messages sent."""
        sent = 0
        # the periodic run passes no time: the extra jobs need one (they compare it with timestamps)
        now = now or datetime.now(timezone.utc)
        with self.session_factory() as session:
            if not tick_lock(session):
                log.info("scheduler tick skipped: another process is running one")
                return 0
            deadlines = session.scalars(select(Deadline).where(Deadline.status == "active")).all()
            for dl in deadlines:
                case = session.get(Case, dl.case_id)
                pack = self.packs.pack(case.jurisdiction)
                today = (now.astimezone(pack.tz) if now else pack.local_now()).date()
                days_left = (dl.due_date - today).days
                action = session.get(Action, dl.action_id)
                scenario = self.packs.scenario(case.scenario_id)
                lang = pack.lang(case.language)
                title = pack.localized(scenario.action(action.action_id).title, lang) or action.action_id
                due_s = dl.due_date.strftime("%d.%m.%Y")
                sent_marks = list(dl.reminders_sent or [])
                if days_left < 0:
                    if "expired" not in sent_marks:
                        self.notifier.notify(session, case, "deadline_expired",
                                             pack.t(lang, "reminders.expired", action=title, date=due_s),
                                             sms="deadline_expired")
                        sent_marks.append("expired")
                        sent += 1
                    dl.status = "expired"
                else:
                    for before in sorted(dl.remind_before_days):  # closest first
                        mark = f"d-{before}"
                        if days_left <= before and mark not in sent_marks:
                            key = "reminders.due_today" if before == 0 else "reminders.before"
                            self.notifier.notify(session, case, "deadline_reminder",
                                                 pack.t(lang, key, action=title, date=due_s, days=days_left),
                                                 sms="deadline_due_today" if days_left == 0 else None)
                            sent_marks.append(mark)
                            sent += 1
                            # only the closest reminder fires if several are overdue at once
                            for other in dl.remind_before_days:
                                if other > before and f"d-{other}" not in sent_marks:
                                    sent_marks.append(f"d-{other}")
                dl.reminders_sent = sent_marks
            for job in self.extra_jobs:
                try:
                    sent += job(session, now)
                except Exception:  # an extra job must never stop deadline reminders
                    log.exception("scheduler job failed")
            session.commit()
        return sent

    # ---- in-process runner -------------------------------------------
    def start(self, interval_seconds: int) -> None:
        if interval_seconds <= 0:
            return
        from apscheduler.schedulers.background import BackgroundScheduler

        self._apscheduler = BackgroundScheduler(timezone="UTC")
        self._apscheduler.add_job(self._safe_tick, "interval", seconds=interval_seconds,
                                  id="deadline-tick", max_instances=1, coalesce=True)
        self._apscheduler.start()

    def stop(self) -> None:
        if self._apscheduler:
            self._apscheduler.shutdown(wait=False)

    def _safe_tick(self) -> None:
        try:
            self.tick()
        except Exception:  # pragma: no cover - background safety
            log.exception("deadline tick failed")
