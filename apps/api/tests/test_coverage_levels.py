"""End-to-end over the three coverage levels (ADR 0001) with the mocked LLM."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from konsilier.core.documents import docx_text
from konsilier.core.models import Action, DemandSignal

from .conftest import hide_scenarios
from .test_e2e import ADMIN, admin_approve, statuses, web_user
from .test_pilot_drafts import AI_LINE_RU, DRAFT_WORDS

WAGES = "Работодатель не платит зарплату три месяца, задолженность 450000 тенге"


def _universal_case(api):
    hide_scenarios(api.ctx, "kz.labor.")  # the universal path: no published scenario fits the story
    created = api.post("/v1/cases", expect=201, json={"text": WAGES, "country": "KZ"})
    case = created["case"]
    # owner 02.10: no «Выберите адресата» list — the system takes the step's recipient (pack rule forum_order)
    assert not created["reply"]["options"] and case["coverage"]["options"] == []
    assert case["coverage"]["level"] == "universal"
    assert case["coverage"]["dispute"]["id"] == "labor.unpaid_wages"
    forum = case["coverage"]["forum"]
    assert forum["id"] == "kz.counterparty.claim" and forum["why"].startswith("Индивидуальный трудовой спор сначала рассматривает согласительная комиссия")
    assert case["scenario"]["id"].endswith("kz__counterparty__claim")
    options = {o["id"]: o for o in case["coverage"]["other_forums"]}  # «Другой адресат»
    assert "kz.labor_inspection" in options and "kz.court.district" in options and forum["id"] not in options
    assert all(not o["verified"] for o in options.values())  # nothing in the KZ registry is signed off yet
    return case["id"], options


def test_level1_verified_scenarios_unchanged(ctx):
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине, сломался, продавец не возвращает деньги", "country": "KZ"})
    assert created["case"]["scenario"]["id"] == "kz.consumer.refund"
    # unsigned (reviewed_at: null) → shown as a draft, never as "verified"
    assert created["case"]["coverage"]["level"] == "scenario_draft"
    assert created["case"]["stage"] == "intake"


def test_level2_universal_path_needs_lawyer_approval(ctx):
    ctx.container.engine.config.self_service = False  # the lawyer-review policy (SELF_SERVICE=false)
    api = web_user(ctx)
    cid, _ = _universal_case(api)

    api.post(f"/v1/cases/{cid}/forum", expect=409, json={"forum_id": "kz.police"})  # not a candidate

    out = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.labor_inspection"})
    case = out["case"]
    assert case["scenario"]["id"].startswith("kz.generic.labor__unpaid_wages.employee.")
    assert case["scenario"]["draft"] is True  # universal documents always carry the unsigned note
    assert case["coverage"]["forum"]["id"] == "kz.labor_inspection"
    assert case["coverage"]["upl_notice"]

    answers = {
        "applicant_name": "Иванов Иван Иванович", "applicant_iin": "пропустить", "applicant_address": "Алматы, ул. Абая 1",
        "applicant_phone": "+7 701 123 45 67", "respondent_name": "ТОО «Ромашка»", "event_date": "пропустить",
        "problem_description": "Не платят зарплату с июня", "desired_outcome": "Выплатить долг по зарплате",
        "amount": "450000", "claim_amount": "пропустить",
    }
    q = case["question"]
    while q is not None:  # evidence and the identity document are skipped
        out = api.answer(cid, "пропустить" if q["type"] == "evidence" else answers[q["field"]])
        assert out["reply"]["error"] is None, out["reply"]
        q = out["case"]["question"]

    out = api.post(f"/v1/cases/{cid}/actions/next")
    action = out["case"]["actions"][0]
    assert action["approval_status"] == "pending"  # always, regardless of APPROVAL_REQUIRED_FIRST_N
    assert action["downloadable"] is False
    assert action["addressee"]["kind"] == "forum"

    admin_approve(ctx, action["id"])
    with ctx.container.session_factory() as s:
        a = s.get(Action, uuid.UUID(action["id"]))
        text = docx_text(ctx.container.storage.get(a.docx_key))
    # the labour inspection's term comes from the registry (АППК ст. 76, verified on adilet), not from the model
    assert "Административный процедурно-процессуальный кодекс Республики Казахстан, статья 76" in text
    assert "Работодатель не платит зарплату" in text  # the story (the test model copies it into the request too)
    assert text.count(AI_LINE_RU) == 1 and not DRAFT_WORDS.search(text)

    case = api.get(f"/v1/cases/{cid}").json()
    assert case["stage"] == "action_ready"
    api.post(f"/v1/cases/{cid}/actions/{action['id']}/submitted", json={"via": "user_submits"})
    out = api.post(f"/v1/cases/{cid}/actions/{action['id']}/response", json={"response_class": "refusal"})
    proposal = out["case"]["proposal"]
    assert proposal["type"] == "prepare_action" and proposal["action_id"] == "step_2"  # escalation from data
    with ctx.container.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(DemandSignal)
                        .where(DemandSignal.dispute_type == "labor.unpaid_wages")) == 1


def test_level3_defence_goes_to_lawyer_without_documents(ctx):
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={
        "text": "Меня обвиняют в мошенничестве, возбудили дело против меня", "country": "KZ"})
    case = created["case"]
    assert case["coverage"]["level"] == "lawyer"
    assert case["status"] == "handed_to_lawyer" and case["stage"] == "handed_to_lawyer"
    assert [r["code"] for r in case["coverage"]["reasons"]] == ["defence"]
    assert case["actions"] == [] and case["scenario"] is None
    assert statuses(ctx, case["id"]) == ["handed_to_lawyer"]
    api.post(f"/v1/cases/{case['id']}/actions/next", expect=409)  # no document path for the defence


def test_level3_children_route_to_lawyer(ctx):
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={
        "text": "Отец против: хочу определить через суд, с кем будет жить ребенок", "country": "KZ"})
    assert created["case"]["coverage"]["level"] == "lawyer"
    assert "children" in [r["code"] for r in created["case"]["coverage"]["reasons"]]


def test_alimony_scenario_lawsuit_waits_for_a_lawyer(ctx):
    """Published level-1 scenario with a court document: the lawsuit is released only after a lawyer's check."""
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": "Бывший муж не платит алименты", "country": "KZ"})
    case = created["case"]
    assert case["scenario"]["id"] == "kz.family.alimony"
    assert case["plan"]["lawyer_check"] is True
    answers = {**_ANSWERS, "respondent_name": "Петров Пётр Петрович",
               "desired_outcome": "Взыскать алименты на сына", "applicant_iin": "900101300128",
               "applicant_birth_date": "01.01.1990", "applicant_email": "пропустить",
               "respondent_address": "Алматы, ул. Сатпаева 3", "respondent_iin": "пропустить",
               "children_info": "Петров Алихан Петрович, 01.02.2018"}
    q = case["question"]
    while q is not None:
        out = api.answer(case["id"], "пропустить" if q["type"] == "evidence" else answers[q["field"]])
        assert out["reply"]["error"] is None, out["reply"]
        q = out["case"]["question"]
    action = api.post(f"/v1/cases/{case['id']}/actions/next")["case"]["actions"][0]
    assert action["approval_status"] == "pending" and action["downloadable"] is False


