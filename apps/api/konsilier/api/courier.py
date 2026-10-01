"""«Доставить курьером» (konsilier/courier): the client's order and its payment, the providers' webhooks and the
operator's list in /ops.

Client (own case only):
  GET  /v1/cases/{case}/actions/{action}/courier — the form: price, cities, windows, dates, what we know already
  POST /v1/cases/{case}/actions/{action}/courier — the order → a bill (purpose "delivery"), paid like the document's
       bill (/v1/invoices/{id}/way, then …/courier/{id}/claim «Оплатить»; a Kaspi Pay push confirms it as well)
  POST /v1/cases/{case}/courier/{delivery}/claim · …/cancel (before payment)
Providers: POST /v1/webhooks/courier/{provider}?token=COURIER_WEBHOOK_TOKEN (404 while the token is empty).
Operator (X-Admin-Token, the /ops app): GET /v1/admin/courier, POST /v1/admin/courier/{delivery} (tracking number,
status, who signed), POST …/{delivery}/refresh, POST /v1/admin/courier-webhook (subscribe CDEK's webhook once).
"""

from __future__ import annotations

import hmac
import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.engine import EngineError
from ..core.models import Action, Case, Delivery, User
from ..courier.service import LIVE, CourierError
from .deps import current_user, get_container, get_session, load_case, require_admin

router = APIRouter(prefix="/v1")
admin_router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])


def _http(e: CourierError) -> HTTPException:
    return HTTPException(e.status, {"code": e.code, "message": e.extra.get("message") or e.code})


def _courier(container: Container) -> Any:
    if getattr(container, "courier", None) is None:
        raise HTTPException(404, "not found")
    return container.courier


def _load(session: Session, user: User, case_id: uuid.UUID, action_id: uuid.UUID) -> tuple[Case, Action]:
    case = load_case(case_id, session, user)
    action = session.get(Action, action_id)
    if action is None or action.case_id != case.id:
        raise HTTPException(404, "action not found")
    return case, action


def _own_delivery(session: Session, user: User, case_id: uuid.UUID, delivery_id: uuid.UUID) -> tuple[Case, Delivery]:
    case = load_case(case_id, session, user)
    d = session.get(Delivery, delivery_id)
    if d is None or d.case_id != case.id:
        raise HTTPException(404, "delivery not found")
    return case, d


def _answer(container: Container, session: Session, case: Case, action_id: Any) -> dict[str, Any]:
    from .views import case_view

    action = session.get(Action, action_id)
    return {"courier": container.courier.state(session, case, action),
            "case": case_view(container.engine, session, case)}


@router.get("/cases/{case_id}/actions/{action_id}/courier")
def courier_form(case_id: uuid.UUID, action_id: uuid.UUID, user: User = Depends(current_user),
                 session: Session = Depends(get_session), container: Container = Depends(get_container)):
    courier = _courier(container)
    case, action = _load(session, user, case_id, action_id)
    return courier.form(session, case, action, user)


class OrderIn(BaseModel):
    city: str | None = Field(default=None, max_length=32)
    date: str = Field(max_length=10)
    window: str = Field(max_length=11)
    pickup_address: str = Field(max_length=500)
    contact_name: str = Field(max_length=200)
    contact_phone: str = Field(max_length=40)
    recipient_name: str = Field(max_length=500)
    recipient_address: str = Field(max_length=500)
    recipient_phone: str | None = Field(default=None, max_length=40)
    comment: str | None = Field(default=None, max_length=500)


