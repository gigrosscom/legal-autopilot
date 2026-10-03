"""ZANN 03.10 (rules R-01…R-35 against the code): R-23 — after the complaint, a lawsuit within a month of its decision
(APC art. 136 p. 1) was in no route; «the lawyer will check the lawsuit» stayed in ru/kk texts although the owner
decided there is no lawyer to promise."""

from __future__ import annotations

from pathlib import Path

from konsilier.core.packs import PackRegistry

PACK = PackRegistry.load(Path(__file__).parents[3] / "packs").pack("KZ")


def test_r23_court_after_the_complaint():
    for key in ("administrative.state_body_inaction", "kz.gov.inaction_complaint"):
        steps = PACK.coverage.routes[key].steps
        assert steps[-1].norm == "АППК РК, ст. 136 п. 1" and "месяца" in steps[-1].why["ru"], key


def test_no_lawyer_promised_in_texts():
    for lang in ("ru", "kk"):
        text = (Path(__file__).parents[3] / "packs/kz/i18n" / f"{lang}.yaml").read_text("utf-8")
        for phrase in ("юрист проверит до подачи", "заңгер беру алдында тексереді"):
            assert phrase not in text, (lang, phrase)