def test_unclassified_story_asks_for_details(ctx):
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": "Здравствуйте, помогите пожалуйста", "country": "KZ"})
    assert created["case"]["status"] == "intake"
    assert created["case"]["coverage"]["level"] == "pending"  # never "verified" before classification
    assert "не хватает деталей" in created["reply"]["message"]


def test_coverage_and_forums_endpoints(ctx):
    cov = ctx.client.get("/v1/coverage?lang=ru").json()
    kz = next(c for c in cov["countries"] if c["country"] == "KZ")
    assert kz["cells"]["consumer"] == "scenario_draft"  # published but not signed off by a lawyer
    assert kz["cells"]["labor"] == "scenario_draft"  # published labour scenarios, not signed by a lawyer
    assert kz["cells"]["inheritance"] == "universal"
    assert kz["cells"]["commercial"] == "universal"  # a business claim letter to the counterparty; a lawsuit after a lawyer
    assert all(c["country"] != "XX" for c in cov["countries"])  # test packs hidden
    forums = ctx.client.get("/v1/forums?country=KZ&branch=labor").json()
    assert {f["id"] for f in forums} >= {"kz.labor_inspection", "kz.court.district"}
    assert all(f["verified"] is False for f in forums)


def test_admin_board_keeps_every_case_in_one_column(ctx):
    api = web_user(ctx)
    _universal_case(api)
    api.post("/v1/cases", expect=201, json={"text": "Меня обвиняют в мошенничестве, возбудили дело против меня",
                                            "country": "KZ"})
    board = ctx.client.get("/v1/admin/board", headers=ADMIN).json()
    cols = {c["id"]: c["cards"] for c in board["columns"]}
    assert list(cols) == ["intake", "qualified", "action_ready", "submitted", "escalated", "handed_to_lawyer",
                          "resolved"]
    assert [c["coverage_level"] for c in cols["intake"]] == ["universal"]
    assert [c["coverage_level"] for c in cols["handed_to_lawyer"]] == ["lawyer"]
    assert sum(len(v) for v in cols.values()) == 2
    universal = ctx.client.get("/v1/admin/cases?coverage_level=universal", headers=ADMIN).json()
    assert len(universal) == 1 and universal[0]["title"] == "Невыплата зарплаты"
    demand = ctx.client.get("/v1/admin/demand", headers=ADMIN).json()
    assert {d["dispute_type"] for d in demand} == {"labor.unpaid_wages", "criminal.defence"}


