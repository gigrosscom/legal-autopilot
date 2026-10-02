"""P0 02.10 (PM, case 13a65913): in a claim the seller «ТОО «Тест»» came back as the applicant «Тестов Тест Тестович» —
a part of the applicant's name redacted with the whole-name label. The same must not happen to any other side:
employer, landlord, bank or MFO, state body, the other parent."""

from __future__ import annotations

import pytest

from konsilier.core.engine import group_norms
from konsilier.core.pii import PiiVault

APPLICANT = "Тестов Тест Тестович"
SIDES = [
    ("seller", "20.09.2026 я приобрёл в ТОО «Тест» телефон, продавец отказал в возврате."),
    ("employer", "Я работаю в ТОО «Тест-Строй», работодатель не выплатил зарплату за июль."),
    ("landlord", "Я снимал квартиру у Тестовой А., наймодатель не вернул депозит."),
    ("bank", "АО «Тест Банк» списало с моей карты 40 000 тенге без моего согласия."),
    ("state body", "Акимат района Тест не ответил на моё обращение за 15 рабочих дней."),
    ("other parent", "Отец ребёнка, Тестович Т., алименты не платит."),
]


@pytest.mark.parametrize("side,text", SIDES, ids=[s for s, _ in SIDES])
def test_other_side_is_never_replaced_by_the_applicant(side, text):
    vault = PiiVault()
    vault.register("person", APPLICANT)
    redacted = vault.redact(f"Я, {APPLICANT}. {text}")
    assert APPLICANT not in redacted  # the model never sees the name
    restored = vault.restore(redacted)
    assert restored == f"Я, {APPLICANT}. {text}", (side, redacted, restored)
    # the other side's words never become the applicant's full name
    assert restored.count(APPLICANT) == 1, (side, restored)


def test_parts_keep_their_endings_and_case_labels_stay_stable():
    vault = PiiVault()
    vault.register("person", "Иванов Иван")
    vault.register("person", "Петрова Анна")
    assert vault.restore(vault.redact("Иванову Ивану, ответчик — Петровой")) == "Иванову Ивану, ответчик — Петровой"
    assert "[PERSON_2]" in vault.mapping and vault.mapping["[PERSON_2]"] == "Петрова Анна"


def test_act_named_once_with_its_articles():
    refs = ["Закон Республики Казахстан «О защите прав потребителей», статья 30",
            "Закон Республики Казахстан «О защите прав потребителей», статья 42-4"]
    assert group_norms(refs) == ["Закон Республики Казахстан «О защите прав потребителей», статьи 30 и 42-4"]
