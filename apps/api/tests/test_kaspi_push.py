"""Kaspi Pay pushes (owner 01.10, «Автоподтверждение Kaspi без оператора»): the payments phone forwards every Kaspi Pay
notification; one bill of that amount with «Оплатить» in the last hour → paid at once, as the desk's «Оплата
получена»; none or several → the desk gets the push and the candidates. No push 15 minutes after «Оплатить» → one
reminder to the client and no new bills until it is paid."""

from __future__ import annotations

import time
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update

from konsilier.api.kaspi_push import read_body, reminders
from konsilier import kaspi_parse as kp
from konsilier.core.models import Invoice, KaspiPush, Notification, User, utcnow

from .test_e2e import run_intake
from .test_payment import ANSWERS, STORY
from .test_payment_ways import DESK, open_bill, ways
from .test_ops_centre import operator

TOKEN = "test-push-token"  # placeholder; the real one lives only in the server's .env
H = {"X-Konsilier-Token": TOKEN}


def on(ctx, background: str = "inline"):
    outbox = ways(ctx, methods="kaspi_link,bank_invoice")
    ctx.container.settings.payment_kaspi_push_token = TOKEN
    ctx.container.engine.config.kaspi_push = True
    ctx.container.settings.background_jobs = background
    return outbox


def pressed_pay(ctx, phone: str):
    """«Оплатить в Kaspi» (the way) and «Оплатить» (the claim), as the one-tap payment window does."""
    api, cid, pay = open_bill(ctx, phone=phone)
    with ctx.container.session_factory() as s:
        s.get(User, s.get(Invoice, pay["invoice_id"]).user_id).email = "client@mail.kz"
        s.commit()
    api.post(f"/v1/invoices/{pay['invoice_id']}/way", json={"way": "kaspi_link"})
    api.post(f"/v1/cases/{cid}/payment/claim")
    assert status(ctx, pay["invoice_id"]) == "awaiting_confirmation"  # «ждёт сверки» (one-tap may show it as given)
    return api, cid, pay


