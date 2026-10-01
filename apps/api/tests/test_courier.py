"""«Доставить курьером» (pilot «Курьер», owner 01.10.2026): the order and its bill, the manual path in /ops, CDEK and
Alem TAT behind fake HTTP (order, intake, polling, webhook, return of the signed copy), the response deadline from
the day of delivery, the Kaspi Pay push confirming the delivery bill."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from konsilier.config import Settings
from konsilier.core.models import Action, Case, Deadline, Delivery, Filing, Invoice, Notification, User, utcnow
from konsilier.courier.providers import (AlemTatProvider, CdekProvider, ManualProvider, ProviderError,
                                         build_provider)

from .test_e2e import web_user
from .test_lawyer_onboarding import Outbox

ADMIN = {"X-Admin-Token": "adm"}
COURIER_YAML = """
enabled: true
price: 3990
currency: TST
cities:
  - id: testville
    name: {en: Testville}
    cdek_city_code: 4756
    alemtat_locality: "TST01"
    alemtat_station: "ST1"
windows: ["10:00-14:00", "14:00-18:00"]
lead_hours: 2
max_days: 14
cdek: {currency: 2, tariff_code: 480, services: [REVERSE]}
alemtat: {service: "E", country: "TS", weight: 0.3}
texts:
  en:
    paid: "Paid: pickup {date}, {window}, {address}."
    ordered: "Courier ordered ({provider}): {date}, {window}.{tracking}"
    picked_up: "Picked up for {recipient}."
    in_transit: "On the way to {recipient}."
    delivered: "Delivered to {recipient}{signer}, {date}{due}."
    refused: "Refused by {recipient}."
    returned: "Second copy returned."
    cancelled: "Cancelled."
    problem: "Delay."
    tracking: " Track: {tracking}."
    due: " (reply by {due})"
    signer: " (signed: {name})"
    provider_cdek: "CDEK"
    provider_manual: "courier service"
    price_note: "We pick up, deliver, bring back."
    print_hint: "Print 2 copies."
