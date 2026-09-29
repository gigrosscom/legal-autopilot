"""The lawyer application form: field rules (422 with a code per field), duplicates, spam protection, the desk's
checklist and rejection with a reason, and approval → the lawyer appears in the catalogue instead of the demo."""

from __future__ import annotations

import pytest
from konsilier.identity import form_rules as R

from .test_e2e import web_user
from .test_ops_centre import operator

GOOD = {"country": "KZ", "full_name": "Нурланова Айгерим", "kind": "advocate", "license_number": "12345",
        "city": "Алматы", "phone": "+7 701 555 12 34", "email": "aigerim@mail.kz", "consent": True,
        "specializations": ["consumer"]}


# ------------------------------------------------------------------ rules
@pytest.mark.parametrize("name", ["Нурланова Айгерим", "Ким Ли", "Әбілқасым Құралай Өмірзаққызы",
                                  "Anna-Maria O'Neil", "Сейтқали-Ұлы Ерғали", "  Иванов   Пётр  "])
def test_names_accepted(name):
    assert R.check_full_name(name) is None


@pytest.mark.parametrize("name,code", [("", "required"), ("Айгерим", "name_words"), ("Иванов И", "name_words"),
                                       ("Иванов И.", "name_chars"), ("Иванов 2", "name_chars"),
                                       ("Test123 User", "name_chars"), ("Иванов - Пётр", "name_chars"),
                                       ("А" * 60 + " " + "Б" * 60, "name_length"), ("asdf@ qwer", "name_chars")])
def test_names_rejected(name, code):
    assert R.check_full_name(name) == code


@pytest.mark.parametrize("raw", ["+7 701 555 12 34", "87015551234", "8 (701) 555-12-34", "+7(701)5551234",
                                 "77015551234", "701 555 12 34"])
def test_phone_normalized(raw):
    assert R.normalize_kz_phone(raw) == ("+77015551234", None)


@pytest.mark.parametrize("raw,code", [("", "required"), ("12-34-56", "phone_format"), ("+7 701 555 12", "phone_format"),
                                      ("+7 916 555 12 34", "phone_operator"), ("8 916 555 12 34", "phone_operator"),
                                      ("+998 90 123 45 67", "phone_format"), ("+7 701 555 12 34 5", "phone_format"),
                                      ("tel 87015551234", "phone_format")])
def test_phone_rejected(raw, code):
    assert R.normalize_kz_phone(raw) == (None, code)


def test_email_city_license():
    assert R.check_email("") is None and R.check_email("", required=True) == "required"
    assert R.check_email("a@b.kz") is None
    for bad in ("a@b", "a b@c.kz", "@mail.kz", "name@mail.k"):
        assert R.check_email(bad) == "email_format"
    assert R.check_city("Усть-Каменогорск") is None and R.check_city("Нур-Султан") is None
    assert R.check_city("") == "required" and R.check_city("123") == "city_format"
    assert R.check_license("", "advocate") == "required" and R.check_license("", "legal_consultant") == "required"
    assert R.check_license("", "human_rights") is None
    assert R.check_license("№ 0001234", "advocate") is None and R.check_license("ПЮК-17/2023", "legal_consultant") is None
    for bad in ("абв", "12;DROP", "!!!", "1" * 41):
        assert R.check_license(bad, "advocate") == "license_format"


# ------------------------------------------------------------------ API
def test_api_rejects_with_codes_per_field(ctx):
    r = ctx.client.post("/v1/lawyer-applications", json={"country": "KZ", "full_name": "Айгерим1", "kind": "advocate",
                                                          "phone": "+7 916 000 00 00", "email": "bad@", "city": ""})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "invalid_application"
    assert d["fields"] == {"full_name": "name_chars", "license_number": "required", "city": "required",
                           "phone": "phone_operator", "email": "email_format", "consent": "required"}
    r = ctx.client.post("/v1/lawyer-applications", json={**GOOD, "kind": "other"})
    assert r.status_code == 422 and r.json()["detail"]["fields"] == {"kind": "required"}
    # a human-rights defender has no licence number
    ok = ctx.client.post("/v1/lawyer-applications", json={**GOOD, "kind": "human_rights", "license_number": ""})
    assert ok.status_code == 201


