"""Case roadmap: statuses and dates follow the scenario and real case events."""

from datetime import date, timedelta

from .test_e2e import Api, admin_approve, run_intake, web_user

ANSWERS = {"seller_name": "ТОО «Техномир»", "seller_bin": "пропустить", "goods_description": "Смартфон",
           "applicant_name": "Иванов Иван", "applicant_phone": "+7 701 000 00 00", "applicant_iin": "пропустить",
           "seller_email": "пропустить", "seller_address": "Алматы, пр. Абая 10",
           "applicant_address": "Алматы, ул. Абая 1"}


def steps(case):
    return {s["key"]: s for s in case["roadmap"]["steps"]}


def new_refund_case(ctx) -> tuple[Api, str]:
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={
        "text": "Купил смартфон в интернет-магазине 01.09.2026 за 90000, сломался, хочу вернуть деньги",
        "country": "KZ"})["case"]["id"]
    return api, cid


def test_roadmap_during_intake_projects_full_path(ctx):
    api, cid = new_refund_case(ctx)
    case = api.get(f"/v1/cases/{cid}").json()
    s = steps(case)
    assert [x["key"] for x in case["roadmap"]["steps"]] == [
        "intake", "claim_to_seller", "complaint_consumer_authority", "handoff_lawyer", "resolution"]
    assert s["intake"]["status"] == "current"
    assert s["claim_to_seller"]["status"] == "upcoming" and not s["claim_to_seller"]["conditional"]
    assert s["complaint_consumer_authority"]["conditional"] is True
    rm = case["roadmap"]
    assert rm["best_case_on"] <= rm["worst_case_on"]  # the authority has no fixed term (lawyer, 01.10)
    assert rm["open_ended_after_worst"] is True  # a lawyer step without a fixed deadline follows


def test_roadmap_follows_real_events(ctx):
    ctx.container.engine.config.self_service = False  # the lawyer-review policy (SELF_SERVICE=false)
    api, cid = new_refund_case(ctx)
    run_intake(api, cid, {**ANSWERS, "evidence": "пропустить", "identity_document": "пропустить"})
    a1 = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    case = api.get(f"/v1/cases/{cid}").json()
    assert steps(case)["intake"]["status"] == "done"
    assert steps(case)["claim_to_seller"]["status"] == "current"
    assert "проверку юристом" in steps(case)["claim_to_seller"]["detail"]

    admin_approve(ctx, a1["id"])
    sub = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/submitted", json={})
    s = steps(sub["case"])
    due = sub["case"]["actions"][0]["deadline"]["due_date"]
    assert s["claim_to_seller"]["due_on"] == due  # the real registered deadline
    assert sub["case"]["roadmap"]["best_case_on"] == due
    # the authority's response term is not in the law (lawyer, 01.10): no invented date
    assert s["complaint_consumer_authority"]["estimated_on"] in (None, due)

    out = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/response", json={"response_class": "full"})
    s = steps(out["case"])
    assert s["claim_to_seller"]["status"] == "done" and "полностью" in s["claim_to_seller"]["detail"]
    assert s["complaint_consumer_authority"]["status"] == "skipped"
    assert s["handoff_lawyer"]["status"] == "skipped"  # depends on a step that will never happen

    closed = api.post(f"/v1/cases/{cid}/close", json={"result": "won", "amount_recovered": "90000"})
    s = steps(closed["case"])
    assert s["resolution"]["status"] == "done" and s["resolution"]["detail"] == "Требования удовлетворены"