def test_forum_drafts_are_validated_and_not_live(ctx):
    good = {"id": "kz.ombudsman.children", "type": "ombudsman", "name": {"ru": "Уполномоченный по правам ребёнка",
            "kk": "Бала құқықтары жөніндегі уәкіл"}, "accepts": [{"branches": ["family"]}],
            "document_types": ["complaint"], "submission": [{"kind": "post"}], "languages": ["ru", "kk"],
            "legal_effect": "advisory", "source": "TODO"}
    r = ctx.client.post("/v1/admin/forum-drafts", headers=ADMIN, json={"country": "KZ", "data": good})
    assert r.status_code == 201, r.text
    bad = {**good, "type": "religious"}  # not a forum type: only state and state-recognised bodies
    assert ctx.client.post("/v1/admin/forum-drafts", headers=ADMIN,
                           json={"country": "KZ", "data": bad}).status_code == 422
    other = {**good, "id": "uz.x.y"}
    assert ctx.client.post("/v1/admin/forum-drafts", headers=ADMIN,
                           json={"country": "KZ", "data": other}).status_code == 422
    listing = ctx.client.get("/v1/admin/forums?country=KZ", headers=ADMIN).json()
    assert [d["forum_id"] for d in listing["drafts"]] == ["kz.ombudsman.children"]
    assert "kz.ombudsman.children" not in {f["id"] for f in listing["registry"]}  # drafts never go live directly


