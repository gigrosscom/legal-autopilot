"""Emergency detection, false-report acknowledgement, abuse holds (ADR 0001 §7)."""

from __future__ import annotations

import uuid

from konsilier.core import safety
from konsilier.core.models import Case, User

from .test_e2e import ADMIN, web_user


def test_triage_shows_emergency_numbers_before_intake(ctx):
    r = ctx.client.post("/v1/triage", json={"text": "Муж угрожает убить меня", "country": "KZ", "language": "ru"})
    body = r.json()
    assert body["emergency"] is True
    assert "112" in [n["number"] for n in body["numbers"]]
    calm = ctx.client.post("/v1/triage", json={"text": "Не вернули деньги за товар", "country": "KZ"}).json()
    assert calm == {"emergency": False, "message": "", "numbers": []}
    assert ctx.client.get("/v1/emergency?country=KZ&lang=kk").json()["numbers"][0]["label"]


def test_case_creation_carries_emergency_screen(ctx):
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": "Сосед избивает меня и угрожает убить", "country": "KZ"})
    assert out["reply"]["emergency"]["numbers"]


def test_crime_report_requires_false_report_acknowledgement(ctx):
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": "У меня украли телефон, кража в автобусе", "country": "KZ"})
    case = out["case"]
    assert case["coverage"]["level"] == "universal"
    assert case["coverage"]["forum"]["id"] == "kz.police"  # the only candidate is chosen automatically
    assert out["reply"]["ack_required"] == "false_report"
    assert "ложный донос" in out["reply"]["message"]
    assert case["safety"]["pending_ack"] == "false_report"
    # nothing moves until the user confirms
    again = api.answer(case["id"], "Иванов Иван")
    assert again["reply"]["ack_required"] == "false_report"
    assert again["case"]["facts"] == [] or all(f["field"] != "applicant_name" for f in again["case"]["facts"])
    api.post(f"/v1/cases/{case['id']}/acknowledge", expect=409, json={"kind": "special_category"})
    done = api.post(f"/v1/cases/{case['id']}/acknowledge", json={"kind": "false_report"})
    assert done["reply"]["ack_required"] is None
    assert done["reply"]["question"]["field"] == "respondent_name"  # the story first, personal data last
    assert done["case"]["safety"]["pending_ack"] is None


def test_abuse_flag_puts_case_on_hold_until_admin_releases(ctx):
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={
        "text": "Сосед занял деньги и не возвращает долг, хочу затравить его, буду жаловаться каждый день",
        "country": "KZ"})
    case = out["case"]
    assert case["safety"]["hold_reason"] == "abuse_suspected"
    cid = case["id"]
    if case["coverage"]["options"]:
        api.post(f"/v1/cases/{cid}/forum", json={"forum_id": case["coverage"]["options"][0]["id"]})
    r = api.c.post(f"/v1/cases/{cid}/actions/next", headers=api.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "on_hold"
    held = ctx.client.get("/v1/admin/cases?on_hold=true", headers=ADMIN).json()
    assert [c["id"] for c in held] == [cid]
    released = ctx.client.post(f"/v1/admin/cases/{cid}/release", headers=ADMIN).json()
    assert released["safety"]["hold_reason"] is None


def test_repeated_cases_against_one_private_person_are_detected(ctx):
    pack = ctx.container.packs.pack("KZ")
    with ctx.container.session_factory() as s:
        user = User()
        s.add(user)
        s.flush()
        cases = []
        for _ in range(5):
            c = Case(owner_id=user.id, language="ru", jurisdiction="KZ", facts={"respondent_name": "Петров П. П."},
                     taxonomy={"dispute_id": "civil.debt", "role": "claimant", "flags": []})
            c.id = uuid.uuid4()
            s.add(c)
            cases.append(c)
        s.flush()
        assert safety.abuse_reason(s, pack.coverage, cases[-1]) == "repeated_against_person"
        # a business counterparty is not a private person: no hold for repeated consumer complaints
        cases[-1].taxonomy = {"dispute_id": "consumer.refund", "role": "consumer", "flags": []}
        assert safety.abuse_reason(s, pack.coverage, cases[-1]) is None


def test_crime_report_asks_for_facts_instead_of_labels_once(ctx):
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": "Этот вор украл телефон, кража в автобусе", "country": "KZ"})
    cid = out["case"]["id"]
    ack = api.post(f"/v1/cases/{cid}/acknowledge", json={"kind": "false_report"})
    # the label in the first story is caught right after the acknowledgement
    assert ack["reply"]["error"] == "facts_not_labels"
    assert ack["reply"]["question"]["field"] == "problem_description"
    assert api.answer(cid, "Вечером в автобусе №12 из моего кармана вытащили телефон")["reply"]["error"] is None


def test_labels_warning_is_given_only_once(ctx):
    api = web_user(ctx)
    out = api.post("/v1/cases", expect=201, json={"text": "У меня украли телефон, кража в автобусе", "country": "KZ"})
    cid = out["case"]["id"]
    api.post(f"/v1/cases/{cid}/acknowledge", json={"kind": "false_report"})
    answers = {"applicant_name": "Иванов Иван", "applicant_iin": "пропустить", "applicant_address": "Алматы",
               "applicant_phone": "+7 701 123 45 67", "respondent_name": "неизвестный", "event_date": "пропустить"}
    q = api.get(f"/v1/cases/{cid}").json()["question"]
    while q and q["field"] in answers:
        q = api.answer(cid, answers[q["field"]])["case"]["question"]
    assert q["field"] == "desired_outcome"  # the story was already taken from the first message
    first = api.answer(cid, "Наказать этого вора")
    assert first["reply"]["error"] == "facts_not_labels"
    second = api.answer(cid, "Наказать этого вора")  # asked once only, then accepted
    assert second["reply"]["error"] is None
