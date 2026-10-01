"""Production smoke checks (deploy/smoke.py) run the whole path as a marked test user: a case, documents, the
bill, its confirmation, the document. Test users stay out of the metrics and the operations centre and never
notify the team. Closed unless SMOKE_TOKEN is set; the token only ever touches test users' own data."""
from __future__ import annotations

import hmac
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..container import Container
from ..core.engine import EngineError
from ..core.models import Case, Invoice, User
from .background import after_commit
from .deps import current_user, get_container, get_session
from .views import case_view

router = APIRouter(prefix="/v1/smoke")


def smoke(x_smoke_token: str | None = Header(default=None), container: Container = Depends(get_container)) -> None:
    expected = container.settings.smoke_token
    if not expected or not x_smoke_token or not hmac.compare_digest(expected, x_smoke_token):
        raise HTTPException(404, "not found")


@router.post("/user", dependencies=[Depends(smoke)])
def test_user(session: Session = Depends(get_session)) -> dict[str, Any]:
    user = User(language="ru", is_test=True, source="smoke")  # the country comes with the case
    session.add(user)
    session.flush()
    return {"token": user.api_token, "user_id": str(user.id)}


class SmokeEmail(BaseModel):
    email: str = Field(max_length=200)


@router.post("/email", dependencies=[Depends(smoke)])
def confirm_test_email(body: SmokeEmail, user: User = Depends(current_user), session: Session = Depends(get_session),
                       container: Container = Depends(get_container)) -> dict[str, Any]:
    """A test user's e-mail as if confirmed by a code — for the sending wizard's check (Reply-To and the copy). Only
    Resend's test sinks (…@resend.dev) are accepted, so no real mailbox can be attached this way."""
    email = body.email.strip().lower()
    if not user.is_test or not email.endswith("@resend.dev"):
        raise HTTPException(404, "not found")
    owner = container.identities.link_or_login(session, user, "email", email, email)
    session.flush()
    # QA 01.10: an address already taken signs into that account — the caller switches to its token
    return {"email": email, "token": owner.api_token, "user_id": str(owner.id)}


@router.post("/cases/{case_id}/payment/confirm", dependencies=[Depends(smoke)])
def confirm_test_payment(case_id: uuid.UUID, session: Session = Depends(get_session),
                         container: Container = Depends(get_container)) -> dict[str, Any]:
    """The desk's «Оплата получена», for a test user's own bill only."""
    case = session.get(Case, case_id)
    owner = session.get(User, case.owner_id) if case is not None else None
    if case is None or owner is None or not owner.is_test:
        raise HTTPException(404, "not found")
    inv = container.engine.invoice_of(session, case)
    if inv is None:
        raise HTTPException(409, {"code": "no_open_invoice", "message": "no open invoice"})
    try:
        container.engine.decide_payment(session, inv, "smoke", True, "smoke check")
    except EngineError as e:
        raise HTTPException(409, {"code": e.code, "message": e.code}) from e
    invoice_id = inv.id

    def prepare(s: Session) -> None:  # as after the desk's confirmation: the document is made at once
        action = container.engine.prepare_after_payment(s, s.get(Invoice, invoice_id))
        if action is not None and not action.pdf_key and action.docx_key:
            s.commit()
            container.engine.ensure_pdf(s, action)
    after_commit(session, container, prepare, "smoke-paid-document")
    session.flush()
    return {"case": case_view(container.engine, session, case)}
