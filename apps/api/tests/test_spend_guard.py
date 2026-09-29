"""The paid model is used only for document tasks and only within the daily and monthly budgets; what it refuses
goes to the free model, every paid call is recorded with its cost, and the operators are told once a day."""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from konsilier.config import Settings
from konsilier.container import build_container
from konsilier.core.llm.base import LLMError
from konsilier.core.llm.spend import BudgetedProvider, SpendGuard, price_of, usage_summary
from konsilier.core.models import Base

TASKS = {"narrative", "extract_fields"}


class Paid:
    def __init__(self, tokens: tuple[int, int] = (1_000_000, 100_000), fail: bool = False):
        self.calls: list[str] = []
        self.tokens, self.fail = tokens, fail
        self.last_usage: dict[str, Any] | None = None

    def model_for(self, task: str) -> str:
        return "claude-sonnet-5-5"

    def complete_json(self, *, task: str, **_: Any) -> dict[str, Any]:
        self.calls.append(task)
        self.last_usage = {"model": "claude-sonnet-5-5", "input_tokens": self.tokens[0],
                           "output_tokens": self.tokens[1]}
        if self.fail:
            raise LLMError("credit balance too low")
        return {"by": "paid"}


class Free:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, *, task: str, **_: Any) -> dict[str, Any]:
        self.calls.append(task)
        return {"by": "free"}


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/spend.db")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def call(p: BudgetedProvider, task: str = "narrative") -> dict[str, Any]:
    return p.complete_json(task=task, system="s", user="u", schema={})


def test_only_document_tasks_reach_the_paid_model(factory):
    paid, free = Paid(tokens=(100, 10)), Free()
    p = BudgetedProvider(paid, SpendGuard(factory, daily_usd=3, monthly_usd=50, allowed_tasks=TASKS), free)
    assert call(p, "narrative") == {"by": "paid"}
    assert call(p, "chat_reply") == {"by": "free"}
    assert paid.calls == ["narrative"] and free.calls == ["chat_reply"]


def test_every_paid_call_is_recorded_with_its_cost(factory):
    guard = SpendGuard(factory, daily_usd=100, monthly_usd=100, allowed_tasks=TASKS)
    p = BudgetedProvider(Paid(), guard, Free())
    call(p)
    # 1M input × $2 + 0.1M output × $10 = $3
    assert guard.spent()["today"] == pytest.approx(3.0)
    with factory() as s:
        summary = usage_summary(s, daily_usd=100, monthly_usd=100)
    assert summary["by_task"]["narrative"] == {"calls": 1, "cost_usd": 3.0}


def test_daily_budget_stops_the_paid_model_and_tells_the_team_once(factory):
    told: list[str] = []
    paid, free = Paid(), Free()
    guard = SpendGuard(factory, daily_usd=3, monthly_usd=50, allowed_tasks=TASKS, on_exhausted=told.append)
    p = BudgetedProvider(paid, guard, free)
    call(p)  # $3 spent: the budget is used up
    assert call(p) == {"by": "free"}
    assert call(p) == {"by": "free"}
    assert len(paid.calls) == 1 and len(free.calls) == 2
    assert len(told) == 1 and "дневной" in told[0]


def test_monthly_budget_is_enforced(factory):
    guard = SpendGuard(factory, daily_usd=100, monthly_usd=3, allowed_tasks=TASKS)
    p = BudgetedProvider(Paid(), guard, Free())
    call(p)
    assert call(p) == {"by": "free"}


def test_a_failing_paid_model_still_makes_the_document_and_is_counted(factory):
    guard = SpendGuard(factory, daily_usd=100, monthly_usd=100, allowed_tasks=TASKS)
    free = Free()
    assert call(BudgetedProvider(Paid(fail=True), guard, free)) == {"by": "free"}
    assert guard.spent()["today"] == pytest.approx(3.0)


def test_without_a_fallback_a_refusal_is_an_error(factory):
    guard = SpendGuard(factory, daily_usd=0, monthly_usd=0, allowed_tasks=TASKS)
    with pytest.raises(LLMError):
        call(BudgetedProvider(Paid(), guard, None))


def test_unknown_models_are_priced_high():
    assert price_of("claude-haiku-4-5") == (1.0, 5.0)
    assert price_of("something-new") >= price_of("claude-opus-5-5")


def test_chat_and_case_questions_are_off_the_paid_model_by_default(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/c.db", llm_provider="anthropic",
                        anthropic_api_key="test", chat_provider="anthropic", chat_fallback_to_anthropic=True,
                        storage_backend="local", storage_local_dir=tmp_path / "f", smtp_host=None,
                        background_jobs="off", scheduler_interval_seconds=0)
    c = build_container(settings)
    assert c.law_agent is None
    assert c.chat_agent is None
    assert c.chat_fallback_agent is None
    assert isinstance(c.engine.llm_provider, BudgetedProvider)
    c.engine_db.dispose()
