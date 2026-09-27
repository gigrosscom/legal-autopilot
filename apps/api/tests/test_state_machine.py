import itertools

import pytest

from konsilier.core.state_machine import TRANSITIONS, CaseStatus, InvalidTransition, assert_transition, can_transition

S = CaseStatus

ALLOWED = {
    (S.INTAKE, S.QUALIFIED),
    (S.INTAKE, S.HANDED_TO_LAWYER),  # coverage level 3 (ADR 0001)
    (S.QUALIFIED, S.ACTION_READY),
    (S.QUALIFIED, S.HANDED_TO_LAWYER),  # coverage level 3 (ADR 0001)
    (S.ACTION_READY, S.SUBMITTED),
    (S.SUBMITTED, S.AWAITING_RESPONSE),
    (S.AWAITING_RESPONSE, S.RESOLVED),
    (S.AWAITING_RESPONSE, S.ESCALATED),
    (S.ESCALATED, S.ACTION_READY),
    (S.ESCALATED, S.HANDED_TO_LAWYER),
    (S.ESCALATED, S.RESOLVED),
    (S.HANDED_TO_LAWYER, S.RESOLVED),
}


def test_every_status_has_a_transition_entry():
    assert set(TRANSITIONS) == set(CaseStatus)


@pytest.mark.parametrize("current,target", list(itertools.product(CaseStatus, CaseStatus)))
def test_transition_table(current, target):
    if (current, target) in ALLOWED:
        assert can_transition(current, target)
        assert_transition(current, target)
    else:
        assert not can_transition(current, target)
        with pytest.raises(InvalidTransition) as exc:
            assert_transition(current, target)
        assert current.value in str(exc.value) and target.value in str(exc.value)


def test_resolved_is_terminal():
    assert TRANSITIONS[S.RESOLVED] == frozenset()


def test_forbidden_examples_raise_with_allowed_list():
    with pytest.raises(InvalidTransition, match="allowed from intake: handed_to_lawyer, qualified"):
        assert_transition("intake", "submitted")
    with pytest.raises(InvalidTransition):
        assert_transition(S.RESOLVED, S.INTAKE)
    with pytest.raises(InvalidTransition):
        assert_transition(S.ACTION_READY, S.RESOLVED)  # must go through submission first
