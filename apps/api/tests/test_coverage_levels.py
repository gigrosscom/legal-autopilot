"""End-to-end over the three coverage levels (ADR 0001) with the mocked LLM."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from konsilier.core.documents import docx_text
from konsilier.core.models import Action, DemandSignal

from .test_e2e import ADMIN, admin_approve, statuses, web_user

WAGES = "Работодатель не платит зарплату три месяца, задолженность 450000 тенге"


def _universal_case(api):
    created = api.post("/v1/cases", expect=201, json={"text": WAGES, "country": "KZ"})
    case = created["case"]
    assert case["scenario"] is None
    assert case["coverage"]["level"] == "universal"
    assert case["coverage"]["dispute"]["id"] == "labor.unpaid_wages"
    options = {o["id"]: o for o in created["reply"]["options"]}
    assert "kz.labor_inspection" in options and "kz.court.district" in options
    assert all(not o["verified"] for o in options.values())  # nothing in the KZ registry is signed off yet
    assert case["coverage"]["options"] == created["reply"]["options"]
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

    # a message before choosing a forum only repeats the choice
    out = api.answer(cid, "что дальше?")
    assert out["reply"]["options"]
    api.post(f"/v1/cases/{cid}/forum", expect=409, json={"forum_id": "kz.police"})  # not a candidate

    out = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.labor_inspection"})
    case = out["case"]
    assert case["scenario"]["id"].startswith("kz.generic.labor__unpaid_wages.employee.")
    assert case["scenario"]["draft"] is True  # universal documents always carry the DRAFT mark
    assert case["coverage"]["forum"]["id"] == "kz.labor_inspection"
    assert case["coverage"]["upl_notice"]

    answers = {
        "applicant_name": "Иванов Иван Иванович", "applicant_iin": "пропустить", "applicant_address": "Алматы, ул. Абая 1",
        "applicant_phone": "+7 701 123 45 67", "respondent_name": "ТОО «Ромашка»", "event_date": "пропустить",
        "problem_description": "Не платят зарплату с июня", "desired_outcome": "Выплатить долг по зарплате",
        "amount": "450000",
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
    assert "[норма: уточнит юрист]" in text
    assert "Выплатить долг по зарплате" in text
    assert "ЧЕРНОВИК" in text

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
    created = api.post("/v1/cases", expect=201, json={"text": "Бывший муж не платит алименты", "country": "KZ"})
    assert created["case"]["coverage"]["level"] == "lawyer"
    assert "children" in [r["code"] for r in created["case"]["coverage"]["reasons"]]


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
    assert kz["cells"]["labor"] == "universal"
    assert kz["cells"]["commercial"] == "lawyer"
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
    "amount": "450000",
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
    assert any("Местный орган по инспекции труда" in s for s in steps)  # the chosen body is named
    assert any(s.startswith("Что приложить:") for s in steps)
    assert steps[-1].startswith("После подачи нажмите")


def test_pre_trial_claim_goes_to_the_other_party(ctx):
    api = web_user(ctx)
    cid, options = _universal_case(api)
    assert "kz.counterparty.claim" in options  # a pre-trial claim is offered next to the bodies
    case = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.counterparty.claim"})["case"]
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
