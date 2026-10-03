"""Notifications: the site's bell (read / unread), e-mail and SMS for key events, quiet hours, failures."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from konsilier.core.models import Action, Case, Deadline, Identity, Notification, User

from .test_e2e import Api, web_user
from .test_lawyer_onboarding import Outbox

DAY = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)  # 11:00 in Almaty
NIGHT = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)  # 23:00 in Almaty


class Broken:
    def send(self, to: str, subject: str, text: str) -> None:
        raise RuntimeError("gateway down")


def new_case(api: Api) -> str:
    return api.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине за 150000 тенге, через неделю сломался, деньги не возвращают",
        "country": "KZ"})["case"]["id"]


def owner_of(s, cid: str) -> User:
    return s.get(User, s.get(Case, uuid.UUID(cid)).owner_id)


def verify(ctx, cid: str, *, email: str | None = None, phone: str | None = None) -> None:
    """Gives the case owner verified contacts, as signing in with a code does."""
    with ctx.container.session_factory() as s:
        user = owner_of(s, cid)
        for kind, value in (("email", email), ("phone", phone)):
            if value:
                setattr(user, kind, value)
                s.add(Identity(user_id=user.id, kind=kind, subject_hash=uuid.uuid4().hex, display=value[-4:]))
        s.commit()


def notify(ctx, cid: str, kind: str, text: str, sms: str | None = None) -> Notification:
    with ctx.container.session_factory() as s:
        n = ctx.container.notifier.notify(s, s.get(Case, uuid.UUID(cid)), kind, text, sms=sms)
        s.commit()
        s.refresh(n)
        s.expunge(n)
        return n


@pytest.fixture
def setup(ctx):
    """A web user with a KZ case, fake e-mail and SMS senders and a daytime clock."""
    ctx.container.email_sender, ctx.container.sms_sender = Outbox(), Outbox()
    ctx.container.notifier.clock = lambda: DAY
    api = web_user(ctx)
    return ctx, api, new_case(api)


def test_bell_lists_newest_first_and_marks_read(setup):
    ctx, api, cid = setup
    other = web_user(ctx)
    foreign = notify(ctx, new_case(other), "handoff", "чужое")
    for i in range(3):
        notify(ctx, cid, "approval", f"сообщение {i}")

    inbox = api.get("/v1/notifications").json()
    assert inbox["unread"] == 3
    assert [n["text"] for n in inbox["items"]] == ["сообщение 2", "сообщение 1", "сообщение 0"]
    assert inbox["items"][0]["case_id"] == cid and inbox["items"][0]["read_at"] is None

    first = inbox["items"][-1]["id"]
    # someone else's notification is never touched
    assert api.post("/v1/notifications/read", json={"ids": [first, foreign.id]}) == {"unread": 2}
    unread = api.get("/v1/notifications?unread=1").json()
    assert [n["text"] for n in unread["items"]] == ["сообщение 2", "сообщение 1"] and unread["unread"] == 2
    assert other.get("/v1/notifications").json()["unread"] == 1

    assert api.post("/v1/notifications/read", json={"all": True}) == {"unread": 0}
    assert api.get("/v1/notifications?unread=1").json() == {"items": [], "unread": 0}
    assert all(n["read_at"] for n in api.get("/v1/notifications").json()["items"])
    assert api.post("/v1/notifications/read", json={}) == {"unread": 0}  # nothing asked, nothing changed


def test_inbox_only_without_verified_contacts(setup):
    ctx, api, cid = setup
    n = notify(ctx, cid, "document", "Документ готов", sms="document_ready")
    assert n.sent_via == "web" and n.error is None
    assert ctx.container.email_sender.sent == [] and ctx.container.sms_sender.sent == []


def test_email_for_key_kinds_and_sms_only_for_critical(setup):
    ctx, api, cid = setup
    verify(ctx, cid, email="client@mail.kz", phone="+77011234567")
    mail, sms = ctx.container.email_sender, ctx.container.sms_sender

    n = notify(ctx, cid, "document", "Документ готов — скачайте его в карточке дела.", sms="document_ready")
    assert n.sent_via == "web,email,sms"
    to, subject, body = mail.sent[-1]
    assert to == "client@mail.kz" and subject == "Konsilier AI: документ готов"
    assert "Документ готов" in body and f"/case/{cid}" in body and "/account" in body
    to, _, text = sms.sent[-1]
    assert to == "+77011234567" and "документ готов" in text and text.endswith(f"/case/{cid}")

    # a reminder days before the deadline: e-mail, no SMS
    n = notify(ctx, cid, "deadline_reminder", "Напоминание: осталось 2 дн.")
    assert n.sent_via == "web,email" and len(sms.sent) == 1
    # kinds outside the list stay in the inbox (case reports mail themselves)
    n = notify(ctx, cid, "report_update", "отчёт")
    assert n.sent_via == "web" and len(mail.sent) == 2

    # e-mail switched off: SMS still goes for a critical event
    with ctx.container.session_factory() as s:
        owner_of(s, cid).notify_email = False
        s.commit()
    n = notify(ctx, cid, "payment", "Оплата получена.", sms="payment_confirmed")
    assert n.sent_via == "web,sms" and len(mail.sent) == 2 and "оплата получена" in sms.sent[-1][2]


def test_unverified_contacts_get_nothing(setup):
    ctx, api, cid = setup
    with ctx.container.session_factory() as s:  # typed in a form, never confirmed with a code
        user = owner_of(s, cid)
        user.email, user.phone = "client@mail.kz", "+77011234567"
        s.commit()
    assert notify(ctx, cid, "document", "Документ готов", sms="document_ready").sent_via == "web"


def test_no_sms_at_night(setup):
    ctx, api, cid = setup
    verify(ctx, cid, email="client@mail.kz", phone="+77011234567")
    ctx.container.notifier.clock = lambda: NIGHT
    n = notify(ctx, cid, "document", "Документ готов", sms="document_ready")
    assert n.sent_via == "web,email" and ctx.container.sms_sender.sent == []
    ctx.container.notifier.clock = lambda: NIGHT + timedelta(hours=9)  # 08:00 local
    assert notify(ctx, cid, "document", "Документ готов", sms="document_ready").sent_via == "web,email,sms"


def test_failures_are_recorded_not_raised(setup):
    ctx, api, cid = setup
    verify(ctx, cid, email="client@mail.kz", phone="+77011234567")
    ctx.container.email_sender = Broken()
    n = notify(ctx, cid, "document", "Документ готов", sms="document_ready")
    assert n.sent_via == "web,sms" and "email: gateway down" in n.error

    ctx.container.email_sender, ctx.container.sms_sender = Outbox(), Broken()
    n = notify(ctx, cid, "payment", "Оплата получена.", sms="payment_confirmed")
    assert n.sent_via == "web,email" and "sms: gateway down" in n.error
    assert api.get("/v1/notifications").json()["unread"] == 2


def _awaiting(ctx, cid: str, due: date) -> None:
    """The case waits for an answer to a sent claim, due on `due`."""
    with ctx.container.session_factory() as s:
        case = s.get(Case, uuid.UUID(cid))
        case.scenario_id, case.status = "kz.consumer.refund", "awaiting_response"
        action = Action(case_id=case.id, sequence=1, action_id="claim_to_seller", kind="document", status="submitted")
        s.add(action)
        s.flush()
        s.add(Deadline(case_id=case.id, action_id=action.id, due_date=due, remind_before_days=[2, 0],
                       reminders_sent=[]))
        s.commit()


def test_deadline_sms_only_on_the_last_day_and_after(setup):
    ctx, api, cid = setup
    verify(ctx, cid, email="client@mail.kz", phone="+77011234567")
    due = date(2026, 10, 10)
    _awaiting(ctx, cid, due)
    sms, mail = ctx.container.sms_sender, ctx.container.email_sender
    ctx.container.scheduler.extra_jobs.clear()  # case reports are tested on their own

    view = api.get("/v1/cases").json()[0]
    assert view["deadline"]["due_date"] == "2026-10-10" and view["deadline"]["status"] == "active"
    today = ctx.container.packs.pack("KZ").local_now().date()
    assert view["deadline"]["days_left"] == (due - today).days

    at = lambda d: datetime(d.year, d.month, d.day, 6, 0, tzinfo=timezone.utc)  # noqa: E731
    assert ctx.container.scheduler.tick(at(due - timedelta(days=2))) == 1
    assert len(mail.sent) == 1 and sms.sent == []  # two days left: e-mail only
    assert ctx.container.scheduler.tick(at(due)) == 1
    assert "последний день" in sms.sent[-1][2]
    assert ctx.container.scheduler.tick(at(due + timedelta(days=1))) == 1
    assert "истёк" in sms.sent[-1][2] and len(sms.sent) == 2 and len(mail.sent) == 3

    view = api.get(f"/v1/cases/{cid}").json()
    assert view["deadline"]["status"] == "expired"
    kinds = [n["kind"] for n in api.get("/v1/notifications").json()["items"]]
    assert kinds == ["deadline_expired", "deadline_reminder", "deadline_reminder"]
