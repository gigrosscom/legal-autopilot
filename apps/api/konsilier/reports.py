"""Case status reports and next-step reminders, by e-mail to the client (plus the site inbox / Telegram).

- When a case moves (status, a document prepared/sent/answered, a new question, papers to sign), the client
  gets a report: where the case is, what is done, the deadline, and the next step with full instructions.
- When nothing moves for `report_every_days`, a reminder with the same next step goes out, at most
  `report_max_nudges` times in a row; closed cases get nothing.
- E-mail goes only to a verified address (an e-mail identity) and only while the client keeps it on.
- The first time a case is seen only a baseline is stored, so switching this on does not mass-mail old cases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.models import Agreement, Case, User
from .core.notify import verified_email
from .core.state_machine import BOARD_COLUMNS, CaseStatus

log = logging.getLogger(__name__)

DEBOUNCE = timedelta(minutes=10)  # several quick changes → one report


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fingerprint(session: Session, case: Case) -> str:
    """What a report describes; a change means there is something new to tell."""
    acts = ";".join(f"{a.action_id}:{a.status}:{a.approval_status}" for a in case.actions)
    ags = ";".join(f"{a.kind}:{a.status}" for a in session.scalars(select(Agreement).where(Agreement.case_id == case.id)))
    return f"{case.status}|{case.pending_field or ''}|{acts}|{ags}|{case.hold_reason or ''}"[:500]


def build_report(view: dict[str, Any], pack: Any, lang: str, kind: str, site_url: str,
                 agreements: list[dict[str, Any]]) -> tuple[str, str]:
    """Subject and plain-text body in the case language, from the pack's `reports.*` texts."""
    t = lambda key, **kw: pack.t(lang, f"reports.{key}", **kw)  # noqa: E731
    title = (view.get("scenario") or {}).get("title") or ((view.get("coverage") or {}).get("dispute") or {}).get("title") \
        or t("untitled")
    columns = [c for c, _ in BOARD_COLUMNS]
    stage_n = columns.index(view["stage"]) + 1 if view.get("stage") in columns else 0
    link = f"{site_url.rstrip('/')}/case/{view['id']}"
    lines = [t("hello"), "", t("status", title=title, status=view["status_label"], n=stage_n, total=len(columns)), ""]

    done = []
    for a in view.get("actions", []):
        if a["kind"] != "document":
            continue
        if a.get("submitted_at"):
            s = t("done_submitted", title=a["title"], date=a["submitted_at"][:10])
            if a.get("response_label"):
                s += " " + t("done_response", response=a["response_label"])
            done.append(s)
        elif a["status"] == "ready":
            done.append(t("done_ready", title=a["title"]))
    if done:
        lines += [t("done_title")] + [f"• {d}" for d in done] + [""]

    deadline = next((a["deadline"] for a in reversed(view.get("actions", [])) if a.get("deadline")
                     and a["deadline"]["status"] == "active"), None)
    if deadline:
        lines += [t("deadline", date=deadline["due_date"]), ""]

    lines.append(t("next_title"))
    step: list[str] = []
    q = view.get("question")
    ready = next((a for a in view.get("actions", []) if a["status"] == "ready" and a["kind"] == "document"), None)
    to_sign = [a for a in agreements if a["status"] == "awaiting_customer"]
    if view.get("safety", {}).get("hold_reason"):
        step.append(t("next_hold"))
    elif q:
        step.append(t("next_question", question=q["text"]))
    elif ready:
        step.append(t("next_document", title=ready["title"]))
        step += [f"{i}. {s.replace('**', '')}" for i, s in enumerate(ready.get("instructions") or [], 1)]
    elif view["status"] == CaseStatus.AWAITING_RESPONSE.value:
        step.append(t("next_wait"))
    elif (view.get("proposal") or {}).get("message"):
        step.append(view["proposal"]["message"])
    elif view["status"] == CaseStatus.HANDED_TO_LAWYER.value:
        step.append(t("next_lawyer"))
    else:
        step.append(t("next_open"))
    if to_sign:
        step.append(t("next_sign", titles=", ".join(f"«{a['title']}»" for a in to_sign)))
    lines += step + ["", t("open_case", link=link), "", t("footer", link=f"{site_url.rstrip('/')}/account")]

    subject = t("subject_reminder" if kind == "reminder" else "subject_update", title=title, status=view["status_label"])
    return subject, "\n".join(lines)


class CaseReporter:
    def __init__(self, container: Any):
        self.container = container

    @property
    def settings(self) -> Any:
        return self.container.settings

    @property
    def engine(self) -> Any:
        return self.container.engine

    def tick(self, session: Session, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        sent = 0
        cases = session.scalars(select(Case).where(Case.status != CaseStatus.RESOLVED.value)).all()
        for case in cases:
            state = fingerprint(session, case)
            if case.report_state is None or case.reported_at is None:
                case.report_state, case.reported_at, case.report_nudges = state, now, 0  # baseline, no mail
                continue
            last = _aware(case.reported_at)
            if state != case.report_state:
                if now - last < DEBOUNCE:
                    continue
                kind = "update"
            elif now - last >= timedelta(days=self.settings.report_every_days) \
                    and case.report_nudges < self.settings.report_max_nudges:
                kind = "reminder"
            else:
                continue
            try:
                if self._send(session, case, kind):
                    sent += 1
            except Exception as e:  # a report must never break the scheduler
                log.warning("case report %s failed: %s", case.id, e)
            case.report_state, case.reported_at = state, now
            case.report_nudges = 0 if kind == "update" else case.report_nudges + 1
        return sent

    def _send(self, session: Session, case: Case, kind: str) -> bool:
        from .api.lawyers import _lawyer_block
        from .api.views import case_view

        user = session.get(User, case.owner_id)
        pack = self.engine.pack_of(case)
        lang = pack.lang(case.language)
        view = case_view(self.engine, session, case)
        agreements = _lawyer_block(session, self.container, case)["agreements"] if case.lawyer_application_id else []
        subject, body = build_report(view, pack, lang, kind, self.settings.public_site_url, agreements)
        self.engine.notifier.notify(session, case, f"report_{kind}", body)  # site inbox / Telegram
        to = verified_email(session, user)
        email = self.container.email_sender
        if to and email is not None:
            email.send(to, subject, body)
            return True
        return False