def test_planned_countries_are_soon_and_accept_no_cases(ctx):
    cov = ctx.client.get("/v1/coverage?lang=ar").json()
    uae = next(c for c in cov["countries"] if c["country"] == "AE")
    assert uae["status"] == "planned" and set(uae["cells"].values()) == {"soon"}
    assert uae["name"] == "الإمارات العربية المتحدة"
    assert {"UZ", "KG", "TR", "SA", "EG"} <= {c["country"] for c in cov["countries"]}
    api = web_user(ctx)
    r = api.c.post("/v1/cases", headers=api.h, json={"text": "Работодатель не платит зарплату", "country": "UZ"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "country_planned"
    assert all(p["country"] == "KZ" for p in ctx.client.get("/v1/packs").json())  # only live packs listed
    for cc in ("AE", "UZ"):
        pack = ctx.container.packs.pack(cc)
        assert pack.scenarios == {} and not pack.coverage.has_registry  # no invented law


def test_only_state_forums_are_offered(ctx):
    api = web_user(ctx)
    # an old client may still send religious_path: it is ignored, only state bodies exist in the registry
    out = api.post("/v1/cases", expect=201, json={"text": "I want a divorce from my husband", "country": "XX",
                                                   "language": "en", "religious_path": True})
    cov = out["case"]["coverage"]
    assert cov["forum"]["id"] == "xx.court.civil"  # single state candidate chosen
    assert "religious_requested" not in cov and "religious" not in cov["forum"]


def test_unsigned_level1_scenario_is_shown_as_draft():
    from konsilier.core.qualifier import display_level

    assert display_level("verified", True) == "scenario_draft"
    assert display_level("verified", False) == "verified"
    assert display_level("universal", True) == "universal"
    assert display_level("lawyer", True) == "lawyer"


_ANSWERS = {
    "applicant_name": "Иванов Иван Иванович", "applicant_iin": "пропустить", "applicant_address": "Алматы, ул. Абая 1",
    "applicant_phone": "+7 701 123 45 67", "respondent_name": "ТОО «Ромашка»", "event_date": "пропустить",
    "problem_description": "Не платят зарплату с июня", "desired_outcome": "Выплатить долг по зарплате",
    "amount": "450000", "claim_amount": "пропустить",
}


def _fill_and_prepare(api, cid, case):
    q = case["question"]
    while q is not None:  # evidence and the identity document are skipped
        out = api.answer(cid, "пропустить" if q["type"] == "evidence" else _ANSWERS[q["field"]])
        assert out["reply"]["error"] is None, out["reply"]
        q = out["case"]["question"]
    return api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]


def test_self_service_complaint_is_released_with_step_by_step_filing(ctx):
    api = web_user(ctx)
    cid, _ = _universal_case(api)
    case = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.labor_inspection"})["case"]
    action = _fill_and_prepare(api, cid, case)
    assert action["approval_status"] == "not_required" and action["downloadable"] is True
    steps = action["instructions"]
    assert steps[0].startswith("Скачайте «Жалоба»")
    assert any("eotinish.kz" in s and "ЭЦП" in s for s in steps)  # portal walk-through, not one line
    assert any("государственная инспекция труда" in s for s in steps)  # the chosen body is named
    assert any(s.startswith("Что приложить:") for s in steps)
    assert steps[-1].startswith("После подачи нажмите")


def test_pre_trial_claim_goes_to_the_other_party(ctx):
    api = web_user(ctx)
    cid, options = _universal_case(api)  # the system took the pre-trial claim to the other party first (owner 02.10)
    case = api.get(f"/v1/cases/{cid}").json()
    action = _fill_and_prepare(api, cid, case)
    assert action["approval_status"] == "not_required"
    assert action["addressee"]["name"] == "ТОО «Ромашка»"  # the claim is addressed to the employer itself
    with ctx.container.session_factory() as s:
        text = docx_text(ctx.container.storage.get(s.get(Action, uuid.UUID(action["id"])).docx_key))
    assert "ПРЕТЕНЗИЯ" in text and "Выплатить долг по зарплате" in text
    assert any("ТОО «Ромашка»" in s for s in action["instructions"])


def test_court_documents_still_wait_for_a_lawyer(ctx):
    api = web_user(ctx)
    cid, _ = _universal_case(api)
    case = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.court.district"})["case"]
    action = _fill_and_prepare(api, cid, case)
    assert action["approval_status"] == "pending" and action["downloadable"] is False


B2B = ("я ип заключил договор с тоо на поставку напитков, условие было что они будут делать рекламу а мы купим у них "
       "наличкой и продавать, но они не делали рекламу и мы не продали товар теперь мы хотим вернуть деньги за не "
       "проданный товар, что делать?")


def test_business_dispute_is_never_a_consumer_case(ctx):
    """A sole trader against a company (the first real client): consumer law does not apply — a contract claim to the
    counterparty under the Civil Code, made by the person themselves; a lawsuit only after a lawyer."""
    ctx.container.packs.experimental = False  # production: no beta business scenarios
    api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={"text": B2B, "country": "KZ"})
    case = created["case"]
    assert "consumer" not in case["scenario"]["id"]  # not kz.consumer.refund
    assert case["coverage"]["dispute"]["id"] == "commercial.contract_breach"
    assert case["coverage"]["level"] == "universal"
    # the claim to the counterparty is chosen by the system; the economic court only by «Другой адресат»
    assert case["coverage"]["forum"]["id"] == "kz.counterparty.claim"
    assert {o["id"] for o in case["coverage"]["other_forums"]} == {"kz.court.economic"}
    assert "commercial__contract_breach.business" in case["scenario"]["id"]
    # the same words from a shopper stay a consumer case
    shop = api.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине ТОО Мечта, сломался, продавец не возвращает деньги", "country": "KZ"})
    assert shop["case"]["scenario"]["id"] == "kz.consumer.refund"