def test_stored_normalized(ctx):
    lawyer = web_user(ctx)
    lawyer.post("/v1/lawyer-applications", expect=201, json={**GOOD, "full_name": "  Нурланова   Айгерим "})
    lw = _desk(ctx)
    row = lw.get("/v1/ops/lawyers/applications").json()[0]
    assert row["full_name"] == "Нурланова Айгерим" and row["phone"] == "+77015551234"
    assert row["checks"]["full_name"] is None and row["checks"]["ecp"] == "missing"
    assert row["registries"] and all(x["url"].startswith("https://") for x in row["registries"])


def test_duplicates_honeypot_and_rate_limit(ctx):
    assert ctx.client.post("/v1/lawyer-applications", json=GOOD).status_code == 201
    dup = ctx.client.post("/v1/lawyer-applications", json={**GOOD, "phone": "8 701 555 12 34", "full_name": "Другой Юрист"})
    assert dup.status_code == 409 and dup.json()["detail"] == {
        "code": "duplicate_application", "message": "duplicate_application", "fields": {"phone": "duplicate"}}
    spam = ctx.client.post("/v1/lawyer-applications", json={**GOOD, "phone": "+77019990000", "website": "http://x"})
    assert spam.status_code == 422 and spam.json()["detail"]["code"] == "spam"
    codes = [ctx.client.post("/v1/lawyer-applications", json={**GOOD, "phone": f"+7701000000{i}"}).status_code
             for i in range(6)]
    assert codes[:4] == [201] * 4 and codes[4:] == [429, 429]  # 5 per hour from one address