def push(ctx, text: str, title: str = "Kaspi Pay", **kw):
    r = ctx.client.post("/v1/payments/kaspi/push", json={"title": title, "text": text, **kw}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def status(ctx, invoice_id: int) -> str:
    with ctx.container.session_factory() as s:
        return s.get(Invoice, invoice_id).status


def test_parser_reads_kaspi_formats():
    p = kp.parse("Kaspi Pay", "Поступила оплата 1 990 ₸ от Имя Ф.")
    assert (p.amount, p.payer, p.incoming) == (Decimal("1990.00"), "Имя Ф.", True)
    assert kp.parse(None, "+1990 ₸").amount == Decimal("1990.00")
    assert kp.parse("Оплата", "1 990 ₸").amount == Decimal("1990.00")  # no-break and thin spaces
    assert kp.parse(None, "Покупка 9 990,00 тг").amount == Decimal("9990.00")
    assert kp.parse(None, "Оплата 1990.50 KZT").amount == Decimal("1990.50")
    assert kp.parse(None, "KZT 1 990").amount == Decimal("1990.00")
    assert kp.parse(None, "Оплата 1,990 ₸").amount == Decimal("1990.00")
    # the balance after the payment is not the payment; a «+» sum wins
    assert kp.parse(None, "Баланс: 15 000 ₸. Поступление +1 990 ₸ от Айгерим Н.").amount == Decimal("1990.00")
    assert kp.parse(None, "Оплата 1 990 ₸. Остаток 15 000 ₸").amount == Decimal("1990.00")
    assert not kp.parse(None, "Возврат 1 990 ₸ покупателю").incoming
    assert not kp.parse(None, "-1 990 ₸").incoming
    assert kp.parse("Kaspi Pay", "Обновите приложение").amount is None


def test_body_in_any_shape():
    assert read_body('{"title": "Kaspi Pay", "text": "+1990 ₸"}', "application/json") == ("Kaspi Pay", "+1990 ₸", None)
    # MacroDroid pastes the text as is: a quote breaks the JSON — the fields are still read
    assert read_body('{"title":"Kaspi Pay","text":"Оплата 1 990 ₸ от ТОО "Ромашка""}', "application/json") == \
        ("Kaspi Pay", 'Оплата 1 990 ₸ от ТОО "Ромашка"', None)
    assert read_body("title=Kaspi+Pay&text=%2B1990+%E2%82%B8", "application/x-www-form-urlencoded") == \
        ("Kaspi Pay", "+1990 ₸", None)
    assert read_body("+1990 ₸", "text/plain") == (None, "+1990 ₸", None)


def test_token(ctx):
    on(ctx)
    ctx.container.settings.payment_kaspi_push_token = ""
    assert ctx.client.post("/v1/payments/kaspi/push", json={"text": "+1990 ₸"}, headers=H).status_code == 404  # off
    ctx.container.settings.payment_kaspi_push_token = TOKEN
    assert ctx.client.post("/v1/payments/kaspi/push", json={"text": "+1990 ₸"}).status_code == 401
    assert ctx.client.post("/v1/payments/kaspi/push", json={"text": "+1990 ₸"},
                           headers={"X-Konsilier-Token": "wrong"}).status_code == 401
    big = ctx.client.post("/v1/payments/kaspi/push", content=b"x" * 100_000, headers=H)
    assert big.status_code == 200 and big.json()["status"] == "ignored"
    with ctx.container.session_factory() as s:
        assert all(len(p.raw) <= 16_384 for p in s.scalars(select(KaspiPush)).all())


def test_one_bill_is_paid_at_once_and_the_document_follows(ctx):
    outbox = on(ctx)
    api, cid, pay = pressed_pay(ctx, "+7 701 555 00 41")
    assert not any(m[0] == DESK for m in outbox.sent)  # «Оплатить» mails no one: the push will confirm it
    outbox.sent.clear()
    r = push(ctx, "Поступила оплата 2 990 ₸ от Имя Ф.")
    assert r["status"] == "matched" and r["invoice"] == pay["code"]
    assert status(ctx, pay["invoice_id"]) == "paid"
    with ctx.container.session_factory() as s:
        inv = s.get(Invoice, pay["invoice_id"])
        assert inv.decided_by == "kaspi:push"
        row = s.scalar(select(KaspiPush))
        assert (row.amount, row.payer, row.invoice_id) == (Decimal("2990.00"), "Имя Ф.", inv.id)
        assert s.scalar(select(Notification).where(Notification.kind == "payment")).text.startswith("Оплата получена")
    assert not any("проверьте" in m[1] for m in outbox.sent)  # nothing for the desk
    # the document was prepared right after the commit, as after the desk's «Оплата получена»
    a = api.get(f"/v1/cases/{cid}").json()["actions"][0]
    assert a["downloadable"] is True
    api.get(f"/v1/cases/{cid}/actions/{a['id']}/document?format=docx")
    assert any(m[0] == "client@mail.kz" and "Оплата получена" in m[2] for m in outbox.sent)


def test_confirmation_is_immediate(ctx):
    """Owner: the paid status and the client's «Оплата получена» are written in the push request itself (< 1 s); the
    letters and the document come after the commit."""
    on(ctx, background="off")  # only what the request itself does
    api, cid, pay = pressed_pay(ctx, "+7 701 555 00 42")
    started = time.perf_counter()
    r = push(ctx, "+2990 ₸")
    assert time.perf_counter() - started < 1.0
    assert r["status"] == "matched" and status(ctx, pay["invoice_id"]) == "paid"
    with ctx.container.session_factory() as s:
        n = s.scalar(select(Notification).where(Notification.kind == "payment"))
        assert n is not None and "Оплата получена" in n.text
    case = api.get(f"/v1/cases/{cid}").json()
    assert case["payment"] is None or case["payment"]["status"] == "paid"


def test_duplicate_push_counts_once(ctx):
    on(ctx)
    _, _, a = pressed_pay(ctx, "+7 701 555 00 43")
    _, _, b = pressed_pay(ctx, "+7 701 555 00 44")
    first = push(ctx, "2 990 ₸ от Имя Ф.", posted_at="1759300000000")
    again = push(ctx, "2 990 ₸ от Имя Ф.", posted_at="1759300000000")
    assert first["status"] == "ambiguous" and again["status"] == "duplicate" and again["duplicate_of"] == first["id"]
    with ctx.container.session_factory() as s:
        assert len(s.scalars(select(KaspiPush)).all()) == 2  # both kept, for tuning
    # the same text at another time is another payment
    assert push(ctx, "2 990 ₸ от Имя Ф.", posted_at="1759300090000")["status"] == "ambiguous"
    assert status(ctx, a["invoice_id"]) == status(ctx, b["invoice_id"]) == "awaiting_confirmation"


def test_two_candidates_go_to_the_desk(ctx):
    outbox = on(ctx)
    _, _, a = pressed_pay(ctx, "+7 701 555 00 45")
    _, _, b = pressed_pay(ctx, "+7 701 555 00 46")
    outbox.sent.clear()
    r = push(ctx, "Поступила оплата 2 990 ₸ от Имя Ф.")
    assert r["status"] == "ambiguous" and r["candidates"] == 2
    assert status(ctx, a["invoice_id"]) == status(ctx, b["invoice_id"]) == "awaiting_confirmation"  # «ждёт сверки»
    to, subject, text = next(m for m in outbox.sent if m[0] == DESK)
    assert "несколько счетов" in subject and a["code"] in text and b["code"] in text and "Имя Ф." in text
    # the owner picks the bill in /ops
    desk = operator(ctx, DESK)
    listed = desk.get("/v1/ops/clients/payments/kaspi").json()
    p = next(x for x in listed["pushes"] if x["id"] == r["id"])
    assert {c["code"] for c in p["candidates"]} == {a["code"], b["code"]}
    desk.post(f"/v1/ops/clients/payments/kaspi/{r['id']}", json={"decision": "match", "invoice_id": b["invoice_id"]})
    assert status(ctx, b["invoice_id"]) == "paid" and status(ctx, a["invoice_id"]) == "awaiting_confirmation"
    assert all(x["id"] != r["id"] for x in desk.get("/v1/ops/clients/payments/kaspi").json()["pushes"])


def test_zero_candidates_go_to_the_desk(ctx):
    outbox = on(ctx)
    _, _, a = pressed_pay(ctx, "+7 701 555 00 47")
    outbox.sent.clear()
    r = push(ctx, "Поступила оплата 5 000 ₸ от Кто-то К.")
    assert r["status"] == "unmatched" and status(ctx, a["invoice_id"]) == "awaiting_confirmation"
    assert any(m[0] == DESK and "не найдена" in m[1] and "5 000" in m[2] for m in outbox.sent)
    # a bill pressed more than an hour ago is not a candidate either
    with ctx.container.session_factory() as s:
        s.execute(update(Invoice).values(claimed_at=utcnow() - timedelta(minutes=61),
                                         updated_at=utcnow() - timedelta(minutes=61)))
        s.commit()
    assert push(ctx, "+2 990 ₸ от Имя Ф.")["status"] == "unmatched"
    desk = operator(ctx, DESK)
    listed = desk.get("/v1/ops/clients/payments/kaspi").json()
    assert listed["enabled"] and {p["status"] for p in listed["pushes"]} == {"unmatched"}
    assert [i["code"] for i in listed["invoices"]] == [a["code"]]  # unpaid, no push: «не найдено»
    dismissed = desk.post(f"/v1/ops/clients/payments/kaspi/{r['id']}", json={"decision": "dismiss"})
    assert dismissed["status"] == "ignored"


def test_push_before_the_claim_is_matched_on_the_claim(ctx):
    on(ctx)
    api, cid, pay = open_bill(ctx, phone="+7 701 555 00 48")
    assert push(ctx, "+2990 ₸")["status"] == "unmatched"  # paid by the link before «Оплатить» on the site
    api.post(f"/v1/invoices/{pay['invoice_id']}/way", json={"way": "kaspi_link"})
    assert status(ctx, pay["invoice_id"]) == "paid"


def test_reminder_once_after_15_minutes_and_no_new_bills_until_paid(ctx):
    outbox = on(ctx)
    api, cid, pay = pressed_pay(ctx, "+7 701 555 00 49")
    job = reminders(ctx.container)

    def payment_notes() -> list[str]:
        with ctx.container.session_factory() as s:
            return [n.text for n in s.scalars(select(Notification).where(Notification.kind == "payment_reminder")).all()]

    with ctx.container.session_factory() as s:
        assert job(s, utcnow() + timedelta(minutes=14)) == 0  # too early
        s.commit()
    # a second case of the same person can still be billed now
    cid2 = api.post("/v1/cases", expect=201, json={"text": STORY, "country": "KZ"})["case"]["id"]
    assert run_intake(api, cid2, ANSWERS)["status"] == "qualified"
    with ctx.container.session_factory() as s:
        s.execute(update(Invoice).where(Invoice.id == pay["invoice_id"])
                  .values(claimed_at=utcnow() - timedelta(minutes=16)))
        s.commit()
    outbox.sent.clear()
    with ctx.container.session_factory() as s:
        assert job(s, utcnow()) == 1
        s.commit()
    with ctx.container.session_factory() as s:
        assert job(s, utcnow() + timedelta(hours=3)) == 0  # one reminder only
        s.commit()
    notes = payment_notes()
    assert len(notes) == 1 and "Мы пока не видим оплату 2 990 ₸" in notes[0]
    assert any(m[0] == "client@mail.kz" and "не видим оплату" in m[2] for m in outbox.sent)  # also by e-mail to the client
    # new documents are stopped: no bill for the other case, no plan
    r = ctx.client.post(f"/v1/cases/{cid2}/payment", json={"purpose": "document"}, headers=api.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "unpaid_invoice"
    assert pay["code"] in r.json()["detail"]["message"]
    assert ctx.client.post("/v1/plans/biz/invoice", headers=api.h).json()["detail"]["code"] == "unpaid_invoice"
    # its push comes (still within the hour of «Оплатить»): paid, and the stop is lifted
    assert push(ctx, "+2990 ₸")["status"] == "matched"
    assert api.post(f"/v1/cases/{cid2}/payment", json={"purpose": "document"})["case"]["payment"]["status"] == "pending"
