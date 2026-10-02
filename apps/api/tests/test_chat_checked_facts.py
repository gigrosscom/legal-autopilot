"""ZANN 02.10: the chat model opens no article (0 tool calls in 10 of 10 QA cases), so deadlines and bodies came from
memory — «10 рабочих дней» for the motor insurer (the law says 5), the cooling-off period as the first step three
months after the loan, «приостановить работу» (a Russian rule). The country rules now carry the facts checked on
adilet.zan.kz; this test keeps them in the chat prompt."""

from __future__ import annotations

from pathlib import Path

from konsilier.core.packs import PackRegistry

RULES = " ".join(PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ").manifest.chat_rules.split())


def test_checked_terms():
    for fact in ("10 calendar days of receiving the claim", "art. 42-4", "never over 20 calendar days",
                 "14 calendar days of the insurance contract", "art. 842 p. 2", "answer within 5 working days",
                 "insurance ombudsman", "art. 29-1", "art. 18 p. 1", "1.25 × the National Bank base rate", "art. 159",
                 "art. 64", "art. 51-4"):
        assert fact in RULES, fact


def test_no_invented_terms():
    assert "never a number of days" in RULES
    assert "no right to stop working until wages are paid" in RULES
    assert "never «обязательный досудебный порядок по закону»" in RULES