def test_rejected_can_apply_again_and_is_told_why(ctx):
    lawyer = web_user(ctx)
    app_id = lawyer.post("/v1/lawyer-applications", expect=201, json=GOOD)["id"]
    lw = _desk(ctx)
    r = ctx.client.post(f"/v1/ops/lawyers/applications/{app_id}", headers=lw.h, json={"status": "rejected"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "reason_required"
    out = lw.post(f"/v1/ops/lawyers/applications/{app_id}",
                  json={"status": "rejected", "reason": "Номер лицензии не найден в реестре"})
    assert out["status"] == "rejected"
    assert ctx.container.email_sender.sent[-1][0] == "aigerim@mail.kz"
    assert "Номер лицензии не найден" in ctx.container.email_sender.sent[-1][2]
    me = lawyer.get("/v1/lawyer/me").json()
    assert me["applications"][0]["reject_reason"] == "Номер лицензии не найден в реестре"
    lawyer.post("/v1/lawyer-applications", expect=201, json={**GOOD, "license_number": "54321"})


def test_ecp_on_another_device_ties_by_phone(ctx):
    """Applied from the phone without ЭЦП; signed with ЭЦП on the computer and sent the form again, same number."""
    from .test_lawyer_agreements import LAWYER_IIN, Verifier, ecp_login

    ctx.container.signature_verifier = Verifier()
    phone_user = web_user(ctx)
    app_id = phone_user.post("/v1/lawyer-applications", expect=201, json=GOOD)["id"]
    desktop = web_user(ctx)
    ecp_login(ctx, desktop, LAWYER_IIN)
    r = ctx.client.post("/v1/lawyer-applications", headers=desktop.h, json=GOOD)
    assert r.status_code == 200 and r.json()["id"] == app_id and r.json()["linked"] is True
    assert desktop.get("/v1/lawyer/me").json()["applications"][0]["id"] == app_id
    # now a second application from the same ЭЦП is a duplicate
    r = ctx.client.post("/v1/lawyer-applications", headers=desktop.h, json={**GOOD, "phone": "+77470000000"})
    assert r.status_code == 409 and r.json()["detail"]["fields"] == {"ecp": "duplicate"}


def test_approval_puts_lawyer_in_catalogue_instead_of_demo(ctx):
    from .test_lawyer_agreements import LAWYER_IIN, Verifier, ecp_login

    demo = ctx.client.get("/v1/lawyers?country=KZ").json()
    assert demo["demo"] is True and demo["lawyers"]
    # demo people are never shown as verified
    assert all(not x["verified"]["license"] and not x["verified"]["identity"] and x["demo"] for x in demo["lawyers"])

    ctx.container.signature_verifier = Verifier()
    lawyer = web_user(ctx)
    ecp_login(ctx, lawyer, LAWYER_IIN)
    app_id = lawyer.post("/v1/lawyer-applications", expect=201, json=GOOD)["id"]
    lw = _desk(ctx)
    assert ctx.client.get("/v1/lawyers?country=KZ").json()["demo"] is True  # not yet approved
    lw.post(f"/v1/ops/lawyers/applications/{app_id}", json={"status": "verified"})

    cat = ctx.client.get("/v1/lawyers?country=KZ").json()
    assert cat["demo"] is False and len(cat["lawyers"]) == 1
    p = cat["lawyers"][0]
    assert p["id"] == f"lawyer-{app_id}" and p["name"] == "Нурланова Айгерим" and p["demo"] is False
    assert p["verified"] == {"license": True, "identity": True, "registry": ""} and p["score"] is None
    assert p["specializations"][0]["key"] == "consumer" and p["city"] == "Алматы"
    # the cabinet opens
    assert lawyer.get("/v1/lawyer/me").json()["verified"] is True
    assert ctx.client.get("/v1/lawyer/cases", headers=lawyer.h).status_code == 200
    # the phone never leaves the desk
    assert "+7701" not in str(cat)


def test_client_request_uses_the_same_rules(ctx):
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "Работодатель не выплатил зарплату", "country": "KZ"})["case"]["id"]
    r = ctx.client.post(f"/v1/cases/{cid}/lawyer-request", headers=api.h,
                        json={"full_name": "Асем", "phone": "+7 916 123 45 67", "email": "x@", "consent": False})
    assert r.status_code == 422 and r.json()["detail"]["fields"] == {
        "full_name": "name_words", "phone": "phone_operator", "email": "email_format", "consent": "required"}


# ------------------------------------------------------------------ helpers
class _Outbox:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, text):
        self.sent.append((to, subject, text))


def _desk(ctx):
    ctx.container.settings.ops_lawyers_emails = "lawyers@konsilier.com"
    if not isinstance(ctx.container.email_sender, _Outbox):
        ctx.container.email_sender = _Outbox()
    return operator(ctx, "lawyers@konsilier.com")


@pytest.fixture(autouse=True)
def _outbox(ctx):
    ctx.container.email_sender = _Outbox()



def test_application_from_the_old_form_is_found_by_its_contact(ctx):
    """The first applications came through the old form (a free-text contact, no phone field)."""
    from konsilier.core.models import LawyerApplication

    from .test_lawyer_agreements import LAWYER_IIN, Verifier, ecp_login

    with ctx.container.session_factory() as s:
        old = LawyerApplication(country="KZ", full_name="Нурланова Айгерим", kind="advocate", contact="8 701 555 12 34",
                                referral_code="OLD0001")
        s.add(old)
        s.commit()
        old_id = old.id
    ctx.container.signature_verifier = Verifier()
    lawyer = web_user(ctx)
    ecp_login(ctx, lawyer, LAWYER_IIN)
    r = ctx.client.post("/v1/lawyer-applications", headers=lawyer.h, json=GOOD)
    assert r.status_code == 200 and r.json() == {**r.json(), "id": old_id, "linked": True}
    row = _desk(ctx).get("/v1/ops/lawyers/applications").json()[0]
    assert row["ecp_verified"] is True and row["license_number"] == "12345"  # filled from the new form
    assert row["checks"]["license_number"] is None and row["city"] == "Алматы"
