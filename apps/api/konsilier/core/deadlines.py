"""Deadlines and reminders.

``DeadlineScheduler`` is the seam for durable workflows: the MVP keeps state in
the DB and polls it (``tick``) from APScheduler; a Temporal implementation can
replace it by starting a workflow in ``schedule`` and sleeping until each reminder.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .models import Action, Case, Deadline
from .notify import Notifier
from .packs import PackRegistry

log = logging.getLogger(__name__)


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
        with self.session_factory() as session:
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
                                             pack.t(lang, "reminders.expired", action=title, date=due_s))
                        sent_marks.append("expired")
                        sent += 1
                    dl.status = "expired"
                else:
                    for before in sorted(dl.remind_before_days):  # closest first
                        mark = f"d-{before}"
                        if days_left <= before and mark not in sent_marks:
                            key = "reminders.due_today" if before == 0 else "reminders.before"
                            self.notifier.notify(session, case, "deadline_reminder",
                                                 pack.t(lang, key, action=title, date=due_s, days=days_left))
                            sent_marks.append(mark)
                            sent += 1
                            # only the closest reminder fires if several are overdue at once
                            for other in dl.remind_before_days:
                                if other > before and f"d-{other}" not in sent_marks:
                                    sent_marks.append(f"d-{other}")
                dl.reminders_sent = sent_marks
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
