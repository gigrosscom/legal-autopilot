"""PM 01.10 (the owner's own case): the draft after at most four questions; what is unknown stays a blank filled
in the draft; «не помню» never blocks; answers that already read as the field need no model call."""

from __future__ import annotations

import pytest

from .test_e2e import web_user

STORY = "Купил подписку на сервис в интернете, списали деньги, услугу не оказали, продавец не возвращает деньги"
CONTRACT = ("Договор оферты\nПродавец: ТОО «Техномир», БИН 123456789012\nАдрес: г. Алматы, пр. Достык, 10\n"
            "Предмет: годовая подписка «Премиум»")
KASPI = "Kaspi Gold. Выписка\n12.08.2026 Покупка ТОО Техномир -150000"


def questions_to_draft(ctx, cap: int) -> tuple[int, dict]:
    ctx.container.engine.config.intake_max_questions = cap
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    for name, text in (("contract.txt", CONTRACT), ("kaspi.txt", KASPI)):
        api.post(f"/v1/cases/{cid}/evidence", expect=201, data={"kind": "other"},
                 files={"file": (name, text.encode(), "text/plain")})
    asked, steps = 0, 0
    case = api.get(f"/v1/cases/{cid}").json()
    while case["status"] == "intake" and case["question"] is not None:
        steps += 1
        assert steps < 40, case["question"]
        q = case["question"]
        if q["type"] == "evidence":
            case = api.answer(cid, "готово" if q.get("uploaded") else "пропустить")["case"]
            continue
        asked += 1
        assert asked < 30
        case = api.answer(cid, "не помню")["case"]  # the worst case: the person knows nothing more
    return asked, case


@pytest.mark.parametrize("cap", [4])
def test_draft_after_at_most_four_questions(ctx, cap):
    before, _ = questions_to_draft(ctx, 0)
    after, case = questions_to_draft(ctx, cap)
    print(f"\nquestions to the draft: before={before} after={after}")
    assert after <= cap < before
    assert case["status"] == "qualified" and case["proposal"]["type"] == "prepare_action"


def test_dont_remember_the_date_leaves_a_blank(ctx):
    ctx.container.engine.config.intake_max_questions = 4
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    case = api.get(f"/v1/cases/{cid}").json()
    for _ in range(30):
        if not case["question"] or case["question"]["field"] == "purchase_date":
            break
        q = case["question"]
        case = api.answer(cid, "пропустить" if q["type"] == "evidence" else "ТОО Техномир")["case"]
        if case["status"] != "intake":
            pytest.skip("the date was not asked")
    out = api.answer(cid, "не помню")
    assert out["reply"]["error"] is None and out["case"]["question"]["field"] != "purchase_date"


def test_plain_answers_skip_the_model(ctx, monkeypatch):
    from konsilier.core import ai
    calls = []
    real = ai.extract_fields
    monkeypatch.setattr(ai, "extract_fields", lambda *a, **k: calls.append(1) or real(*a, **k))
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    case = api.get(f"/v1/cases/{cid}").json()
    plain = {"date": "12.08.2026", "money": "150000", "text": "ТОО Техномир", "email": "shop@mail.kz",
             "longtext": "Списали деньги, услугу не оказали", "phone": "+7 701 123 45 67"}
    n = 0
    while case["status"] == "intake" and case["question"] and n < 6:
        q = case["question"]
        if q["type"] == "evidence":
            case = api.answer(cid, "пропустить")["case"]
            continue
        if q["type"] not in plain:
            break
        calls.clear()
        answer = "123456789012" if q.get("pattern") else plain[q["type"]]
        if "address" in q["field"]:
            answer = "г. Алматы, пр. Достык, 10"
        case = api.answer(cid, answer)["case"]
        assert calls == [], q["field"]
        n += 1
    assert n >= 2


def test_scheduler_extra_jobs_get_the_time(ctx):
    # the periodic run calls tick() with no time: the extra jobs (paid documents, review reminders) got None and
    # failed every time
    got = []
    ctx.container.scheduler.extra_jobs.append(lambda s, now: got.append(now) or 0)
    ctx.container.scheduler.tick()
    assert got and got[0] is not None and got[0].tzinfo is not None