@router.post("/cases/{case_id}/actions/{action_id}/courier")
def courier_order(case_id: uuid.UUID, action_id: uuid.UUID, body: OrderIn, user: User = Depends(current_user),
                  session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """«Доставить курьером»: the order and its bill. The courier is ordered once the bill is paid."""
    courier = _courier(container)
    case, action = _load(session, user, case_id, action_id)
    container.engine.lock(session, case)
    try:
        courier.create(session, case, action, user, body.model_dump())
    except CourierError as e:
        raise _http(e) from e
    session.flush()
    return _answer(container, session, case, action.id)


@router.post("/cases/{case_id}/courier/{delivery_id}/claim")
def courier_claim(case_id: uuid.UUID, delivery_id: uuid.UUID, user: User = Depends(current_user),
                  session: Session = Depends(get_session), container: Container = Depends(get_container)):
    """«Оплатить» / «Я оплатил(а)» for the delivery bill — exactly as for the document's bill."""
    from .kaspi_push import match_waiting_push, push_confirms
    from .routes import _tell_desk_claimed, engine_error

    courier = _courier(container)
    case, d = _own_delivery(session, user, case_id, delivery_id)
    try:
        inv = container.engine.claim_payment(session, courier.invoice(session, d), f"user:{user.id}")
    except EngineError as e:
        raise engine_error(e) from e
    session.flush()
    if not user.is_test and match_waiting_push(session, container, inv):
        pass  # its Kaspi Pay push came first: paid now
    elif inv.status == "awaiting_confirmation" and not user.is_test and not push_confirms(container, inv):
        _tell_desk_claimed(container, inv, f"доставка курьером, дело {case.id}")
    return _answer(container, session, case, d.action_id)


@router.post("/cases/{case_id}/courier/{delivery_id}/cancel")
def courier_cancel(case_id: uuid.UUID, delivery_id: uuid.UUID, user: User = Depends(current_user),
                   session: Session = Depends(get_session), container: Container = Depends(get_container)):
    courier = _courier(container)
    case, d = _own_delivery(session, user, case_id, delivery_id)
    try:
        courier.cancel_unpaid(session, d, f"user:{user.id}")
    except CourierError as e:
        raise _http(e) from e
    session.flush()
    return _answer(container, session, case, d.action_id)


# ------------------------------------------------------------------ providers' webhooks
@router.post("/webhooks/courier/{provider}")
async def courier_webhook(provider: str, request: Request, token: str = "",
                          container: Container = Depends(get_container)) -> dict[str, Any]:
    """A provider says an order changed. CDEK signs nothing, so the URL carries our secret token and the status is
    then read from the provider's API — never from the body."""
    secret = container.settings.courier_webhook_token
    if not secret or getattr(container, "courier", None) is None:
        raise HTTPException(404, "not found")
    if not hmac.compare_digest(token.encode(), secret.encode()):
        raise HTTPException(401, "bad token")
    raw = await request.body()
    try:
        payload = json.loads(raw[:65536] or b"{}")
    except ValueError as e:
        raise HTTPException(422, "bad payload") from e

    def handle() -> dict[str, Any]:
        with container.session_factory() as session:
            out = container.courier.webhook(session, provider, payload)
            session.commit()
            return out

    return await run_in_threadpool(handle)


# ------------------------------------------------------------------ the operator (/ops)
@admin_router.get("/courier")
def ops_list(all: bool = False, session: Session = Depends(get_session),
             container: Container = Depends(get_container)) -> dict[str, Any]:
    """Deliveries for the duty operator: those still on their way (``all``: the last 200 of every status)."""
    courier = _courier(container)
    q = select(Delivery).order_by(Delivery.created_at.desc()).limit(200)
    if not all:
        q = q.where(Delivery.status.in_(LIVE))
    return {"provider": courier.provider.name, "has_api": courier.provider.has_api,
            "webhook": bool(container.settings.courier_webhook_token),
            "items": [courier.view(session, d, ops=True) for d in session.scalars(q).all()]}


class OpsUpdate(BaseModel):
    status: Literal["ordered", "picked_up", "in_transit", "delivered", "refused", "returned", "cancelled"] | None = None
    tracking: str | None = Field(default=None, max_length=100)
    signer_name: str | None = Field(default=None, max_length=200)
    at: datetime | None = None  # when it happened (the courier's time); now when empty
    note: str | None = Field(default=None, max_length=500)
    operator: str | None = Field(default=None, max_length=100)


@admin_router.post("/courier/{delivery_id}")
def ops_update(delivery_id: uuid.UUID, body: OpsUpdate, session: Session = Depends(get_session),
               container: Container = Depends(get_container)) -> dict[str, Any]:
    courier = _courier(container)
    d = session.get(Delivery, delivery_id)
    if d is None:
        raise HTTPException(404, "delivery not found")
    try:
        courier.ops_update(session, d, body.operator or "owner", status=body.status, tracking=body.tracking,
                           signer_name=(body.signer_name or "").strip() or None, at=body.at, note=body.note)
    except CourierError as e:
        raise _http(e) from e
    session.flush()
    return courier.view(session, d, ops=True)


@admin_router.post("/courier/{delivery_id}/refresh")
def ops_refresh(delivery_id: uuid.UUID, session: Session = Depends(get_session),
                container: Container = Depends(get_container)) -> dict[str, Any]:
    """Ask the provider now (or retry the order of a paid delivery)."""
    courier = _courier(container)
    d = session.get(Delivery, delivery_id)
    if d is None:
        raise HTTPException(404, "delivery not found")
    if d.status == "paid" and not d.external_id:
        courier.place(session, d)
    else:
        courier.refresh(session, d, "ops")
    session.flush()
    return courier.view(session, d, ops=True)


@admin_router.post("/courier-webhook")
def ops_subscribe(container: Container = Depends(get_container)) -> dict[str, Any]:
    """Subscribe the provider's order-status webhook to our URL (CDEK; once, after the keys are set)."""
    from ..courier.providers import ProviderError

    courier = _courier(container)
    token = container.settings.courier_webhook_token
    subscribe = getattr(courier.provider, "subscribe", None)
    if not token or subscribe is None:
        raise HTTPException(409, {"code": "webhook_unavailable", "message": "COURIER_WEBHOOK_TOKEN and CDEK keys"})
    url = f"{container.settings.public_api_url.rstrip('/')}/v1/webhooks/courier/{courier.provider.name}?token={token}"
    try:
        sub = subscribe(url)
    except ProviderError as e:
        raise HTTPException(502, {"code": e.code, "message": e.detail or e.code}) from e
    return {"ok": True, "id": sub}
