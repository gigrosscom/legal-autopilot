"""Web push subscriptions: the site or the installed app turns notifications on for this device.

GET /v1/push/key is public (the browser needs the key before it subscribes); subscribing and unsubscribing act for
the bearer of the token. A device belongs to one person: subscribing again from another account moves it there.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.models import PushSubscription, User
from ..core.push import allowed_endpoint
from .deps import current_user, get_container, get_session

router = APIRouter(prefix="/v1/push")


def _key(container: Container) -> str:
    key = container.settings.vapid_public_key
    if not key or container.push_sender is None:
        raise HTTPException(404, {"code": "push_off", "message": "push notifications are not configured"})
    return key


@router.get("/key")
def push_key(container: Container = Depends(get_container)) -> dict[str, str]:
    """The VAPID public key (applicationServerKey); 404 while push is not configured."""
    return {"key": _key(container)}


class Keys(BaseModel):
    p256dh: str = Field(min_length=16, max_length=255)
    auth: str = Field(min_length=8, max_length=64)


class SubscribeIn(BaseModel):
    """The browser's PushSubscription.toJSON(), plus its user agent to tell devices apart."""

    endpoint: str = Field(min_length=10, max_length=1024)
    keys: Keys
    user_agent: str | None = Field(default=None, max_length=1000)


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1024)


@router.post("/subscribe")
def subscribe(body: SubscribeIn, user: User = Depends(current_user), session: Session = Depends(get_session),
              container: Container = Depends(get_container)) -> dict[str, Any]:
    _key(container)
    if not allowed_endpoint(body.endpoint):
        raise HTTPException(422, {"code": "bad_endpoint", "message": "not a browser push service"})
    sub = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint, user_id=user.id)
        session.add(sub)
    sub.user_id = user.id
    sub.p256dh, sub.auth = body.keys.p256dh, body.keys.auth
    sub.user_agent = (body.user_agent or "")[:300] or None
    sub.failed_count = 0
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeIn, user: User = Depends(current_user),
                session: Session = Depends(get_session)) -> dict[str, Any]:
    """Forgets this device; only the person's own subscription is touched."""
    session.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint,
                                                   PushSubscription.user_id == user.id))
    return {"ok": True}
