"""A third scenario (and even a new country) is added as DATA only.

``tests/fixtures/packs/xx`` contains a pack manifest, one scenario YAML and a
DOCX template. Nothing in ``konsilier/`` knows about it — yet the whole case
lifecycle works: intake → document → deadline in business days → response →
escalation to an authority → hand-off → close.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from konsilier.core.documents import docx_text

from .test_e2e import Api, statuses, tick_at, web_user

CORE = Path(__file__).resolve().parents[1] / "konsilier"


def test_dummy_scenario_full_lifecycle(ctx):
    ctx.container.engine.config.approval_required_first_n = 0
    api: Api = web_user(ctx)
    created = api.post("/v1/cases", expect=201, json={
        "text": "My dummy widget was never delivered", "country": "XX", "language": "en"})
    case = created["case"]
    cid = case["id"]
    assert case["scenario"]["id"] == "xx.test.dummy"
    assert case["scenario"]["draft"] is False  # reviewed_at is set → no DRAFT disclaimer
    assert case["currency"] == "TST"
    assert created["reply"]["question"] == {"field": "counterparty", "text": "Who owes you?", "type": "text",
                                            "optional": False, "evidence_kinds": []}
    api.answer(cid, "Widget Corp")
    out = api.answer(cid, "1200")
    assert out["reply"]["intake_complete"] is True  # story was pre-filled from the first message

    a1 = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]
    assert a1["status"] == "ready" and a1["instructions"] == ["Send it to Widget Corp."]
    text = docx_text(api.get(f"/v1/cases/{cid}/actions/{a1['id']}/document?format=docx").content)
    assert "To: Widget Corp" in text and "I demand: pay 1 200 TST" in text
    assert "Basis: Test Code s.1" in text and "Prepared with AI" in text and "DRAFT" not in text

    sub = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/submitted", json={})
    due = date.fromisoformat(sub["case"]["actions"][0]["deadline"]["due_date"])
    assert due.weekday() < 5  # business days
    assert tick_at(ctx, due - timedelta(days=1)) == 1  # pack-level reminder_before_days: [1]

    r = api.post(f"/v1/cases/{cid}/actions/{a1['id']}/response", json={"text": "They paid some of it"})
    assert r["proposal"]["action_id"] == "ombudsman"  # 'or ... == partial' branch of the condition
    a2 = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][1]
    assert a2["addressee"]["name"] == "Testland Ombudsman"
    api.post(f"/v1/cases/{cid}/actions/{a2['id']}/submitted", json={})
    r = api.post(f"/v1/cases/{cid}/actions/{a2['id']}/response", json={"text": "We refuse"})
    assert r["proposal"]["type"] == "handoff"
    api.post(f"/v1/cases/{cid}/actions/next")
    closed = ctx.client.post(f"/v1/admin/cases/{cid}/close", headers={"X-Admin-Token": "adm"},
                             json={"result": "lost"}).json()
    assert closed["outcome"]["resolved_at_step"] == "lawyer"
    assert statuses(ctx, cid)[-3:] == ["escalated", "handed_to_lawyer", "resolved"]


def test_core_has_no_country_specific_code():
    """Guard: the global core must not branch on (or mention) particular countries."""
    forbidden = re.compile(r"""(['"](KZ|kz|KZT|XX)['"]|\bKZT\b|Kazakh|Казахстан|eotinish|АРРФР|\bИИН\b|\bБИН\b)""")
    offenders = []
    for path in CORE.rglob("*.py"):
        for n, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            if forbidden.search(line):
                offenders.append(f"{path.relative_to(CORE)}:{n}: {line.strip()}")
    assert offenders == []
