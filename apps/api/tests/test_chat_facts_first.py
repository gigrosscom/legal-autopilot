"""Owner 02.10 / PM #201: facts first, then one solution. QA run on prod 02.10 16:20 (#201): 0 of 10 bare messages got
a question — the old «help at once, never reply with questions alone» above the rule won. The old shape is gone; the
rule's legal limits (never ask where to file, no questions first in danger or a running time limit) stay."""

from __future__ import annotations

from konsilier.chat import FACTS_FIRST_RULE, SYSTEM


def flat(t: str) -> str:
    return " ".join(t.split())


def test_nothing_above_contradicts_facts_first():
    s = flat(SYSTEM)
    for old in ("Help at once, then ask", "Never reply with questions alone", "at most one question",
                "closing question", "Every reply first gives the solution"):
        assert old not in s, old
    assert "Facts first, then one solution" in s


def test_legal_limits_of_the_questions():
    r = flat(FACTS_FIRST_RULE)
    assert "never where to file" in r
    assert "never names, addresses or ID numbers" in r
    assert "life or health is in danger" in r and "time limit may run out" in r
    assert "never also gives the solution" in r
    assert "no greeting or introduction before it" in r
