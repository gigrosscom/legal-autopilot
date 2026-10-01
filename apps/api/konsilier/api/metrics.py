"""Investor / traction metrics for the admin: funnel, outcomes, money, weekly growth. Counted from real
records only (cases, actions, outcomes), never estimated."""

from __future__ import annotations

import csv
import io
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..container import Container
from ..core.engine import TRUST
from ..core.models import Action, Case, Invoice, LawyerApplication, Outcome, User, WaitlistEntry
from ..core.llm.spend import usage_summary
from ..zann.corpus import corpus_metrics
from ..zann.court import court_metrics
from .chat import chat_latency, chat_usage_today
from .deps import get_container, get_session, require_admin
from .referral import referral_metrics

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])

POSITIVE = ("won", "partial", "settled")


def _week(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def compute(session: Session, weeks: int = 12, settings: Settings | None = None) -> dict[str, Any]:
    # test accounts (production smoke checks) are left out of every figure
    tests = set(session.scalars(select(User.id).where(User.is_test.is_(True))).all())
    cases = [c for c in session.execute(select(Case.id, Case.created_at, Case.status, Case.scenario_id,
                                                Case.coverage_level, Case.jurisdiction, Case.amount_at_stake,
                                                Case.currency, Case.owner_id)).all() if c.owner_id not in tests]
    real = {c.id for c in cases}
    actions = [a for a in session.execute(select(Action.case_id, Action.created_at, Action.kind, Action.submitted_at,
                                                 Action.response_class)).all() if a.case_id in real]
    outcomes = [o for o in session.execute(select(Outcome.case_id, Outcome.result, Outcome.amount_recovered,
                                                  Outcome.currency, Outcome.days_to_resolution,
                                                  Outcome.scenario_id)).all() if o.case_id in real]

    docs = [a for a in actions if a.kind != "handoff"]
    has_doc = {a.case_id for a in docs}
    submitted = {a.case_id for a in docs if a.submitted_at}
    responded = {a.case_id for a in docs if a.response_class}
    positive = {o.case_id for o in outcomes if o.result in POSITIVE}
    classified = {c.id for c in cases if c.scenario_id or c.coverage_level == "lawyer"}
    past_intake = {c.id for c in cases if c.status != "intake"}

    funnel = [
        {"step": "created", "cases": len(cases)},
        {"step": "classified", "cases": len(classified)},
        {"step": "intake_done", "cases": len(past_intake)},
        {"step": "document_ready", "cases": len(has_doc)},
        {"step": "submitted", "cases": len(submitted)},
        {"step": "response", "cases": len(responded)},
        {"step": "resolved_positive", "cases": len(positive)},
    ]

    def money(rows: list[tuple[Any, Any]]) -> dict[str, str]:
        out: dict[str, Decimal] = {}
        for amount, cur in rows:
            if amount is not None:
                out[cur or "?"] = out.get(cur or "?", Decimal(0)) + Decimal(str(amount))
        return {k: str(v) for k, v in out.items()}

    days = [o.days_to_resolution for o in outcomes if o.days_to_resolution is not None]
    now = datetime.now(timezone.utc)
    start = now - timedelta(weeks=weeks)
    series: dict[str, Counter] = {}
    for i in range(weeks):
        series[_week(start + timedelta(weeks=i + 1))] = Counter()
    def bump(when: datetime | None, key: str) -> None:
        if when is not None and _aware(when) > start:
            series.setdefault(_week(_aware(when)), Counter())[key] += 1
    for c in cases:
        bump(c.created_at, "cases")
    for a in docs:
        bump(a.created_at, "documents")
        bump(a.submitted_at, "submitted")
    for u in session.execute(select(User.created_at).where(User.is_test.is_(False))).scalars():
        bump(u, "users")

    today = now.date()
    new_users_today = sum(1 for u in session.execute(select(User.created_at).where(User.is_test.is_(False))).scalars()
                          if u is not None and _aware(u).date() == today)
    owners = {c.owner_id for c in cases}
    repeat = sum(1 for n in Counter(c.owner_id for c in cases).values() if n > 1)
    out = {
        "generated_at": now.isoformat(),
        "totals": {
            "users": session.scalar(select(func.count()).select_from(User).where(User.is_test.is_(False))) or 0,
            "users_with_case": len(owners),
            "repeat_users": repeat,
            "cases": len(cases),
            "documents": len(docs),
            "submitted": len(submitted),
            "handed_to_lawyer": sum(1 for c in cases if c.status == "handed_to_lawyer"),
            "lawyer_applications": session.scalar(select(func.count()).select_from(LawyerApplication)) or 0,
            "waitlist": session.scalar(select(func.count()).select_from(WaitlistEntry)) or 0,
        },
        "today": {  # UTC day
            "users": new_users_today,
            "cases": sum(1 for c in cases if c.created_at is not None and _aware(c.created_at).date() == today),
            "documents": sum(1 for a in docs if a.created_at is not None and _aware(a.created_at).date() == today),
        },
        "funnel": funnel,
        "outcomes": dict(Counter(o.result for o in outcomes)),
        "money": {
            "at_stake": money([(c.amount_at_stake, c.currency) for c in cases]),
            "recovered": money([(o.amount_recovered, o.currency) for o in outcomes]),
        },
        "median_days_to_resolution": statistics.median(days) if days else None,
        "levels": dict(Counter("unclassified" if not c.scenario_id and c.coverage_level == "verified"
                               else c.coverage_level for c in cases)),
        "countries": dict(Counter(c.jurisdiction or "—" for c in cases)),
        "top_scenarios": Counter(c.scenario_id for c in cases if c.scenario_id).most_common(10),
        "referral": referral_metrics(session),
        "payments": payment_metrics(session, tests, now),
        "zann": corpus_metrics(session),  # the Zann law corpus collected from adilet (konsilier/zann/corpus.py)
        "zann_court": court_metrics(session),  # court practice from sud.kz (konsilier/zann/court.py)
        "weekly": [{"week": w, **{k: series[w].get(k, 0) for k in ("users", "cases", "documents", "submitted")}}
                   for w in sorted(series)][-weeks:],
    }
    if settings is not None:  # consultation chat today: who answered, refusals, Claude spend against its budget
        out["chat"] = chat_usage_today(session, settings)
        # time to the chat's first words, last 24 h (p50 / p95, by provider): the /ops tile «Ответ чата»
        out["chat_latency"] = chat_latency(session)
        out["claude"] = usage_summary(session, daily_usd=settings.llm_daily_budget_usd,
                                      monthly_usd=settings.llm_monthly_budget_usd)
    return out


def payment_metrics(session: Session, tests: set[Any], now: datetime) -> dict[str, Any]:
    """Real payments only (the test «stub» method and test accounts are left out): paid bills, paying clients,
    revenue by currency (all time and today, UTC), and bills waiting for the desk's confirmation."""
    rows = [i for i in session.execute(select(Invoice.user_id, Invoice.status, Invoice.amount, Invoice.currency,
                                              Invoice.purpose, Invoice.decided_at, Invoice.decided_by)
                                       .where(Invoice.method != "stub")).all() if i.user_id not in tests]
    # owner 02.10: a document given on trust is not revenue until the desk finds the money — the KPI «оплаченные
    # документы» counts confirmed payments only; the trusted ones are counted apart
    on_trust = [i for i in rows if i.status == "paid" and i.decided_by == TRUST]
    paid = [i for i in rows if i.status == "paid" and i.decided_by != TRUST]
    today = now.date()

    def revenue(items: list[Any]) -> dict[str, str]:
        out: dict[str, Decimal] = {}
        for i in items:
            out[i.currency or "?"] = out.get(i.currency or "?", Decimal(0)) + Decimal(str(i.amount))
        return {k: str(v) for k, v in out.items()}
    paid_today = [i for i in paid if i.decided_at is not None and _aware(i.decided_at).date() == today]
    return {
        "paid": len(paid),
        "paid_clients": len({i.user_id for i in paid}),
        "paid_plans": sum(1 for i in paid if i.purpose == "plan"),
        "paid_today": len(paid_today),
        "revenue": revenue(paid),
        "revenue_today": revenue(paid_today),
        "awaiting_confirmation": sum(1 for i in rows if i.status == "awaiting_confirmation"),
        "on_trust": len(on_trust),
        "on_trust_amount": revenue(on_trust),
    }


@router.get("/metrics")
def metrics(weeks: int = 12, session: Session = Depends(get_session),
            container: Container = Depends(get_container)) -> dict[str, Any]:
    return compute(session, max(1, min(weeks, 104)), container.settings)


@router.get("/metrics.csv")
def metrics_csv(weeks: int = 12, session: Session = Depends(get_session)) -> Response:
    """Weekly series and funnel as CSV — for a data room or a spreadsheet."""
    m = compute(session, max(1, min(weeks, 104)))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["week", "new_users", "new_cases", "documents", "submitted"])
    for r in m["weekly"]:
        w.writerow([r["week"], r["users"], r["cases"], r["documents"], r["submitted"]])
    w.writerow([])
    w.writerow(["funnel_step", "cases"])
    for r in m["funnel"]:
        w.writerow([r["step"], r["cases"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=konsilier-metrics.csv"})
