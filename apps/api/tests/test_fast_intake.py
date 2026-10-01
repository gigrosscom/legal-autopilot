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


def test_site_goes_to_the_draft_at_once_the_bot_keeps_questions(ctx):
    """Owner 01.10, «3 клика»: on the site the draft comes at once (filled from the story and files, blanks to fill);
    the Telegram bot has no draft screen and keeps its few questions."""
    from .test_e2e import telegram_user

    ctx.container.engine.config.intake_max_questions = -1
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})
    case = out["case"]
    assert case["status"] == "qualified" and case["question"] is None
    assert "черновик" in out["reply"]["message"].lower()
    draft = api.get(f"/v1/cases/{case['id']}/draft").json()
    assert draft["blanks"] and draft["paid"] is False

    tg = telegram_user(ctx)
    case = tg.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]
    assert case["status"] == "intake" and case["question"] is not None


def test_gov_inaction_complaint_is_a_paid_document_and_asks_applicant_data_before_paying(ctx):
    """QA BUG-12 (01.10): a citizen's complaint about a state body's inaction had no scenario — no draft, no bill.
    And the applicant's own data is asked on one screen right before paying, never a bill with blanks."""
    from .test_payment import manual

    manual(ctx)
    ctx.container.settings.payment_requires_contact = False
    ctx.container.engine.config.intake_max_questions = -1
    api = web_user(ctx)
    story = ("Акимат района уже 2 месяца не отвечает на моё заявление о ремонте дороги, подал 01.08.2026 через "
             "eOtinish. Хочу пожаловаться.")
    case = api.post("/v1/cases", expect=201, json={"text": story, "country": "KZ"})["case"]
    cid = case["id"]
    assert case["scenario"]["id"] == "kz.gov.inaction_complaint" and case["status"] == "qualified"
    draft = api.get(f"/v1/cases/{cid}/draft").json()
    assert "[" in draft["visible"] + draft["hidden"] and draft["blanks"]

    r = ctx.client.post(f"/v1/cases/{cid}/payment", headers=api.h, json={"purpose": "document"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "applicant_data_required"
    need = {f["field"] for f in r.json()["detail"]["fields"]}
    assert {"applicant_name", "applicant_iin", "applicant_address", "applicant_phone"} <= need
    api.post(f"/v1/cases/{cid}/facts", json={"values": {
        "applicant_name": "Иванов Иван Иванович", "applicant_iin": "900101300123",
        "applicant_address": "г. Алматы, ул. Абая, 1", "applicant_phone": "+7 701 123 45 67"}})
    pay = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]
    assert pay["amount"] == 1990 and pay["code"]
