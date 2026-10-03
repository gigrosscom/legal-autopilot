"""Case roadmap: where the case is now, what comes next and when.

Everything is derived deterministically from the scenario (action order, `when`
conditions, deadlines in calendar/business days) and from real case events
(submission dates, registered deadlines, responses). No LLM involved.

The projection is pessimistic on purpose: future steps assume the counterparty
does not satisfy the claim, so the user sees the worst-case horizon, and the
best case ("the counterparty satisfies the claim by the current deadline").
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .models import Action, Case, Deadline
from .packs import JurisdictionPack
from .scenario import ActionSpec, Scenario

# Days we budget for preparing a document (interview, lawyer approval, signing).
PREPARATION_DAYS = 2


@dataclass
class RoadmapStep:
    key: str
    kind: str  # intake | document | handoff | resolution
    title: str
    status: str  # done | current | upcoming | skipped
    conditional: bool = False  # needed only if the previous step fails
    started_on: str | None = None
    finished_on: str | None = None
    due_on: str | None = None  # a real, registered deadline
    estimated_on: str | None = None  # projection
    detail: str = ""
    norm_ref: str | None = None


@dataclass
class Roadmap:
    steps: list[RoadmapStep] = field(default_factory=list)
    best_case_on: str | None = None
    worst_case_on: str | None = None
    open_ended_after_worst: bool = False  # a lawyer step follows with no fixed deadline

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _d(value: datetime | date | None, tz) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(tz).date() if value.tzinfo else value.date()
    return value


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _deadline_end(pack: JurisdictionPack, spec: ActionSpec, start: date) -> date | None:
    if spec.deadline is None:
        return None
    return pack.add_days(start, spec.deadline.calendar_days, spec.deadline.business_days)


def build_roadmap(case: Case, sc: Scenario, pack: JurisdictionPack, deadlines: dict[Any, Deadline],
                  today: date | None = None) -> Roadmap:
    lang = pack.lang(case.language)
    tz = pack.tz
    today = today or pack.local_now().date()
    rm = Roadmap()
    resolved = case.status == "resolved"

    # ---- 1. intake -----------------------------------------------------
    intake_done = case.status != "intake"
    first_action = case.actions[0] if case.actions else None
    rm.steps.append(RoadmapStep(
        key="intake", kind="intake", title=pack.t(lang, "roadmap.intake", default="intake"),
        status="done" if intake_done else "current",
        started_on=_iso(_d(case.created_at, tz)),
        finished_on=_iso(_d(first_action.created_at, tz)) if first_action else None,
        detail=pack.t(lang, "roadmap.intake_detail", default=""),
    ))

    # ---- 2. scenario actions ------------------------------------------
    executed: dict[str, Action] = {a.action_id: a for a in case.actions}
    responses = {a.action_id: a.response_class for a in case.actions}
    cursor = today
    best: date | None = None
    has_estimate = False
    skipped: set[str] = set()

    def ruled_out(spec: ActionSpec) -> bool:
        cond = spec.condition
        if cond is not None and cond.actions & skipped:
            return True  # depends on a step that will never happen
        return _ruled_out(spec, responses)

    for spec in sc.actions:
        title = pack.localized(spec.title, lang) or spec.id
        row = executed.get(spec.id)
        norm = spec.deadline.norm_ref if spec.deadline else None
        if spec.kind == "handoff":
            if row is not None:
                status = "done" if resolved else "current"
                rm.steps.append(RoadmapStep(key=spec.id, kind="handoff", title=title, status=status,
                                            conditional=True, started_on=_iso(_d(row.created_at, tz)),
                                            detail=pack.t(lang, "roadmap.handoff_detail", default="")))
            else:
                status = "skipped" if (resolved or ruled_out(spec)) else "upcoming"
                if status == "skipped":
                    skipped.add(spec.id)
                rm.steps.append(RoadmapStep(key=spec.id, kind="handoff", title=title, status=status,
                                            conditional=True,
                                            detail=pack.t(lang, "roadmap.handoff_detail", default="")))
                if status == "upcoming":
                    rm.open_ended_after_worst = True
            continue

        if row is not None:
            submitted = _d(row.submitted_at, tz)
            dl = deadlines.get(row.id)
            due = dl.due_date if dl else None
            if row.response_class:
                finished = _d(row.responded_at, tz)
                label = pack.t(lang, f"responses.{row.response_class}", default=row.response_class)
                rm.steps.append(RoadmapStep(
                    key=spec.id, kind="document", title=title, status="done", conditional=spec.when is not None,
                    started_on=_iso(_d(row.created_at, tz)), finished_on=_iso(finished), due_on=_iso(due),
                    detail=pack.t(lang, "roadmap.response_detail", default="{response}", response=label),
                    norm_ref=norm))
                cursor = max(cursor, finished or cursor)
                continue
            if submitted:
                end = due or _deadline_end(pack, spec, submitted)
                detail = pack.t(lang, "roadmap.waiting_detail", default="",
                                date=end.strftime("%d.%m.%Y") if end else "")
            else:
                end = _deadline_end(pack, spec, today + timedelta(days=PREPARATION_DAYS))
                key = "roadmap.approval_detail" if row.approval_status == "pending" else "roadmap.ready_detail"
                detail = pack.t(lang, key, default="")
            rm.steps.append(RoadmapStep(
                key=spec.id, kind="document", title=title, status="current", conditional=spec.when is not None,
                started_on=_iso(_d(row.created_at, tz)), due_on=_iso(due),
                estimated_on=None if due else _iso(end), detail=detail, norm_ref=norm))
            if end:
                best = best or end
                cursor = max(cursor, end)
                has_estimate = True
            continue

        # not executed yet
        if resolved or ruled_out(spec):
            skipped.add(spec.id)
            rm.steps.append(RoadmapStep(key=spec.id, kind="document", title=title, status="skipped",
                                        conditional=spec.when is not None, norm_ref=norm))
            continue
        start = cursor + timedelta(days=PREPARATION_DAYS if case.actions or intake_done else 0)
        end = _deadline_end(pack, spec, start + timedelta(days=PREPARATION_DAYS))
        rm.steps.append(RoadmapStep(
            key=spec.id, kind="document", title=title, status="upcoming", conditional=spec.when is not None,
            estimated_on=_iso(end),
            detail=pack.t(lang, "roadmap.if_needed" if spec.when else "roadmap.next_detail", default=""),
            norm_ref=norm))
        if end:
            best = best or end
            cursor = end
            has_estimate = True

    # ---- 3. resolution --------------------------------------------------
    if resolved and case.outcome is not None:
        o = case.outcome
        rm.steps.append(RoadmapStep(
            key="resolution", kind="resolution", title=pack.t(lang, "roadmap.resolution", default="resolution"),
            status="done", finished_on=_iso(_d(o.resolved_at, tz)),
            detail=pack.t(lang, f"outcomes.{o.result}", default=o.result)))
    else:
        rm.best_case_on = _iso(best)
        rm.worst_case_on = _iso(cursor) if has_estimate else None
        rm.steps.append(RoadmapStep(
            key="resolution", kind="resolution", title=pack.t(lang, "roadmap.resolution", default="resolution"),
            status="upcoming", estimated_on=rm.best_case_on,
            detail=pack.t(lang, "roadmap.resolution_detail", default="")))
    return rm


def _ruled_out(spec: ActionSpec, responses: dict[str, str | None]) -> bool:
    """True when every action the condition depends on is answered and it evaluates to False."""
    cond = spec.condition
    if cond is None:
        return False
    if any(responses.get(a) is None for a in cond.actions):
        return False
    return not cond.evaluate(responses)
