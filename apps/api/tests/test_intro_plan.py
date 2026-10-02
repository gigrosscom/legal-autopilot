"""Backlog #43: the plan shown once the scenario is chosen was the same for every case — «договор, акты, чеки…» and
«буду следить за сроком ответа» even for a visa or a tender. A dispute now names its own documents; a service has its
own plan without receipts and reply deadlines."""

from __future__ import annotations

import pytest

from konsilier.core.models import Case


def _intro(ctx, scenario_id: str, lang: str = "ru") -> str:
    engine = ctx.container.engine
    case = Case(language=lang, jurisdiction="KZ", scenario_id=scenario_id)
    return engine.intro(case, engine.scenario_of(case), engine.pack_of(case))


def test_a_refund_names_its_own_documents(ctx):
    text = _intro(ctx, "kz.consumer.refund")
    assert "чек или квитанция об оплате" in text and "скриншот заказа" in text
    assert "акты" not in text and "{documents}" not in text
    assert "сроком ответа" in text


@pytest.mark.parametrize("sid", ["kz.services.visa_uk", "kz.services.tender_application"])
def test_a_service_has_its_own_plan(ctx, sid):
    for lang in ("ru", "kk"):
        text = _intro(ctx, sid, lang)
        assert "{" not in text and "interview." not in text
        assert "чек" not in text.split("чек-лист")[0] and "договор" not in text and "акты" not in text
        assert "сроком ответа" not in text and "мерзімін" not in text