def test_business_dispute_prefers_a_business_scenario_when_offered(ctx):
    api = web_user(ctx)  # tests run with EXPERIMENTAL_SCENARIOS=true: the beta business scenarios are offered
    case = api.post("/v1/cases", expect=201, json={
        "text": "Я ИП, поставщик ТОО недопоставил товар по договору поставки, не хватает половины партии",
        "country": "KZ"})["case"]
    assert case["scenario"]["id"].startswith("kz.business.")


def test_owner_review_queue_lists_pending_documents_and_reminds_once(ctx):
    """A held document shows in the owner's queue (/v1/admin/reviews, the command centre in /ops); after 24 h the
    desk is reminded once."""
    from datetime import timedelta

    from konsilier.core.models import utcnow

    ctx.container.engine.config.self_service = False
    api = web_user(ctx)
    cid, _ = _universal_case(api)
    case = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.labor_inspection"})["case"]
    answers = {
        "applicant_name": "Иванов Иван Иванович", "applicant_iin": "пропустить", "applicant_address": "Алматы, ул. Абая 1",
        "applicant_phone": "+7 701 123 45 67", "respondent_name": "ТОО «Ромашка»", "event_date": "пропустить",
        "problem_description": "Не платят зарплату с июня", "desired_outcome": "Выплатить долг по зарплате",
        "amount": "450000", "claim_amount": "пропустить",
    }
    q = case["question"]
    for _ in range(40):  # bounded: a rejected answer repeats the question
        if q is None:
            break
        out = api.answer(cid, "пропустить" if q["type"] == "evidence" else answers[q["field"]])
        assert out["reply"]["error"] is None, out["reply"]
        q = out["case"]["question"]
    assert q is None
    action = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert action["approval_status"] == "pending"

    queue = ctx.client.get("/v1/admin/reviews", headers=ADMIN).json()
    assert [r["action_id"] for r in queue] == [action["id"]]
    assert queue[0]["case_id"] == cid and queue[0]["title"] and queue[0]["waiting_since"]
    assert ctx.client.get("/v1/admin/reviews").status_code in (401, 403)  # owner only

    job = next(j for j in ctx.container.scheduler.extra_jobs if getattr(j, "__name__", "") == "approval_reminders")
    with ctx.container.session_factory() as s:
        assert job(s, utcnow()) == 0  # not 10 minutes yet (owner 01.10: a review takes minutes)
        assert job(s, utcnow() + timedelta(minutes=11)) == 1
        s.commit()
    with ctx.container.session_factory() as s:
        assert job(s, utcnow() + timedelta(minutes=30)) == 0  # once per document

    admin_approve(ctx, action["id"])
    assert ctx.client.get("/v1/admin/reviews", headers=ADMIN).json() == []
