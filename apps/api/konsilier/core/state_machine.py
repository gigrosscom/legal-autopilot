"""Case lifecycle as an explicit finite state machine."""

from __future__ import annotations

from enum import Enum


class CaseStatus(str, Enum):
    INTAKE = "intake"
    QUALIFIED = "qualified"
    ACTION_READY = "action_ready"
    SUBMITTED = "submitted"
    AWAITING_RESPONSE = "awaiting_response"
    ESCALATED = "escalated"
    HANDED_TO_LAWYER = "handed_to_lawyer"
    RESOLVED = "resolved"


S = CaseStatus

TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    # → handed_to_lawyer from intake/qualified: coverage level 3 (ADR 0001, approved 27.09.2026)
    S.INTAKE: frozenset({S.QUALIFIED, S.HANDED_TO_LAWYER}),
    S.QUALIFIED: frozenset({S.ACTION_READY, S.HANDED_TO_LAWYER}),
    S.ACTION_READY: frozenset({S.SUBMITTED}),
    S.SUBMITTED: frozenset({S.AWAITING_RESPONSE}),
    S.AWAITING_RESPONSE: frozenset({S.RESOLVED, S.ESCALATED}),
    S.ESCALATED: frozenset({S.ACTION_READY, S.HANDED_TO_LAWYER, S.RESOLVED}),
    S.HANDED_TO_LAWYER: frozenset({S.RESOLVED}),
    S.RESOLVED: frozenset(),
}

TERMINAL = frozenset({S.RESOLVED})

# Kanban board (ADR 0001 §15): columns are lifecycle stages, not new statuses. A case always sits in exactly
# one column and never disappears — resolved cases stay in the last one.
BOARD_COLUMNS: tuple[tuple[str, tuple[CaseStatus, ...]], ...] = (
    ("intake", (S.INTAKE,)),
    ("qualified", (S.QUALIFIED,)),
    ("action_ready", (S.ACTION_READY,)),
    ("submitted", (S.SUBMITTED, S.AWAITING_RESPONSE)),
    ("escalated", (S.ESCALATED,)),
    ("handed_to_lawyer", (S.HANDED_TO_LAWYER,)),
    ("resolved", (S.RESOLVED,)),
)


def board_column(status: CaseStatus | str) -> str:
    st = CaseStatus(status)
    return next(col for col, statuses in BOARD_COLUMNS if st in statuses)


class InvalidTransition(Exception):
    def __init__(self, current: CaseStatus | str, target: CaseStatus | str):
        self.current = CaseStatus(current)
        self.target = CaseStatus(target)
        allowed = ", ".join(sorted(s.value for s in TRANSITIONS[self.current])) or "—"
        super().__init__(
            f"Transition {self.current.value} → {self.target.value} is not allowed "
            f"(allowed from {self.current.value}: {allowed})"
        )


def can_transition(current: CaseStatus | str, target: CaseStatus | str) -> bool:
    return CaseStatus(target) in TRANSITIONS[CaseStatus(current)]


def assert_transition(current: CaseStatus | str, target: CaseStatus | str) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current, target)
