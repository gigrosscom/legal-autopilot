"""Owner 01.10: QA and smoke runs must not mail the team (new lawyer application, document to check, payment to
verify) — dozens of such letters hid the real answers. In /ops such deals are marked «test» and hidden by default."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from konsilier.core.models import Case, User
from konsilier.team import is_test_text, is_test_user

from .test_e2e import Api
from .test_lawyer_onboarding import APP, Outbox
from .test_payment_ways import open_bill, ways

ADMIN = {"X-Admin-Token": "adm"}


def test_what_counts_as_a_test_account():
    assert is_test_user(User(is_test=True)) and is_test_user(User(source="team-test"))
    for name in ("Тест", "Тест Тестов", "test user", "Person 0456", "Пилот Ссылкин", "qa-test+1@konsilier.com"):
        assert is_test_text(name), name
    for name in ("Айгерим Нурланова", "Тестемиров Ержан", "Иванов Иван", "persona@mail.kz", None):
        assert not is_test_text(name), name
    assert not is_test_user(User(display_name="Айгерим", email="aigerim@mail.kz"))


def test_team_test_source_marks_the_account(ctx):
    token = ctx.client.post("/v1/users", json={"language": "ru", "src": "team-test"}).json()["token"]
    with ctx.container.session_factory() as s:
        assert s.scalar(select(User).where(User.api_token == token)).is_test is True


def test_no_letters_for_test_lawyer_applications(ctx):
    outbox = Outbox()
    ctx.container.email_sender = outbox
    qa = Api(ctx, ctx.client.post("/v1/users", json={"language": "ru", "src": "team-test"}).json()["token"])
    qa.post("/v1/lawyer-applications", expect=201, json={**APP, "phone": "+7 701 555 77 01"})
    real = Api(ctx, ctx.client.post("/v1/users", json={"language": "ru"}).json()["token"])
    real.post("/v1/lawyer-applications", expect=201,
              json={**APP, "full_name": "Пилот Ссылкин", "phone": "+7 701 555 77 02", "email": "pilot@mail.kz"})
    assert outbox.sent == []  # neither the test account nor the test name reaches the team
    real.post("/v1/lawyer-applications", expect=201, json={**APP, "phone": "+7 701 555 77 03", "email": "a@mail.kz"})
    assert len(outbox.sent) == 1 and "Айгерим Нурланова" in outbox.sent[0][1]


def test_no_payment_letter_for_a_test_account(ctx):
    outbox = ways(ctx, methods="kaspi_qr")
    api, cid, pay = open_bill(ctx, phone="+7 701 555 77 11")
    with ctx.container.session_factory() as s:
        owner = s.scalar(select(User).join(Case, Case.owner_id == User.id).where(Case.id == uuid.UUID(cid)))
        owner.source = "team-test"
        s.commit()
    before = len(outbox.sent)
    api.post(f"/v1/invoices/{pay['invoice_id']}/way", json={"way": "kaspi_qr"})
    assert api.post(f"/v1/cases/{cid}/payment/claim")["case"]["payment"]["status"] == "awaiting_confirmation"
    assert len(outbox.sent) == before  # «Оплата … проверьте перевод» is not sent


def test_deals_hide_tests_by_default(ctx):
    ways(ctx, methods="kaspi_qr")
    _, real_cid, _ = open_bill(ctx, phone="+7 701 555 77 21")
    _, test_cid, _ = open_bill(ctx, phone="+7 701 555 77 22")
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(test_cid))
        case.facts = {**(case.facts or {}), "applicant_name": "Тест Тестов"}
        s.commit()
    ids = lambda board: {c["id"]: c["test"] for col in board["columns"] for c in col["cards"]}  # noqa: E731
    shown = ids(ctx.client.get("/v1/admin/deals", headers=ADMIN).json())
    assert real_cid in shown and test_cid not in shown and shown[real_cid] is False
    all_ = ids(ctx.client.get("/v1/admin/deals?tests=true", headers=ADMIN).json())
    assert all_[test_cid] is True and all_[real_cid] is False
