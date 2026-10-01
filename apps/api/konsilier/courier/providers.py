"""Courier services behind one interface: ``quote`` · ``create_order`` · ``status`` · ``cancel`` (+ ``webhook_ref``).

* ``manual`` — no API: the order waits in /ops, the duty operator orders the courier by phone or in the service's
  cabinet and enters the tracking number and the statuses (konsilier/api/courier.py, admin endpoints).
* ``cdek`` — СДЭК API v2 (https://apidoc.cdek.ru; the same API serves cdek.kz — the contract is signed with the
  country's СДЭК company): OAuth client_credentials (``POST /v2/oauth/token``), tariff
  (``POST /v2/calculator/tariff``), order (``POST /v2/orders``, ``GET /v2/orders/{uuid}``,
  ``DELETE /v2/orders/{uuid}``), the courier pickup (``POST /v2/intakes``), the «Реверс» service (code REVERSE:
  the signed copy goes back to the sender) and webhooks (``POST /v2/webhooks`` type ORDER_STATUS). CDEK webhooks carry no signature: a webhook only names the order and
  its status is then read from the API (``status``), never taken from the webhook body.
* ``alemtat`` — Алем ТАТ (https://api.alemtat.kz/web/, API key from the sales manager under a contract): courier
  request (``CourierRequest/CourierRequest``), e-waybill (``WayBill/regEWayBill_v2``), tracking
  (``Find/getWayBill``), tariff (``Calc/getAmountV2``). No cancel and no webhooks in its API → polling, and cancel
  is done by the operator by phone. The return of the signed copy has no documented service code — TODO with the
  manager; until then the operator marks «возвращено» in /ops.

Statuses of every provider are mapped to ours: ordered → picked_up → in_transit → delivered | refused → returned
(and cancelled). Secrets are taken from the settings only and never logged or put into an error text.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

ORDERED, PICKED_UP, IN_TRANSIT, DELIVERED, REFUSED, RETURNED, CANCELLED = (
    "ordered", "picked_up", "in_transit", "delivered", "refused", "returned", "cancelled")


class ProviderError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail[:250]


@dataclass
class OrderRequest:
    """Everything a courier service needs for one delivery (filled from a ``Delivery`` row and the pack's city)."""
    reference: str  # our delivery id — the order number on the service's side
    city: dict[str, Any]  # the pack's city (codes per provider)
    pickup_address: str
    pickup_date: date
    pickup_from: str  # HH:MM
    pickup_to: str
    sender_name: str
    sender_phone: str
    recipient_name: str
    recipient_address: str
    recipient_phone: str | None = None
    comment: str = ""
    config: dict[str, Any] = field(default_factory=dict)  # the pack's settings of this provider (tariff, services…)


@dataclass
class Quote:
    amount: Decimal | None
    currency: str | None = None
    days_min: int | None = None
    days_max: int | None = None


@dataclass
class Placed:
    external_id: str
    tracking: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    status: str  # one of ours
    at: datetime | None = None
    code: str | None = None  # the provider's status code / event name
    text: str | None = None
    signer: str | None = None


@dataclass
class Snapshot:
    """What the provider says about an order now: its events in time order (only those mapped to our statuses),
    the tracking number, provider data to keep (e.g. the return order's id)."""
    events: list[Event]
    tracking: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class CourierProvider(Protocol):
    name: str
    has_api: bool

    def quote(self, req: OrderRequest) -> Quote: ...

    def create_order(self, req: OrderRequest) -> Placed: ...

    def status(self, external_id: str, meta: dict[str, Any]) -> Snapshot: ...

    def cancel(self, external_id: str, meta: dict[str, Any]) -> None: ...

    def webhook_ref(self, payload: Any) -> str | None: ...


# ------------------------------------------------------------------ manual
class ManualProvider:
    """No API: the operator does it in /ops."""
    name = "manual"
    has_api = False

    def quote(self, req: OrderRequest) -> Quote:
        return Quote(None)

    def create_order(self, req: OrderRequest) -> Placed:
        raise ProviderError("manual")

    def status(self, external_id: str, meta: dict[str, Any]) -> Snapshot:
        return Snapshot([])

    def cancel(self, external_id: str, meta: dict[str, Any]) -> None:
        return None

    def webhook_ref(self, payload: Any) -> str | None:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":" and s[-4:].isdigit():  # +0600 → +06:00
        s = f"{s[:-2]}:{s[-2:]}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _error_text(r: httpx.Response) -> str:
    """The service's error message without anything we sent (no keys)."""
    try:
        data = r.json()
    except ValueError:
        return f"HTTP {r.status_code}"
    msgs: list[str] = []
    if isinstance(data, dict):
        for req in data.get("requests") or []:
            for e in (req or {}).get("errors") or []:
                msgs.append(str(e.get("message") or e.get("code") or ""))
        for e in data.get("errors") or []:
            if isinstance(e, dict):
                msgs.append(str(e.get("message") or e.get("code") or ""))
        if data.get("Message"):
            msgs.append(str(data["Message"]))
        if data.get("error_description"):
            msgs.append(str(data["error_description"]))
    return f"HTTP {r.status_code}" + (f": {'; '.join(m for m in msgs if m)}" if msgs else "")


# ------------------------------------------------------------------ СДЭК
# CDEK order status codes → ours. Unknown codes are kept in the log only. TODO(test account): check the codes of a
# door-to-door order in the pilot city and of the reverse order on api.edu.cdek.ru before going live.
CDEK_STATUS = {
    "CREATED": ORDERED, "ACCEPTED": ORDERED,
    "RECEIVED_AT_SHIPMENT_WAREHOUSE": PICKED_UP, "READY_FOR_SHIPMENT_IN_SENDER_CITY": PICKED_UP,
    "TAKEN_BY_TRANSPORTER_FROM_SENDER_CITY": IN_TRANSIT, "SENT_TO_TRANSIT_CITY": IN_TRANSIT,
    "ACCEPTED_IN_TRANSIT_CITY": IN_TRANSIT, "ACCEPTED_AT_TRANSIT_WAREHOUSE": IN_TRANSIT,
    "READY_FOR_SHIPMENT_IN_TRANSIT_CITY": IN_TRANSIT, "TAKEN_BY_TRANSPORTER_FROM_TRANSIT_CITY": IN_TRANSIT,
    "SENT_TO_RECIPIENT_CITY": IN_TRANSIT, "ACCEPTED_IN_RECIPIENT_CITY": IN_TRANSIT,
    "ACCEPTED_AT_RECIPIENT_CITY_WAREHOUSE": IN_TRANSIT, "ACCEPTED_AT_PICK_UP_POINT": IN_TRANSIT,
    "TAKEN_BY_COURIER": IN_TRANSIT, "RETURNED_TO_RECIPIENT_CITY_WAREHOUSE": IN_TRANSIT,
    "DELIVERED": DELIVERED, "NOT_DELIVERED": REFUSED, "REMOVED": CANCELLED,
}


class CdekProvider:
    name = "cdek"
    has_api = True

    def __init__(self, client_id: str, client_secret: str, base_url: str, http: httpx.Client | None = None):
        self._id, self._secret = client_id, client_secret
        self.base = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=20)
        self._token: str | None = None
        self._token_until = 0.0

    # -- transport
    def _auth(self) -> str:
        if self._token and time.monotonic() < self._token_until:
            return self._token
        try:
            r = self.http.post(f"{self.base}/v2/oauth/token", data={
                "grant_type": "client_credentials", "client_id": self._id, "client_secret": self._secret})
        except httpx.HTTPError as e:
            raise ProviderError("unreachable", e.__class__.__name__) from e
        if r.status_code != 200:
            raise ProviderError("auth_failed", f"HTTP {r.status_code}")
        data = r.json()
        self._token = str(data["access_token"])
        self._token_until = time.monotonic() + max(60, int(data.get("expires_in") or 3600) - 60)
        return self._token

    def _call(self, method: str, path: str, json: Any = None) -> dict[str, Any]:
        for attempt in (1, 2):
            try:
                r = self.http.request(method, f"{self.base}{path}", json=json,
                                      headers={"Authorization": f"Bearer {self._auth()}"})
            except httpx.HTTPError as e:
                raise ProviderError("unreachable", e.__class__.__name__) from e
            if r.status_code == 401 and attempt == 1:  # the token expired early: once more with a new one
                self._token = None
                continue
            if r.status_code >= 400:
                raise ProviderError("rejected", _error_text(r))
            try:
                return r.json() if r.content else {}
            except ValueError as e:
                raise ProviderError("bad_answer", f"HTTP {r.status_code}") from e
        raise ProviderError("auth_failed")

    # -- the order
    @staticmethod
    def _locations(req: OrderRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        code = req.city.get("cdek_city_code")
        frm: dict[str, Any] = {"address": req.pickup_address}
        to: dict[str, Any] = {"address": req.recipient_address}
        if code:
            frm["code"] = to["code"] = int(code)
        return frm, to

    @staticmethod
    def _package(req: OrderRequest) -> dict[str, Any]:
        p = req.config.get("package") or {}
        return {"weight": int(p.get("weight", 300)), "length": int(p.get("length", 32)),
                "width": int(p.get("width", 23)), "height": int(p.get("height", 2))}

    def _services(self, req: OrderRequest) -> list[dict[str, Any]]:
        return [{"code": str(c)} for c in req.config.get("services") or []]

    def quote(self, req: OrderRequest) -> Quote:
        frm, to = self._locations(req)
        body = {"type": 2, "tariff_code": int(req.config.get("tariff_code") or 480), "from_location": frm,
                "to_location": to, "packages": [self._package(req)], "services": self._services(req)}
        if req.config.get("currency"):
            body["currency"] = int(req.config["currency"])
        data = self._call("POST", "/v2/calculator/tariff", body)
        total = data.get("total_sum", data.get("delivery_sum"))
        return Quote(Decimal(str(total)) if total is not None else None, data.get("currency"),
                     data.get("period_min"), data.get("period_max"))

    def create_order(self, req: OrderRequest) -> Placed:
        if not req.recipient_phone:
            raise ProviderError("recipient_phone_required")
        frm, to = self._locations(req)
        pkg = {"number": "1", "comment": "Документы", **self._package(req)}
        body = {
            "type": 2, "number": req.reference, "tariff_code": int(req.config.get("tariff_code") or 480),
            "comment": (req.comment or "Документы: вручить под подпись на втором экземпляре")[:255],
            "sender": {"name": req.sender_name[:255], "phones": [{"number": req.sender_phone}]},
            "recipient": {"name": req.recipient_name[:255], "company": req.recipient_name[:255],
                          "phones": [{"number": req.recipient_phone}]},
            "from_location": frm, "to_location": to, "packages": [pkg], "services": self._services(req),
        }
        data = self._call("POST", "/v2/orders", body)
        uuid_ = ((data.get("entity") or {}).get("uuid"))
        states = [(q or {}).get("state") for q in data.get("requests") or []]
        if not uuid_ or "INVALID" in states:
            raise ProviderError("rejected", _error_text(httpx.Response(400, json=data)))
        meta: dict[str, Any] = {}
        try:  # the courier's visit to the sender: a separate request in CDEK («заявка на вызов курьера»)
            intake = self._call("POST", "/v2/intakes", {
                "order_uuid": uuid_, "intake_date": req.pickup_date.isoformat(),
                "intake_time_from": req.pickup_from, "intake_time_to": req.pickup_to,
                "name": "Документы", "need_call": True, "comment": req.comment[:255] if req.comment else None,
                "sender": {"name": req.sender_name[:255], "phones": [{"number": req.sender_phone}]},
                "from_location": frm})
            meta["intake_uuid"] = (intake.get("entity") or {}).get("uuid")
        except ProviderError as e:  # the order stands; the operator orders the pickup by phone if needed
            meta["intake_error"] = e.detail or e.code
        return Placed(external_id=str(uuid_), tracking=None, meta=meta)

    def _snapshot(self, uuid_: str) -> tuple[dict[str, Any], list[Event]]:
        data = self._call("GET", f"/v2/orders/{uuid_}")
        entity = data.get("entity") or {}
        events = []
        for st in entity.get("statuses") or []:
            ours = CDEK_STATUS.get(str(st.get("code")))
            if ours:
                events.append(Event(ours, _parse_dt(st.get("date_time")), str(st.get("code")), st.get("name")))
        events.sort(key=lambda e: e.at or datetime.min.replace(tzinfo=timezone.utc))
        return entity, events

    def status(self, external_id: str, meta: dict[str, Any]) -> Snapshot:
        entity, events = self._snapshot(external_id)
        signer = ((entity.get("delivery_detail") or {}).get("recipient_name")
                  or (entity.get("delivery_detail") or {}).get("delivery_recipient_name"))
        for e in events:
            if e.status == DELIVERED and signer:
                e.signer = str(signer)[:200]
        out = Snapshot(events, tracking=entity.get("cdek_number"))
        # «Реверс»: the signed copy travels back as a related order; its delivery to the sender = returned.
        # TODO(test account): confirm the related entity type name of the reverse order.
        back = meta.get("return_uuid") or next(
            (r.get("uuid") for r in entity.get("related_entities") or []
             if str(r.get("type", "")).lower() in ("reverse_order", "return_order") and r.get("uuid")), None)
        if back:
            out.meta["return_uuid"] = back
            _, back_events = self._snapshot(str(back))
            for e in back_events:
                if e.status == DELIVERED:
                    out.events.append(Event(RETURNED, e.at, f"return:{e.code}", e.text))
        return out

    def cancel(self, external_id: str, meta: dict[str, Any]) -> None:
        self._call("DELETE", f"/v2/orders/{external_id}")

    def webhook_ref(self, payload: Any) -> str | None:
        """ORDER_STATUS: {"type": "ORDER_STATUS", "uuid": "<order uuid>", "attributes": {"code": …, "is_return": …}}.
        Only the order id is used; the status is read from the API."""
        if not isinstance(payload, dict) or payload.get("type") != "ORDER_STATUS":
            return None
        return str(payload.get("uuid") or "") or None

    def subscribe(self, url: str) -> str | None:
        """Register our webhook for order statuses (once, by the owner from /ops)."""
        data = self._call("POST", "/v2/webhooks", {"url": url, "type": "ORDER_STATUS"})
        return (data.get("entity") or {}).get("uuid")


# ------------------------------------------------------------------ Алем ТАТ
ALEMTAT_READY = ("12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00")


class AlemTatProvider:
    name = "alemtat"
    has_api = True

    def __init__(self, api_key: str, card: str, base_url: str, http: httpx.Client | None = None):
        self._key, self.card = api_key, card
        self.base = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=20)

    def _call(self, method: str, path: str, json: dict[str, Any] | None = None,
              params: dict[str, Any] | None = None) -> Any:
        params = {**(params or {}), "ApiKey": self._key}
        body = {**json, "ApiKey": self._key} if json is not None else None
        try:
            r = self.http.request(method, f"{self.base}/{path}", params=params, json=body)
        except httpx.HTTPError as e:
            raise ProviderError("unreachable", e.__class__.__name__) from e
        if r.status_code >= 400:
            raise ProviderError("rejected", _error_text(r))
        try:
            data = r.json()
        except ValueError as e:
            raise ProviderError("bad_answer", f"HTTP {r.status_code}") from e
        if isinstance(data, dict) and data.get("IsError"):
            raise ProviderError("rejected", f"{data.get('ErrorCode')}: {data.get('Message') or ''}")
        return data

    def _city(self, req: OrderRequest) -> tuple[str, str]:
        loc, station = str(req.city.get("alemtat_locality") or ""), str(req.city.get("alemtat_station") or "")
        if not loc or not station:
            raise ProviderError("city_not_configured", "alemtat_locality / alemtat_station in courier.yaml")
        return loc, station

    def quote(self, req: OrderRequest) -> Quote:
        loc, _ = self._city(req)
        country = str(req.config.get("country") or "")
        data = self._call("POST", "Calc/getAmountV2", {
            "FromCountryCode": country, "FromLocalCode": loc, "ToCountryCode": country, "ToLocalCode": loc,
            "ServiceLocalCode": str(req.config.get("service") or "E"), "Weight": str(req.config.get("weight") or 0.3)})
        # TODO(contract): the answer's fields are not in the public help page; read the usual names
        amount = None
        if isinstance(data, dict):
            amount = next((data[k] for k in ("Amount", "AmountWithVAT", "Total", "Sum") if data.get(k) is not None),
                          None)
        return Quote(Decimal(str(amount)) if amount is not None else None, req.config.get("currency_code"))

    def create_order(self, req: OrderRequest) -> Placed:
        loc, station = self._city(req)
        ready = req.pickup_from if req.pickup_from in ALEMTAT_READY else "готово"
        until = min((t for t in ALEMTAT_READY if t >= req.pickup_to), default="18:00")
        service = str(req.config.get("service") or "E")
        courier = self._call("POST", "CourierRequest/CourierRequest", {
            "Date": req.pickup_date.isoformat(), "Card": self.card, "SenderName": req.sender_name[:128],
            "LocalityCode": loc, "AddressDetail": req.pickup_address[:512], "ContactName": req.sender_name[:128],
            "Phone": req.sender_phone[:32], "ReadyFor": ready, "PickUp": until, "Service": service,
            "Note": (req.comment or "Документы: 2 экземпляра, вручить под подпись на втором")[:500]})
        request_id = courier.get("RequestId") if isinstance(courier, dict) else None
        if not request_id:
            raise ProviderError("rejected", "no RequestId")
        bill = self._call("POST", "WayBill/regEWayBill_v2", {
            "RequestId": request_id, "Card": self.card, "ReceivingStation": station,
            "Recipient": {"Company": req.recipient_name[:128], "Contact": req.recipient_name[:128],
                          "Tel": req.recipient_phone or "", "LocalityCode": loc,
                          "AddressDetail": req.recipient_address[:512]},
            "Service": service, "Place": 1, "Weight": float(req.config.get("weight") or 0.3), "DeclareAmount": 0,
            "Content": "Документы"})
        number = bill.get("WayBillNumber") if isinstance(bill, dict) else None
        if not number:
            raise ProviderError("rejected", "no WayBillNumber")
        return Placed(external_id=str(number), tracking=str(number),
                      meta={"request_id": str(request_id), "document_id": str(bill.get("WayBillDocumentId") or "")})

    def status(self, external_id: str, meta: dict[str, Any]) -> Snapshot:
        data = self._call("GET", "Find/getWayBill", params={"Number": external_id})
        if not isinstance(data, dict):
            return Snapshot([])
        raw = [e for s in data.get("Shipments") or [] for e in (s or {}).get("Events") or []]
        events: list[Event] = []
        for i, e in enumerate(raw):
            at = _parse_dt(f"{e.get('DateDelivery') or ''}T{e.get('TimeDelivery') or '00:00'}") \
                if e.get("DateDelivery") else None
            name = str(e.get("CodeName") or "")
            # TODO(contract): map by Find/getEventTypes (LocalCode, Kind 2 = завершение); words until then
            low = name.lower()
            status = REFUSED if "отказ" in low else PICKED_UP if i == 0 else IN_TRANSIT
            events.append(Event(status, at, name or None, e.get("Comment")))
        if data.get("IsDelivered"):
            signer = next((str(e.get("ToName")) for e in reversed(raw) if e.get("ToName")), None)
            at = events[-1].at if events else None
            events.append(Event(DELIVERED, at, "IsDelivered", data.get("CurrentState"), signer))
        return Snapshot(events, tracking=str(data.get("Number") or external_id))

    def cancel(self, external_id: str, meta: dict[str, Any]) -> None:
        raise ProviderError("cancel_manual", "Алем ТАТ: отмена — звонком менеджеру (в API нет отмены)")

    def webhook_ref(self, payload: Any) -> str | None:
        return None  # no webhooks: polling


def build_provider(settings: Any, http: httpx.Client | None = None) -> CourierProvider:
    """COURIER_PROVIDER: auto → cdek with its keys, else alemtat with its key and contract card, else manual. A
    provider named without its keys falls back to manual (logged, without the values)."""
    want = (settings.courier_provider or "auto").strip().lower()
    cdek_ok = bool(settings.cdek_client_id and settings.cdek_client_secret)
    alem_ok = bool(settings.alemtat_api_key and settings.alemtat_card)
    if want in ("auto", "cdek") and cdek_ok:
        return CdekProvider(settings.cdek_client_id, settings.cdek_client_secret, settings.cdek_base_url, http)
    if want in ("auto", "alemtat") and alem_ok:
        return AlemTatProvider(settings.alemtat_api_key, settings.alemtat_card, settings.alemtat_base_url, http)
    if want not in ("auto", "manual"):
        log.warning("COURIER_PROVIDER=%s without its keys: courier orders go to /ops (manual)", want)
    return ManualProvider()
