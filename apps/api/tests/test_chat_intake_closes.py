"""BUG-26 (PM 03.10, P0): no document was made in any case — the chat never runs the interview, and since decision 226
(no question cap) nothing else closed it: the case stayed in «intake» and «Подготовить документ» answered 409
(intake_incomplete, or no_document_path when the recipient was never picked). The interview ends when the person asks
for the document: the scenario and the recipient are worked out from what they told, the unknown stays a blank, the
applicant's data are asked in the form — and the document is made."""

from __future__ import annotations

import uuid

from konsilier.core.models import Case

from .test_chat_flood_dialog import FIRST, SOLUTION, _flood
from .test_chat_paid_document import _say

VALUES = {"applicant_name": "Иванов Иван Иванович", "applicant_address": "г. Алматы, ул. Абая, 10, кв. 5",
          "respondent_name": "Петров Пётр Петрович", "respondent_address": "г. Алматы, ул. Абая, 10, кв. 9"}


def _value(field: dict) -> str:
    n, t = field["field"], field["type"]
    if n in VALUES:
        return VALUES[n]
    return {"date": "25.09.2026", "money": "450000", "phone": "+7 701 123 45 67"}.get(t) or (
        "г. Алматы, ул. Абая, 10" if n.endswith("address") else "880101300123" if n.endswith("iin")
        else "Петров Пётр Петрович")


def _document(ctx, api, cid):
    r = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert r.status_code in (200, 422), r.json()  # never 409: the interview is closed by the request itself
    if r.status_code == 422:
        assert r.json()["detail"]["code"] == "applicant_data_required"
        fields = r.json()["detail"]["fields"]
        out = api.c.post(f"/v1/cases/{cid}/facts", headers=api.h,
                         json={"values": {f["field"]: _value(f) for f in fields}})
        assert out.status_code == 200, out.json()
        r = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert r.status_code == 200, r.json()
    return r.json()


def test_chat_interview_to_a_document(ctx):
    api, cid = _flood(ctx, "Когда это случилось?", SOLUTION, SOLUTION)
    _say(ctx, api, cid, FIRST)
    _say(ctx, api, cid, "Сосед сверху, 25.09.2026, у него лопнула труба.")
    _say(ctx, api, cid, "Ущерб 450 000 тенге, документов больше нет")
    out = _document(ctx, api, cid)
    assert out["action_id"], out
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        assert c.actions and c.actions[-1].docx_key
        assert c.status != "intake"


def test_a_case_waiting_for_the_recipient_gets_one(ctx):
    """no_document_path: a universal case whose recipient was never picked — the first lawful one is taken."""
    api, cid = _flood(ctx, SOLUTION)
    engine = ctx.container.engine
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        options = engine.forum_options(c) if c.scenario_id is None else None
        if c.scenario_id:  # as on prod: dispute known, recipient not chosen yet
            c.scenario_id = c.scenario_version = c.forum_id = None
            c.status = "intake"
            s.commit()
            options = engine.forum_options(c)
        assert options, "the dispute offers recipients"
    out = _document(ctx, api, cid)
    assert out["action_id"], out
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).scenario_id


def test_no_more_documents_in_the_chat_ends_the_interview(ctx):
    """PM 03.10: «документов больше нет» after the facts — the case is qualified in the chat itself."""
    api, cid = _flood(ctx, "Когда это случилось?", SOLUTION, SOLUTION)
    _say(ctx, api, cid, FIRST)
    _say(ctx, api, cid, "Сосед сверху, 25.09.2026, у него лопнула труба.")
    _say(ctx, api, cid, "Ущерб 450 000 тенге, документов больше нет")
    with ctx.container.session_factory() as s:
        c = s.get(Case, uuid.UUID(cid))
        assert c.status == "qualified", c.status


def test_facts_still_missing_keep_the_interview_open(ctx):
    api, cid = _flood(ctx, "Когда это случилось?")
    _say(ctx, api, cid, "Достаточно")  # no date, no sum, nothing asked yet: the chat asks first
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).status == "intake"
