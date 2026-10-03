"""Case status reports and next-step reminders by e-mail."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from konsilier.core.models import Case
from konsilier.identity.senders import LogSender

from .test_e2e import Api, web_user

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def tick(ctx, at: datetime) -> int:
    with ctx.container.session_factory() as s:
        n = ctx.container.reporter.tick(s, at)
        s.commit()
        return n


@pytest.fixture
def client(ctx):
    """A client with a verified e-mail and a fresh KZ case."""
    c = ctx.container
    c.email_sender = LogSender("email")
    c.settings.dev_show_codes = True
    api = web_user(ctx)
    code = api.post("/v1/auth/email/start", json={"target": "client@mail.kz"})["dev_code"]
    api.post("/v1/auth/email/verify", json={"target": "client@mail.kz", "code": code})
    c.email_sender.sent.clear()  # only reports from here on
    cid = api.post("/v1/cases", expect=201, json={
        "text": "Купил телефон в магазине за 150000 тенге, через неделю сломался, деньги не возвращают",
        "country": "KZ"})["case"]["id"]
    return ctx, api, cid


def mails(ctx) -> list[tuple[str, str]]:
    return ctx.container.email_sender.sent


def test_baseline_then_update_then_reminders_capped(client):
    ctx, api, cid = client
    assert tick(ctx, T0) == 0 and mails(ctx) == []  # first sight: baseline only, nothing mailed

    api.answer(cid, "ТОО Технодом")  # the case moves → a report
    assert tick(ctx, T0 + timedelta(minutes=5)) == 0  # debounced: too soon after the baseline
    assert tick(ctx, T0 + timedelta(minutes=15)) == 1
    to, body = mails(ctx)[-1]
    assert to == "client@mail.kz"
    assert "этап 1 из 7" in body and "Следующий шаг:" in body and "Ответьте на вопрос" in body
    assert re.search(r"/case/" + cid, body) and "/account" in body

    # nothing moves: a reminder every 3 days, at most 5 in a row
    t = T0 + timedelta(minutes=15)
    sent = 0
    for _ in range(8):
        t += timedelta(days=3, minutes=1)
        sent += tick(ctx, t)
    assert sent == 5
    assert "Напоминание" not in mails(ctx)[-1][1]  # subject is separate; body repeats the next step
    assert "Ответьте на вопрос" in mails(ctx)[-1][1]


def test_ready_document_report_contains_instructions(client):
    ctx, api, cid = client
    ctx.container.engine.config.approval_required_first_n = 0
    tick(ctx, T0)
    reply = api.get(f"/v1/cases/{cid}").json()["question"]
    answers = {"seller_name": "ТОО Технодом", "seller_bin": "пропустить", "goods_description": "Телефон",
               "purchase_date": "12.08.2026", "amount": "150000", "problem_description": "Сломался",
               "applicant_name": "Тестов Тест", "applicant_phone": "+77011234567", "applicant_iin": "пропустить",
               "seller_email": "пропустить"}
    q = reply
    for _ in range(25):
        if q is None:
            break
        q = api.answer(cid, answers.get(q["field"], "пропустить"))["reply"]["question"]
    api.post(f"/v1/cases/{cid}/actions/next")
    assert tick(ctx, T0 + timedelta(hours=1)) == 1
    body = mails(ctx)[-1][1]
    assert "Подайте документ" in body and "1. " in body and "подготовлен документ" in body


def test_no_mail_without_verified_email_or_when_switched_off(ctx, client):
    ctx_, api, cid = client
    api.post("/v1/cases", expect=201, json={"text": "Магазин не возвращает деньги за телефон 150000", "country": "KZ"})
    other: Api = web_user(ctx_)  # never verified an e-mail
    ocid = other.post("/v1/cases", expect=201, json={"text": "Магазин не возвращает деньги за телефон 90000",
                                                     "country": "KZ"})["case"]["id"]
    tick(ctx_, T0)
    other.answer(ocid, "ТОО Магазин")
    assert tick(ctx_, T0 + timedelta(hours=1)) == 0
    # the client switches e-mail reports off
    assert ctx_.client.patch("/v1/me", headers=api.h, json={"notify_email": False}).json()["notify_email"] is False
    api.answer(cid, "ТОО Технодом")
    assert tick(ctx_, T0 + timedelta(hours=2)) == 0
    assert mails(ctx_) == []


def test_closed_cases_get_nothing(client):
    ctx, api, cid = client
    tick(ctx, T0)
    with ctx.container.session_factory() as s:
        s.get(Case, __import__("uuid").UUID(cid)).status = "resolved"
        s.commit()
    assert tick(ctx, T0 + timedelta(days=30)) == 0
