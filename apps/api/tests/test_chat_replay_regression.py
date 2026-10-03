"""Regression on real answers. The 121 replies of the two QA-gate runs of 02.10 (bare-10, chats-10, dialog-10 on the
production model and prompt) are already cleaned by the server and checked by ZANN. Cleaning them again must change
nothing: a new rule in the chat's code-side cleaning that cuts a lawful step, a checked term or an article, or leaves
a broken bracket (the «кодекса)» bug of #209), fails here before it reaches a client."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from konsilier.chat import drop_extra_steps, keep_checked, strip_foreign_script, strip_labels, take_offer
from konsilier.core.packs import PackRegistry

REPLIES = yaml.safe_load((Path(__file__).parent / "data" / "qa_gate_replies_2026-10-02.yaml").read_text("utf-8"))


@pytest.fixture(scope="module")
def rules() -> str:
    return PackRegistry.load(Path(__file__).resolve().parents[3] / "packs").pack("KZ").manifest.chat_rules or ""


PARTS = {"1-й ответ": "first", "Решение": "solution", "Основания и детали": "details"}


def _id(r: dict) -> str:
    return f"{r['run']}-{r['case']}-{PARTS.get(r['part'], 'other')}"


@pytest.mark.parametrize("reply", REPLIES, ids=_id)
def test_cleaning_a_clean_reply_changes_nothing(reply, rules):
    text = reply["text"]
    assert strip_labels(text) == text
    assert drop_extra_steps(text) == text
    assert strip_foreign_script(text, "Russian") == text
    assert take_offer(text) == (text.strip(), False)
    cleaned, removed = keep_checked(text, rules, set())
    assert removed == [] and cleaned == text


def test_the_replay_covers_every_case():
    cases = {(r["run"], r["case"]) for r in REPLIES}
    assert len(cases) == 60 and len(REPLIES) >= 100
