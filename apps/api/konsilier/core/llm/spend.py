"""Spend guard for the paid model: it writes only what the documents need, within a daily and a monthly budget.

Every call is checked before it goes out — the task must be one of `allowed_tasks` (routing a case, reading its
documents, writing a document's text) and today's and this month's spend must be under the budgets — and recorded
after it with its tokens and cost. A call the guard refuses goes to the free fallback model instead, so documents
are still made; the operators are told once a day that the budget is used up."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..models import LLMUsage
from .base import Attachment, LLMError

log = logging.getLogger(__name__)

# USD per million tokens (input, output), by model name prefix; the first match wins.
PRICES: tuple[tuple[str, float, float], ...] = (
    ("claude-sonnet", 2.0, 10.0), ("anthropic.claude-sonnet", 2.0, 10.0),
    ("claude-haiku", 1.0, 5.0), ("anthropic.claude-haiku", 1.0, 5.0),
    ("claude-opus", 4.0, 20.0), ("anthropic.claude-opus", 4.0, 20.0),
)


def price_of(model: str) -> tuple[float, float]:
    for prefix, i, o in PRICES:
        if model.startswith(prefix):
            return i, o
    return 5.0, 25.0  # unknown model: count it high rather than low


class SpendGuard:
    def __init__(self, session_factory: sessionmaker[Session], *, daily_usd: float, monthly_usd: float,
                 allowed_tasks: set[str], on_exhausted: Callable[[str], None] | None = None):
        self.session_factory = session_factory
        self.daily_usd, self.monthly_usd, self.allowed_tasks = daily_usd, monthly_usd, allowed_tasks
        self.on_exhausted = on_exhausted
        self._told: str | None = None  # the day the operators were last told

    def spent(self, now: datetime | None = None) -> dict[str, float]:
        now = now or datetime.now(timezone.utc)
        day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
        with self.session_factory() as s:
            today = s.scalar(select(func.coalesce(func.sum(LLMUsage.cost_usd), 0)).where(LLMUsage.day == day))
            this_month = s.scalar(select(func.coalesce(func.sum(LLMUsage.cost_usd), 0))
                                  .where(LLMUsage.month == month))
        return {"today": float(today or 0), "month": float(this_month or 0),
                "daily_budget": self.daily_usd, "monthly_budget": self.monthly_usd}

    def refusal(self, task: str) -> str | None:
        """Why this call may not use the paid model, or None."""
        if task not in self.allowed_tasks:
            return f"task {task} is not allowed on the paid model"
        s = self.spent()
        if s["today"] >= self.daily_usd:
            self._tell(f"дневной лимит ${self.daily_usd:.2f} исчерпан (потрачено ${s['today']:.2f})")
            return "daily budget used up"
        if s["month"] >= self.monthly_usd:
            self._tell(f"месячный лимит ${self.monthly_usd:.2f} исчерпан (потрачено ${s['month']:.2f})")
            return "monthly budget used up"
        return None

    def record(self, task: str, model: str, input_tokens: int, output_tokens: int) -> float:
        i, o = price_of(model)
        cost = input_tokens * i / 1e6 + output_tokens * o / 1e6
        now = datetime.now(timezone.utc)
        with self.session_factory() as s:
            s.add(LLMUsage(day=now.strftime("%Y-%m-%d"), month=now.strftime("%Y-%m"), task=task, model=model,
                           input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 6)))
            s.commit()
        return cost

    def _tell(self, what: str) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._told == day or self.on_exhausted is None:
            return
        self._told = day
        try:
            self.on_exhausted(what)
        except Exception:  # noqa: BLE001 — telling must never stop a document
            log.warning("budget notice failed", exc_info=True)


class BudgetedProvider:
    """The paid provider behind the guard; refused calls go to `fallback` (the free model), or fail."""

    def __init__(self, paid: Any, guard: SpendGuard, fallback: Any = None):
        self.paid, self.guard, self.fallback = paid, guard, fallback

    def model_for(self, task: str) -> str:
        return self.paid.model_for(task)

    def complete_json(self, *, task: str, system: str, user: str, schema: dict[str, Any],
                      attachments: tuple[Attachment, ...] = ()) -> dict[str, Any]:
        why = self.guard.refusal(task)
        if why is not None:
            log.info("paid model not used for %s: %s", task, why)
            if self.fallback is None:
                raise LLMError(f"paid model refused: {why}")
            return self.fallback.complete_json(task=task, system=system, user=user, schema=schema,
                                               attachments=attachments)
        try:
            return self.paid.complete_json(task=task, system=system, user=user, schema=schema,
                                           attachments=attachments)
        except LLMError as e:  # the paid model is down or out of credit: the document is still made
            if self.fallback is None:
                raise
            log.warning("paid model failed for %s, using the free model: %s", task, e)
            return self.fallback.complete_json(task=task, system=system, user=user, schema=schema,
                                               attachments=attachments)
        finally:
            usage = getattr(self.paid, "last_usage", None)
            if usage:
                self.guard.record(task, usage["model"], usage["input_tokens"], usage["output_tokens"])
                self.paid.last_usage = None


def usage_summary(session: Session, *, daily_usd: float, monthly_usd: float) -> dict[str, Any]:
    """The paid model's spend today and this month, by task, against the budgets (for the admin)."""
    now = datetime.now(timezone.utc)
    day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    rows = session.execute(select(LLMUsage.day, LLMUsage.task, func.count(), func.sum(LLMUsage.cost_usd))
                           .where(LLMUsage.month == month).group_by(LLMUsage.day, LLMUsage.task)).all()
    today = sum(float(c or 0) for d, _, _, c in rows if d == day)
    total = sum(float(c or 0) for _, _, _, c in rows)
    by_task: dict[str, dict[str, float]] = {}
    for _, task, n, c in rows:
        t = by_task.setdefault(task, {"calls": 0, "cost_usd": 0.0})
        t["calls"] += int(n)
        t["cost_usd"] = round(t["cost_usd"] + float(c or 0), 4)
    return {"today_usd": round(today, 4), "month_usd": round(total, 4), "daily_budget_usd": daily_usd,
            "monthly_budget_usd": monthly_usd, "by_task": by_task}
