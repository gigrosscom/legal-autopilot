from datetime import date

import pytest

from konsilier.core.fields import FieldError, display, normalize
from konsilier.core.pii import PiiVault
from konsilier.core.scenario.schema import IntakeField


def test_redact_and_restore_roundtrip():
    v = PiiVault()
    v.register("person", "Иванов Иван Иванович")
    text = ("Я, Иванов Иван Иванович, ИИН 900101300123, счёт KZ12345678901234567890, "
            "почта ivan@example.com, тел +7 701 123 45 67, сумма 150000")
    red = v.redact(text)
    for secret in ("Иванов", "900101300123", "KZ1234", "ivan@example.com", "701 123"):
        assert secret not in red
    assert "[PERSON_1]" in red and "[ID_NUMBER_1]" in red and "[ACCOUNT_1]" in red
    assert "150000" in red  # amounts are not PII
    assert v.restore(red) == text


def test_labels_are_stable_across_calls():
    v = PiiVault()
    a = v.redact("ИИН 900101300123")
    b = v.redact("повторно 900101300123 и 880202400456")
    assert "[ID_NUMBER_1]" in a and "[ID_NUMBER_1]" in b and "[ID_NUMBER_2]" in b
    v2 = PiiVault(v.mapping)  # restored from DB
    assert v2.restore("[ID_NUMBER_2]") == "880202400456"


def test_normalize_types():
    today = date(2026, 9, 25)
    assert normalize(IntakeField(name="d", type="date"), "12.08.2026", today) == "2026-08-12"
    with pytest.raises(FieldError, match="date_future"):
        normalize(IntakeField(name="d", type="date"), "2027-01-01", today)
    assert normalize(IntakeField(name="m", type="money"), "150 000 тг", today) == "150000.00"
    assert normalize(IntakeField(name="m", type="money"), "1.500.000", today) == "1500000.00"
    with pytest.raises(FieldError):
        normalize(IntakeField(name="m", type="money"), "много", today)
    assert normalize(IntakeField(name="i", pattern=r"^\d{12}$"), "900101 300123", today) == "900101300123"
    with pytest.raises(FieldError, match="pattern"):
        normalize(IntakeField(name="i", pattern=r"^\d{12}$"), "123", today)
    with pytest.raises(FieldError, match="phone"):
        normalize(IntakeField(name="p", type="phone"), "12345", today)


def test_display():
    assert display(IntakeField(name="m", type="money"), "150000.00") == "150 000"
    assert display(IntakeField(name="d", type="date"), "2026-08-12") == "12.08.2026"
