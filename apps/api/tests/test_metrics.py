"""Investor metrics are counted from real records: funnel, outcomes, money, weekly series, CSV."""

from tests.test_e2e import ADMIN, test_credit_fraud_via_telegram_full_path, web_user


def test_metrics_follow_a_real_case_to_the_end(ctx):
    web_user(ctx).post("/v1/cases", expect=201, json={"text": "Сосед шумит по ночам", "country": "KZ"})  # not classified
    test_credit_fraud_via_telegram_full_path(ctx)  # classified → documents → submitted → response → won 300 000
    m = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()
    funnel = {r["step"]: r["cases"] for r in m["funnel"]}
    assert funnel["created"] == 2 and funnel["classified"] == 1
    assert funnel["document_ready"] == funnel["submitted"] == funnel["response"] == funnel["resolved_positive"] == 1
    assert m["outcomes"] == {"won": 1}
    assert m["money"]["recovered"] == {"KZT": "300000.00"}
    assert m["totals"]["cases"] == 2 and m["totals"]["users"] >= 2
    assert sum(w["cases"] for w in m["weekly"]) == 2 and len(m["weekly"]) == 12
    csv = ctx.client.get("/v1/admin/metrics.csv", headers=ADMIN)
    assert csv.status_code == 200 and csv.text.startswith("week,new_users,new_cases")
    assert ctx.client.get("/v1/admin/metrics").status_code in (401, 403)  # admin only
