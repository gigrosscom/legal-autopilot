"""Owner 02.10: the client does not choose where to file. The pack's rule (routing.forum_order) takes the step's
recipient — the other party's pre-trial claim first, else the body or court by competence; the person sees
«Кому: … — почему» and may switch only by «Другой адресат» until the document is made."""

from __future__ import annotations

import uuid

from konsilier.core import qualifier
from konsilier.core.models import Case

from .conftest import hide_scenarios
from .test_coverage_levels import WAGES, _fill_and_prepare
from .test_e2e import web_user


def test_every_dispute_gets_a_recipient_and_a_reason(ctx):
    cov = ctx.container.packs.pack("KZ").coverage
    for d in cov.disputes.values():
        for role in d.applicant_roles:
            forums = cov.candidate_forums(d, role)
            if not forums or cov.is_lawyer_only(d, role):
                continue
            picked = cov.auto_forum(forums, d.id)
            assert picked is not None, (d.id, role)
            assert picked.id not in ("kz.mediation", "kz.court.pending", "kz.police.case"), (d.id, role)
            assert picked.id in cov.routing.forum_why or len(forums) == 1 or cov.route_step(d.id, picked.id), \
                (d.id, role, picked.id)
    assert all(f in cov.forums for f in cov.routing.forum_order)  # no typo in the pack's order


def test_alimony_goes_to_the_juvenile_court(ctx):
    cov = ctx.container.packs.pack("KZ").coverage
    d = cov.dispute("family.alimony")
    assert cov.auto_forum(cov.candidate_forums(d, "parent")).id == "kz.court.juvenile"


def test_the_recipient_can_be_changed_until_the_document_is_made(ctx):
    hide_scenarios(ctx, "kz.labor.")
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": WAGES, "country": "KZ"})["case"]
    cid = case["id"]
    assert case["coverage"]["forum"]["id"] == "kz.counterparty.claim"
    case = api.post(f"/v1/cases/{cid}/forum", json={"forum_id": "kz.labor_inspection"})["case"]
    assert case["coverage"]["forum"]["id"] == "kz.labor_inspection"
    assert "kz.counterparty.claim" in {o["id"] for o in case["coverage"]["other_forums"]}  # and back
    _fill_and_prepare(api, cid, case)
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["coverage"]["other_forums"] == []  # the document exists: no switching under it
    api.post(f"/v1/cases/{cid}/forum", expect=409, json={"forum_id": "kz.counterparty.claim"})


def test_a_case_left_at_the_old_list_gets_its_recipient_when_opened(ctx):
    hide_scenarios(ctx, "kz.labor.")
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": WAGES, "country": "KZ"})["case"]["id"]
    with ctx.container.session_factory() as s:  # as it was before 02.10: universal, no forum, no scenario
        c = s.get(Case, uuid.UUID(cid))
        c.scenario_id = c.scenario_version = c.forum_id = c.pending_field = None
        assert c.coverage_level == qualifier.LEVEL_UNIVERSAL
        s.commit()
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["coverage"]["forum"]["id"] == "kz.counterparty.claim" and case["scenario"] is not None
    assert case["coverage"]["options"] == []


def test_the_reason_in_kazakh(ctx):
    hide_scenarios(ctx, "kz.labor.")
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={"text": WAGES, "country": "KZ", "language": "kk"})["case"]
    # labour: the dispute's own route (routes.yaml) gives the reason — the conciliation commission comes first
    assert case["coverage"]["forum"]["why"].startswith("Ұйымда келісім комиссиясы болса")


def test_a_case_already_at_the_draft_can_switch_too(ctx):
    ctx.container.packs.experimental = False  # production: the universal path for a business contract
    api = web_user(ctx)
    case = api.post("/v1/cases", expect=201, json={
        "text": "я ип заключил договор с тоо на поставку, они не выполнили условия договора, хотим вернуть деньги",
        "country": "KZ"})["case"]
    assert case["coverage"]["forum"]["id"] == "kz.counterparty.claim"
    case = api.post(f"/v1/cases/{case['id']}/forum", json={"forum_id": "kz.court.economic"})["case"]
    assert case["coverage"]["forum"]["id"] == "kz.court.economic" and case["scenario"]["id"].endswith("kz__court__economic")
    assert case["status"] in ("intake", "qualified")