"""


def tomorrow() -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


ORDER = {"city": "testville", "window": "10:00-14:00", "pickup_address": "Abay ave 1, apt 2",
         "contact_name": "Ivan Ivanov", "contact_phone": "+7 701 555 00 11", "recipient_name": "Widget Corp",
         "recipient_address": "Dostyk 5, office 10", "recipient_phone": "+7 702 000 11 22"}


@pytest.fixture
def case(ctx):
    """A paid, ready document of an XX case; the pack has a courier."""
    c = ctx.container
    c.engine.config.approval_required_first_n = 0
    c.email_sender = Outbox()
    c.settings.ops_clients_emails = "desk@konsilier.com"
    (c.packs.pack("XX").root / "courier.yaml").write_text(COURIER_YAML, "utf-8")
    api = web_user(ctx)
    cid = api.post("/v1/cases", expect=201, json={"text": "My dummy widget was never delivered", "country": "XX",
                                                  "language": "en"})["case"]["id"]
    api.answer(cid, "Widget Corp")
    api.answer(cid, "1200")
    aid = api.post(f"/v1/cases/{cid}/actions/next")["case"]["actions"][0]["id"]
    with c.session_factory() as s:
        s.get(Action, uuid.UUID(aid)).unlocked_by = "credit"
        user = s.get(User, s.get(Case, uuid.UUID(cid)).owner_id)
        user.email = "client@mail.kz"
        s.commit()
    return ctx, api, cid, aid


def url(cid, aid):
    return f"/v1/cases/{cid}/actions/{aid}/courier"


def order(api, cid, aid, **over):
    return api.post(url(cid, aid), json={**ORDER, "date": tomorrow(), **over})


def delivery(ctx) -> Delivery:
    with ctx.container.session_factory() as s:
        d = s.query(Delivery).order_by(Delivery.created_at.desc()).first()
        s.expunge(d)
        return d


def texts(ctx, cid) -> list[str]:
    with ctx.container.session_factory() as s:
        return [n.text for n in s.query(Notification).filter(Notification.case_id == uuid.UUID(cid))
                .order_by(Notification.id)]


# ------------------------------------------------------------------ the form and the order (manual provider)
def test_form_and_manual_path_to_deadline(case):
    ctx, api, cid, aid = case
    form = api.get(url(cid, aid)).json()
    assert form["available"] and form["price"] == 3990 and form["provider"] == "manual"
    assert form["cities"] == [{"id": "testville", "name": "Testville"}] and form["windows"][0] == "10:00-14:00"
    assert form["defaults"]["recipient_name"] == "Widget Corp" and form["note"]

    out = order(api, cid, aid)  # stub payments: paid at once → the desk orders the courier by hand
    view = out["courier"]["delivery"]
    assert view["status"] == "paid" and view["price"] == 3990 and not out["courier"]["available"]
    a = out["case"]["actions"][0]
    assert a["courier"]["delivery"]["id"] == view["id"] and a["filings"] == []  # the proof is in the courier card
    assert any("Курьер: закажите доставку" in subj for _, subj, _ in ctx.container.email_sender.sent)
    with ctx.container.session_factory() as s:
        inv = s.query(Invoice).filter(Invoice.purpose == "delivery").one()
        assert inv.status == "paid" and inv.amount == 3990
        assert s.get(Case, uuid.UUID(cid)).doc_credits == 0  # a delivery bill never unlocks a document
        f = s.query(Filing).filter(Filing.channel == "courier").one()
        assert f.status == "sending" and f.doc_sha256 and "Dostyk 5" in f.recipient
    r = ctx.client.post(url(cid, aid), headers=api.h, json={**ORDER, "date": tomorrow()})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_ordered"

    ops = ctx.client.get("/v1/admin/courier", headers=ADMIN).json()
    assert ops["provider"] == "manual" and [i["id"] for i in ops["items"]] == [view["id"]]
    did = view["id"]
    up = lambda **kw: ctx.client.post(f"/v1/admin/courier/{did}", headers=ADMIN, json=kw)  # noqa: E731
    assert up(status="ordered", tracking="TRK-1").json()["tracking"] == "TRK-1"
    assert up(status="picked_up").status_code == 200
    assert up(status="ordered").status_code == 409  # never back
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    r = up(status="delivered", signer_name="A. Petrov, manager", at=yesterday.isoformat())
    assert r.status_code == 200 and r.json()["signer_name"] == "A. Petrov, manager"

    case_view = api.get(f"/v1/cases/{cid}").json()
    a = case_view["actions"][0]
    assert a["status"] == "submitted" and a["submitted_via"] == "courier"
    assert a["submitted_at"][:10] == yesterday.date().isoformat()  # the deadline runs from the day of delivery
    assert case_view["status"] == "awaiting_response"
    with ctx.container.session_factory() as s:
        dl = s.query(Deadline).one()
        assert dl.due_date > yesterday.date()
        f = s.query(Filing).filter(Filing.channel == "courier").one()
        assert f.status == "delivered" and f.external_id == "TRK-1" and f.sent_at is not None
    up(status="returned")
    assert delivery(ctx).status == "returned" and delivery(ctx).returned_at
    said = texts(ctx, cid)
    assert any(t.startswith("Paid: pickup") for t in said)
    assert any("Track: TRK-1" in t for t in said)
    delivered = next(t for t in said if t.startswith("Delivered"))
    assert "signed: A. Petrov" in delivered and "reply by" in delivered
    assert said[-1] == "Second copy returned."
    assert ctx.client.get("/v1/admin/courier", headers=ADMIN).json()["items"] == []  # nothing left on its way


def test_validation_and_unpaid_document(case):
    ctx, api, cid, aid = case
    bad = lambda **kw: ctx.client.post(url(cid, aid), headers=api.h, json={**ORDER, "date": tomorrow(), **kw})  # noqa: E731
    assert bad(window="09:00-10:00").json()["detail"]["code"] == "bad_window"
    assert bad(date=(date.today() - timedelta(days=1)).isoformat()).json()["detail"]["code"] == "bad_date"
    assert bad(date=(date.today() + timedelta(days=30)).isoformat()).json()["detail"]["code"] == "bad_date"
    assert bad(contact_phone="123").json()["detail"]["code"] == "bad_contact_phone"
    assert bad(recipient_phone="12").json()["detail"]["code"] == "bad_recipient_phone"
    assert bad(pickup_address="x").json()["detail"]["code"] == "bad_pickup_address"
    assert bad(city="nowhere").json()["detail"]["code"] == "bad_city"
    with ctx.container.session_factory() as s:
        s.get(Action, uuid.UUID(aid)).unlocked_by = "free"
        s.commit()
    r = bad()
    assert r.status_code == 402 and r.json()["detail"]["code"] == "payment_required"
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["courier"]["reason"] == "payment_required"
    with ctx.container.session_factory() as s:
        assert s.query(Delivery).count() == 0 and s.query(Invoice).filter(Invoice.purpose == "delivery").count() == 0


def test_off_without_pack_data_or_setting(case):
    ctx, api, cid, aid = case
    ctx.container.settings.courier_enabled = False
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["courier"] is None
    ctx.container.settings.courier_enabled = True
    (ctx.container.packs.pack("XX").root / "courier.yaml").unlink()
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["courier"] is None


# ------------------------------------------------------------------ paying the delivery bill like the document's
def test_delivery_bill_paid_by_kaspi_push_then_cancel_rules(case):
    from .test_kaspi_push import H, TOKEN
    from .test_payment_ways import ways

    ctx, api, cid, aid = case
    ways(ctx, methods="kaspi_link")
    ctx.container.settings.background_jobs = "inline"  # the client's e-mail goes after the commit
    ctx.container.settings.payment_kaspi_push_token = TOKEN
    ctx.container.engine.config.kaspi_push = True
    ctx.container.email_sender = Outbox()
    out = order(api, cid, aid)
    d = out["courier"]["delivery"]
    assert d["status"] == "awaiting_payment" and d["invoice"]["amount"] == 3990
    assert any(w["id"] == "kaspi_link" for w in d["invoice"]["ways"])
    api.post(f"/v1/invoices/{d['invoice']['id']}/way", json={"way": "kaspi_link"})
    claimed = api.post(f"/v1/cases/{cid}/courier/{d['id']}/claim")
    assert claimed["courier"]["delivery"]["invoice"]["status"] == "awaiting_confirmation"
    r = ctx.client.post(f"/v1/cases/{cid}/courier/{d['id']}/cancel", headers=api.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "invoice_awaiting_confirmation"
    r = ctx.client.post("/v1/payments/kaspi/push", json={"title": "Kaspi Pay", "text": "Поступила оплата 3 990 ₸"},
                        headers=H)
    assert r.json()["status"] == "matched", r.text
    got = delivery(ctx)
    assert got.status == "paid" and got.paid_at is not None
    with ctx.container.session_factory() as s:
        assert s.get(Invoice, got.invoice_id).status == "paid"
    assert any("Оплата доставки получена" in text for _, _, text in ctx.container.email_sender.sent)
    r = ctx.client.post(f"/v1/cases/{cid}/courier/{d['id']}/cancel", headers=api.h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cannot_cancel"


def test_client_cancels_before_paying_and_orders_again(case):
    from .test_payment_ways import ways

    ctx, api, cid, aid = case
    ways(ctx, methods="kaspi_link")
    d = order(api, cid, aid)["courier"]["delivery"]
    out = api.post(f"/v1/cases/{cid}/courier/{d['id']}/cancel")
    assert out["courier"]["delivery"]["status"] == "cancelled" and out["courier"]["available"]
    with ctx.container.session_factory() as s:
        assert s.get(Invoice, d["invoice"]["id"]).status == "cancelled"
    assert order(api, cid, aid)["courier"]["delivery"]["status"] == "awaiting_payment"


# ------------------------------------------------------------------ CDEK behind fake HTTP
class FakeCdek:
    """api.edu.cdek.ru as far as we use it."""

    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []
        self.statuses = [{"code": "ACCEPTED", "name": "Принят", "date_time": "2026-10-02T09:00:00+0600"}]
        self.reverse: list[dict] = []
        self.signer = None
        self.tokens = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content and request.method != "GET" and \
            request.headers.get("content-type", "").startswith("application/json") else None
        self.calls.append((request.method, path, body))
        if path == "/v2/oauth/token":
            assert b"client_credentials" in request.content
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"tok{self.tokens}", "token_type": "bearer",
                                             "expires_in": 3599})
        assert request.headers["Authorization"].startswith("Bearer tok")
        if path == "/v2/orders" and request.method == "POST":
            return httpx.Response(202, json={"entity": {"uuid": "ord-uuid-1"}, "requests": [
                {"request_uuid": "r1", "type": "CREATE", "state": "ACCEPTED"}]})
        if path == "/v2/intakes":
            return httpx.Response(202, json={"entity": {"uuid": "intake-1"}, "requests": []})
        if path == "/v2/calculator/tariff":
            return httpx.Response(200, json={"total_sum": 1600, "currency": "KZT", "period_min": 1, "period_max": 1})
        if path == "/v2/orders/ord-uuid-1" and request.method == "GET":
            entity = {"uuid": "ord-uuid-1", "cdek_number": "1234567890", "statuses": list(reversed(self.statuses))}
            if self.signer:
                entity["delivery_detail"] = {"recipient_name": self.signer}
            if self.reverse:
                entity["related_entities"] = [{"type": "reverse_order", "uuid": "rev-uuid"}]
            return httpx.Response(200, json={"entity": entity})
        if path == "/v2/orders/rev-uuid":
            return httpx.Response(200, json={"entity": {"uuid": "rev-uuid", "statuses": self.reverse}})
        if path == "/v2/orders/ord-uuid-1" and request.method == "DELETE":
            return httpx.Response(202, json={"entity": {"uuid": "ord-uuid-1"}})
        if path == "/v2/webhooks":
            return httpx.Response(200, json={"entity": {"uuid": "wh-1"}})
        return httpx.Response(404, json={"errors": [{"code": "not_found", "message": "no"}]})


@pytest.fixture
def cdek(case):
    ctx = case[0]
    fake = FakeCdek()
    ctx.container.courier.provider = CdekProvider("test-id", "test-secret-value", "https://api.edu.cdek.ru",
                                                  http=httpx.Client(transport=httpx.MockTransport(fake)))
    return (*case, fake)


def test_cdek_order_poll_webhook_and_return(cdek, caplog):
    ctx, api, cid, aid, fake = cdek
    job = ctx.container.courier.job
    r = ctx.client.post(url(cid, aid), headers=api.h, json={**ORDER, "date": tomorrow(), "recipient_phone": ""})
    assert r.json()["detail"]["code"] == "recipient_phone_required"  # CDEK needs the recipient's phone
    out = order(api, cid, aid)
    assert out["courier"]["delivery"]["status"] == "paid"  # stub payment; the order goes after the commit / by the job
    with ctx.container.session_factory() as s:
        assert job(s, utcnow()) == 1
        s.commit()
    d = delivery(ctx)
    assert d.status == "ordered" and d.external_id == "ord-uuid-1" and d.meta["intake_uuid"] == "intake-1"
    assert d.meta["cost"] == "1600"
    sent = next(b for m, p, b in fake.calls if p == "/v2/orders" and m == "POST")
    assert sent["services"] == [{"code": "REVERSE"}] and sent["to_location"]["code"] == 4756
    assert sent["recipient"]["phones"] == [{"number": "+77020001122"}] and sent["number"] == str(d.id)
    intake = next(b for m, p, b in fake.calls if p == "/v2/intakes")
    assert intake["intake_date"] == tomorrow() and intake["intake_time_from"] == "10:00"

    # polling: at most every COURIER_POLL_MINUTES
    fake.statuses.append({"code": "RECEIVED_AT_SHIPMENT_WAREHOUSE", "name": "Принят на склад",
                          "date_time": "2026-10-02T12:00:00+0600"})
    with ctx.container.session_factory() as s:
        assert job(s, utcnow()) == 0  # polled just now (placed)
        assert job(s, utcnow() + timedelta(minutes=31)) == 1
        s.commit()
    d = delivery(ctx)
    assert d.status == "picked_up" and d.tracking == "1234567890"

    # the webhook names the order; the status is read from the API
    fake.statuses.append({"code": "DELIVERED", "name": "Вручен", "date_time": "2026-10-03T11:00:00+0600"})
    fake.signer = "Petrov A."
    ctx.container.settings.courier_webhook_token = "hook-token"
    hook = {"type": "ORDER_STATUS", "uuid": "ord-uuid-1", "attributes": {"code": "DELIVERED"}}
    assert ctx.client.post("/v1/webhooks/courier/cdek", json=hook).status_code == 401
    assert ctx.client.post("/v1/webhooks/courier/cdek?token=nope", json=hook).status_code == 401
    r = ctx.client.post("/v1/webhooks/courier/cdek?token=hook-token", json=hook)
    assert r.json() == {"ok": True, "matched": True, "status": "delivered"}
    d = delivery(ctx)
    assert d.signer_name == "Petrov A." and d.delivered_at.date() == date(2026, 10, 3)
    view = api.get(f"/v1/cases/{cid}").json()
    a = view["actions"][0]
    assert a["status"] == "submitted" and a["submitted_via"] == "courier" and a["submitted_at"][:10] == "2026-10-03"
    with ctx.container.session_factory() as s:
        due = ctx.container.packs.pack("XX").add_days(date(2026, 10, 3), None, 3)  # the scenario's 3 business days
        assert s.query(Deadline).one().due_date == due

    # «Реверс»: the related return order reaches the sender → returned
    fake.reverse = [{"code": "DELIVERED", "name": "Вручен", "date_time": "2026-10-04T15:00:00+0600"}]
    r = ctx.client.post("/v1/webhooks/courier/cdek?token=hook-token", json=hook)
    assert r.json()["status"] == "returned"
    said = texts(ctx, cid)
    assert sum(t.startswith("Delivered") for t in said) == 1 and said[-1] == "Second copy returned."
    assert "test-secret-value" not in caplog.text


def test_cdek_failure_is_retried_and_the_desk_told(cdek):
    ctx, api, cid, aid, _fake = cdek
    ctx.container.courier.provider = CdekProvider(
        "id", "test-secret-value", "https://api.edu.cdek.ru",
        http=httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"error": "invalid_client"}))))
    order(api, cid, aid)
    job = ctx.container.courier.job
    with ctx.container.session_factory() as s:
        assert job(s, utcnow()) == 0
        s.commit()
    d = delivery(ctx)
    assert d.status == "paid" and d.attempts == 1 and d.error.startswith("auth_failed")
    assert "test-secret-value" not in (d.error or "")
    assert any("ошибка заказа" in subj for _, subj, _ in ctx.container.email_sender.sent)
    with ctx.container.session_factory() as s:
        assert job(s, utcnow() + timedelta(minutes=1)) == 0
        assert s.get(Delivery, d.id).attempts == 1  # not before PLACE_RETRY
        job(s, utcnow() + timedelta(minutes=11))
        s.commit()
    assert delivery(ctx).attempts == 2
    # the operator takes the order over by hand: no more API calls for it
    r = ctx.client.post(f"/v1/admin/courier/{d.id}", headers=ADMIN, json={"status": "ordered", "tracking": "M-7"})
    assert r.status_code == 200 and r.json()["provider"] == "manual" and r.json()["status"] == "ordered"


def test_cdek_cancel_by_operator(cdek):
    ctx, api, cid, aid, fake = cdek
    order(api, cid, aid)
    with ctx.container.session_factory() as s:
        ctx.container.courier.job(s, utcnow())
        s.commit()
    did = delivery(ctx).id
    r = ctx.client.post(f"/v1/admin/courier/{did}", headers=ADMIN, json={"status": "cancelled"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert ("DELETE", "/v2/orders/ord-uuid-1", None) in fake.calls
    assert ctx.client.post(f"/v1/admin/courier/{did}", headers=ADMIN, json={"status": "delivered"}).status_code == 409


def test_cdek_webhook_subscription(cdek):
    ctx, *_rest, fake = cdek
    assert ctx.client.post("/v1/admin/courier-webhook", headers=ADMIN).status_code == 409  # no token yet
    ctx.container.settings.courier_webhook_token = "hook-token"
    ctx.container.settings.public_api_url = "https://api.konsilier.com"
    assert ctx.client.post("/v1/admin/courier-webhook", headers=ADMIN).json() == {"ok": True, "id": "wh-1"}
    body = next(b for m, p, b in fake.calls if p == "/v2/webhooks")
    assert body == {"url": "https://api.konsilier.com/v1/webhooks/courier/cdek?token=hook-token",
                    "type": "ORDER_STATUS"}


def test_webhook_off_without_token(case):
    ctx = case[0]
    assert ctx.client.post("/v1/webhooks/courier/cdek?token=", json={}).status_code == 404


# ------------------------------------------------------------------ Alem TAT behind fake HTTP
def test_alemtat_order_and_polling(case):
    ctx, api, cid, aid = case
    calls = []
    state = {"delivered": False}

    def fake(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, dict(request.url.params),
                      json.loads(request.content) if request.content else None))
        assert request.url.params["ApiKey"] == "alem-key"
        if request.url.path.endswith("/CourierRequest/CourierRequest"):
            return httpx.Response(200, json={"RequestId": "req-1", "IsError": False})
        if request.url.path.endswith("/WayBill/regEWayBill_v2"):
            return httpx.Response(200, json={"WayBillNumber": "AT-555", "WayBillDocumentId": "doc-1", "IsError": False})
        if request.url.path.endswith("/Calc/getAmountV2"):
            return httpx.Response(200, json={"Amount": 1386})
        if request.url.path.endswith("/Find/getWayBill"):
            events = [{"DateDelivery": "2026-10-02", "TimeDelivery": "11:00", "CodeName": "Забор у отправителя"}]
            if state["delivered"]:
                events.append({"DateDelivery": "2026-10-02", "TimeDelivery": "16:30", "CodeName": "Доставлено",
                               "ToName": "Сидоров"})
            return httpx.Response(200, json={"Number": "AT-555", "IsDelivered": state["delivered"],
                                             "CurrentState": "Доставлено" if state["delivered"] else "В пути",
                                             "Shipments": [{"Number": "1", "Events": events}]})
        return httpx.Response(404)

    ctx.container.courier.provider = AlemTatProvider("alem-key", "CARD-9", "https://api.alemtat.kz/web/json",
                                                     http=httpx.Client(transport=httpx.MockTransport(fake)))
    order(api, cid, aid, window="14:00-18:00")
    job = ctx.container.courier.job
    with ctx.container.session_factory() as s:
        assert job(s, utcnow()) == 1
        s.commit()
    d = delivery(ctx)
    assert d.status == "ordered" and d.external_id == d.tracking == "AT-555" and d.meta["cost"] == "1386"
    courier_req = next(b for _, p, _, b in calls if p.endswith("/CourierRequest/CourierRequest"))
    assert courier_req["Card"] == "CARD-9" and courier_req["LocalityCode"] == "TST01"
    assert courier_req["ReadyFor"] == "14:00" and courier_req["PickUp"] == "18:00"
    bill = next(b for _, p, _, b in calls if p.endswith("/WayBill/regEWayBill_v2"))
    assert bill["RequestId"] == "req-1" and bill["ReceivingStation"] == "ST1"
    with ctx.container.session_factory() as s:
        job(s, utcnow() + timedelta(minutes=31))
        s.commit()
    assert delivery(ctx).status == "picked_up"
    state["delivered"] = True
    with ctx.container.session_factory() as s:
        job(s, utcnow() + timedelta(minutes=62))
        s.commit()
    d = delivery(ctx)
    assert d.status == "delivered" and d.signer_name == "Сидоров"
    assert api.get(f"/v1/cases/{cid}").json()["actions"][0]["submitted_via"] == "courier"
    with pytest.raises(ProviderError) as e:
        ctx.container.courier.provider.cancel("AT-555", {})
    assert e.value.code == "cancel_manual"


# ------------------------------------------------------------------ choosing the provider
def test_provider_from_settings_never_logs_keys(caplog):
    caplog.set_level(logging.WARNING)
    assert isinstance(build_provider(Settings()), ManualProvider)
    assert isinstance(build_provider(Settings(cdek_client_id="a", cdek_client_secret="b")), CdekProvider)
    assert isinstance(build_provider(Settings(alemtat_api_key="k", alemtat_card="c")), AlemTatProvider)
    assert isinstance(build_provider(Settings(alemtat_api_key="k")), ManualProvider)  # no contract card
    assert isinstance(build_provider(Settings(courier_provider="manual", cdek_client_id="a",
                                              cdek_client_secret="b")), ManualProvider)
    assert isinstance(build_provider(Settings(courier_provider="cdek", cdek_client_secret="sekret-123")),
                      ManualProvider)
    assert "sekret-123" not in caplog.text and "COURIER_PROVIDER=cdek" in caplog.text
