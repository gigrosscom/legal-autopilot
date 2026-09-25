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
    S.INTAKE: frozenset({S.QUALIFIED}),
    S.QUALIFIED: frozenset({S.ACTION_READY}),
    S.ACTION_READY: frozenset({S.SUBMITTED}),
    S.SUBMITTED: frozenset({S.AWAITING_RESPONSE}),
    S.AWAITING_RESPONSE: frozenset({S.RESOLVED, S.ESCALATED}),
    S.ESCALATED: frozenset({S.ACTION_READY, S.HANDED_TO_LAWYER, S.RESOLVED}),
    S.HANDED_TO_LAWYER: frozenset({S.RESOLVED}),
    S.RESOLVED: frozenset(),
}

TERMINAL = frozenset({S.RESOLVED})


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
