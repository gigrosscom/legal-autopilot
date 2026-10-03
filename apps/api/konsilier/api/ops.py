"""Operations centre: two desks, each opened by its operators' verified e-mail (sign in with an e-mail code).

- lawyers desk: every application of an advocate, legal consultant or human-rights organisation;
- clients desk: every client question, complaint or suggestion, every client request to a lawyer, and document
  payments by transfer waiting for confirmation.

Which e-mails operate which desk: settings OPS_LAWYERS_EMAILS / OPS_CLIENTS_EMAILS (konsilier/team.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..container import Container
from ..core.engine import EngineError
from ..core.models import (AuditLog, Case, Invoice, LawyerApplication, LawyerRequest, Notification, SupportTicket,
                           TicketMessage, User)
from ..team import Desk, desks_of
from .background import after_commit
from .deps import current_user, get_container, get_session
from .support import messages_of, ticket_view

router = APIRouter(prefix="/v1/ops")


def _test_users():
    """Test accounts' bills (production smoke checks) never reach the desk."""
    return select(User.id).where(User.is_test.is_(True))
log = logging.getLogger(__name__)


def operator(desk: Desk):
    def dep(user: User = Depends(current_user), container: Container = Depends(get_container)) -> User:
        if desk not in desks_of(container.settings, user.email):
            raise HTTPException(403, {"code": "not_operator", "message": "not_operator"})
        return user
    return dep


def _tell(session: Session, container: Container, user_id: Any, email: str | None, subject: str, text: str) -> None:
    """Reach the person: site inbox (if they have an account here) and e-mail (if they left one)."""
    if user_id:
        session.add(Notification(user_id=user_id, channel="web", kind="desk_message", text=text, delivered=True))
    if email and "@" in email and container.email_sender is not None:
        try:
            container.email_sender.send(email, subject, text)
        except Exception:  # noqa: BLE001
            log.warning("desk e-mail to a client failed", exc_info=True)


@router.get("/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_session),
       container: Container = Depends(get_container)) -> dict[str, Any]:
    desks = desks_of(container.settings, user.email)
    counts: dict[str, int] = {}
    if "lawyers" in desks:
        counts["lawyers"] = session.scalar(select(func.count()).select_from(LawyerApplication)
                                           .where(LawyerApplication.status == "new")) or 0
    if "clients" in desks:
        counts["clients"] = (session.scalar(select(func.count()).select_from(SupportTicket)
                                            .where(SupportTicket.status == "new")) or 0) + \
                            (session.scalar(select(func.count()).select_from(LawyerRequest)
                                            .where(LawyerRequest.status == "new")) or 0) + \
                            (session.scalar(select(func.count()).select_from(Invoice)
                                            .where(Invoice.status == "awaiting_confirmation",
                                                   Invoice.user_id.not_in(_test_users()))) or 0)
    return {"email": user.email, "desks": desks, "new": counts}


# ------------------------------------------------------------------ lawyers desk
# Official registries for the operator's manual check (opened and checked 28.09.2026). «Заң көмегі» is the
# Ministry of Justice portal with the search of advocates and legal consultants; e-licensing holds advocates'
# licences. Legal consultants' chambers also keep their own member registries.
REGISTRIES: dict[str, list[dict[str, str]]] = {
    "advocate": [
        {"title": "«Заң көмегі» (Минюст РК): поиск адвоката", "url": "https://eup.adilet.gov.kz/#/lawyers/advocate"},
        {"title": "Е-лицензирование: реестр лицензий (адвокатская деятельность)",
         "url": "https://elicense.kz/Licenses/Index?documentType=License"},
        {"title": "Республиканская коллегия адвокатов", "url": "https://advokatura.kz/ru/"},
    ],
    "legal_consultant": [
        {"title": "«Заң көмегі» (Минюст РК): поиск юридического консультанта",
         "url": "https://eup.adilet.gov.kz/#/lawyers/consultant"},
    ],
    "human_rights": [],
}


def _checks(a: LawyerApplication) -> dict[str, Any]:
    """What the form rules say about this application now (older applications were accepted without them)."""
    from ..identity import form_rules as R

    phone, phone_err = R.normalize_kz_phone(a.phone or a.contact)
    return {
        "full_name": R.check_full_name(a.full_name),
        "phone": phone_err, "phone_normalized": phone,
        "license_number": R.check_license(a.license_number, a.kind),
        "city": R.check_city(a.city),
        "kind": None if a.kind in R.LAWYER_KINDS else "required",
        "ecp": None if a.iin_hash else "missing",
    }


def application_view(a: LawyerApplication) -> dict[str, Any]:
    return {"id": a.id, "created_at": a.created_at.isoformat(), "full_name": a.full_name, "kind": a.kind,
            "organization": a.organization, "license_number": a.license_number, "city": a.city,
            "specializations": a.specializations, "contact": a.contact, "phone": a.phone, "email": a.email,
            "message": a.message, "wants_expert": a.wants_expert, "status": a.status, "ecp_verified": bool(a.iin_hash),
            "ecp_name": a.ecp_name, "note": a.desk_note, "reject_reason": a.reject_reason,
            "checks": _checks(a), "registries": REGISTRIES.get(a.kind, [])}


@router.get("/lawyers/applications")
def applications(status: str | None = None, session: Session = Depends(get_session),
                 _: User = Depends(operator("lawyers"))) -> list[dict[str, Any]]:
    q = select(LawyerApplication).order_by(LawyerApplication.id.desc()).limit(500)
    if status:
        q = q.where(LawyerApplication.status == status)
    return [application_view(a) for a in session.scalars(q).all()]


class AppUpdate(BaseModel):
    status: Literal["new", "verified", "rejected"] | None = None
    note: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=2000)  # required to reject: the lawyer is told it


@router.post("/lawyers/applications/{app_id}")
def update_application(app_id: int, body: AppUpdate, session: Session = Depends(get_session),
                       container: Container = Depends(get_container),
                       _: User = Depends(operator("lawyers"))) -> dict[str, Any]:
    a = session.get(LawyerApplication, app_id)
    if a is None:
        raise HTTPException(404, "application not found")
    if body.note is not None:
        a.desk_note = body.note
    if body.status and body.status != a.status:
        if body.status == "verified" and not a.iin_hash:
            # who signs papers with clients is known only from the ЭЦП certificate
            raise HTTPException(409, {"code": "ecp_required", "message": "ecp_required"})
        reason = (body.reason or "").strip()
        if body.status == "rejected" and len(reason) < 5:
            raise HTTPException(422, {"code": "reason_required", "message": "reason_required",
                                      "fields": {"reason": "required"}})
        a.status = body.status
        a.reject_reason = reason if body.status == "rejected" else None
        email = a.email or (a.contact if "@" in (a.contact or "") else None)
        if body.status == "verified":
            _tell(session, container, a.user_id, email, "Konsilier AI: заявка юриста подтверждена",
                  f"{a.full_name}, ваш статус проверен, доступ к кабинету юриста открыт, профиль появился в каталоге "
                  f"юристов: https://konsilier.com/lawyer")
        elif body.status == "rejected":
            _tell(session, container, a.user_id, email, "Konsilier AI: заявка юриста",
                  f"{a.full_name}, подтвердить статус по заявке не удалось.\nПричина: {reason}\n\n"
                  f"Исправьте данные и подайте заявку заново на https://konsilier.com/for-lawyers или ответьте на это "
                  f"письмо (info@konsilier.com).")
    return application_view(a)


# ------------------------------------------------------------------ clients desk
@router.get("/clients/tickets")
def tickets(status: str | None = None, session: Session = Depends(get_session),
            _: User = Depends(operator("clients"))) -> list[dict[str, Any]]:
    q = select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(500)
    if status:
        q = q.where(SupportTicket.status == status)
    rows = session.scalars(q).all()
    msgs = messages_of(session, [t.id for t in rows])
    return [ticket_view(t, msgs[t.id]) for t in rows]


# The desk's reply reaches the client in the language the ticket was written in (SupportTicket.language).
REPLY_MAIL = {
    "ru": ("Konsilier AI: ответ на обращение №{n}",
           "{text}\n\nОбращение №{n}. Ответить можно на странице https://konsilier.com/support"),
    "kk": ("Konsilier AI: №{n} өтінішке жауап",
           "{text}\n\n№{n} өтініш. Жауап беруге болады: https://konsilier.com/support"),
    "en": ("Konsilier AI: reply to your request No. {n}",
           "{text}\n\nRequest No. {n}. You can reply at https://konsilier.com/support"),
    "tr": ("Konsilier AI: {n} numaralı başvurunuza yanıt",
           "{text}\n\nBaşvuru No. {n}. Yanıtlamak için: https://konsilier.com/support"),
    "ar": ("Konsilier AI: الرد على طلبك رقم {n}",
           "{text}\n\nالطلب رقم {n}. يمكنك الرد على الصفحة https://konsilier.com/support"),
}


class DeskReply(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/clients/tickets/{ticket_id}/reply")
def reply(ticket_id: int, body: DeskReply, session: Session = Depends(get_session),
          container: Container = Depends(get_container), op: User = Depends(operator("clients"))) -> dict[str, Any]:
    t = session.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(404, "ticket not found")
    session.add(TicketMessage(ticket_id=t.id, author="desk", operator=op.email, text=body.text.strip()))
    t.status, t.updated_at = "in_progress", datetime.now(timezone.utc)
    subject, text = REPLY_MAIL.get((t.language or "ru")[:2], REPLY_MAIL["ru"])
    _tell(session, container, t.user_id, t.email, subject.format(n=t.id), text.format(n=t.id, text=body.text.strip()))
    session.flush()
    return ticket_view(t, messages_of(session, [t.id])[t.id])


class TicketStatus(BaseModel):
    status: Literal["new", "in_progress", "done"]


@router.post("/clients/tickets/{ticket_id}/status")
def ticket_status(ticket_id: int, body: TicketStatus, session: Session = Depends(get_session),
                  _: User = Depends(operator("clients"))) -> dict[str, Any]:
    t = session.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(404, "ticket not found")
    t.status, t.updated_at = body.status, datetime.now(timezone.utc)
    return {"id": t.id, "status": t.status}


@router.get("/clients/lawyer-requests")
def lawyer_requests(status: str | None = None, session: Session = Depends(get_session),
                    _: User = Depends(operator("clients"))) -> list[dict[str, Any]]:
    q = select(LawyerRequest).order_by(LawyerRequest.created_at.desc()).limit(500)
    if status:
        q = q.where(LawyerRequest.status == status)
    return [{"id": r.id, "case_id": str(r.case_id), "lawyer_ref": r.lawyer_ref, "full_name": r.full_name,
             "phone": r.phone, "email": r.email, "status": r.status, "note": r.desk_note,
             "created_at": r.created_at.isoformat()} for r in session.scalars(q).all()]


class RequestUpdate(BaseModel):
    status: Literal["new", "passed", "closed"] | None = None
    note: str | None = Field(default=None, max_length=4000)


@router.post("/clients/lawyer-requests/{req_id}")
def update_request(req_id: int, body: RequestUpdate, session: Session = Depends(get_session),
                   _: User = Depends(operator("clients"))) -> dict[str, Any]:
    r = session.get(LawyerRequest, req_id)
    if r is None:
        raise HTTPException(404, "request not found")
    if body.note is not None:
        r.desk_note = body.note
    if body.status:
        r.status = body.status
    return {"id": r.id, "status": r.status, "note": r.desk_note}


# ------------------------------------------------------------------ clients desk: document payments
PLAN_RU = {"biz": "Бизнес", "bizpro": "Бизнес Про"}


def invoice_view(session: Session, container: Container, inv: Invoice) -> dict[str, Any]:
    case = session.get(Case, inv.case_id) if inv.case_id else None
    owner = session.get(User, inv.user_id)
    title = None
    if case is not None and case.scenario_id:
        try:
            title = container.engine.pack_of(case).localized(container.engine.scenario_of(case).title, "ru")
        except Exception:  # noqa: BLE001 — a removed scenario must not hide the payment
            title = case.scenario_id
    if inv.purpose == "plan":
        title = f"Тариф «{PLAN_RU.get(inv.plan or '', inv.plan)}»"
    from .pilot import lawyer_invoice_line

    return {"kaspi_opened_at": _kaspi_opened_at(session, inv),
            "trusted_at": inv.trusted_at.isoformat() if inv.trusted_at else None, "id": inv.id, "code": inv.code, "amount": float(inv.amount), "currency": inv.currency,
            "status": inv.status, "method": inv.method, "purpose": inv.purpose, "plan": inv.plan,
            "case_id": str(inv.case_id) if inv.case_id else None, "case_title": title,
            "client_email": owner.email if owner else None, "client_phone": owner.phone if owner else None,
            "created_at": inv.created_at.isoformat(), "claimed_at": inv.claimed_at.isoformat() if inv.claimed_at else None,
            "decided_at": inv.decided_at.isoformat() if inv.decided_at else None, "decided_by": inv.decided_by,
            "note": inv.desk_note, "way": inv.pay_way, "payer_phone": inv.payer_phone,
            "buyer_name": inv.buyer_name, "buyer_bin": inv.buyer_bin, "lawyer": lawyer_invoice_line(session, inv)}


def _kaspi_opened_at(session: Session, inv: Invoice) -> str | None:
    """When the person last tapped «Оплатить в Kaspi» for this bill (the «payment_way» audit entry): the desk matches a
    Kaspi Pay payment by its amount and this time — the client is not asked to type the payment code (owner 01.10)."""
    if inv.case_id is None:
        return None
    rows = session.scalars(select(AuditLog).where(AuditLog.case_id == inv.case_id, AuditLog.event == "payment_way")
                           .order_by(AuditLog.created_at.desc()).limit(20)).all()
    hit = next((r for r in rows if (r.data or {}).get("invoice") == inv.code
                and (r.data or {}).get("way") in ("kaspi_link", "kaspi_qr")), None)
    return hit.created_at.isoformat() if hit else None


@router.get("/clients/payments")
def payments(status: str | None = "awaiting_confirmation", session: Session = Depends(get_session),
             container: Container = Depends(get_container),
             _: User = Depends(operator("clients"))) -> list[dict[str, Any]]:
    q = select(Invoice).where(Invoice.method != "stub", Invoice.user_id.not_in(_test_users())) \
        .order_by(Invoice.created_at.desc()).limit(500)
    if status:
        q = q.where(Invoice.status == status)
    return [invoice_view(session, container, inv) for inv in session.scalars(q).all()]


class PaymentDecision(BaseModel):
    decision: Literal["paid", "not_found"]
    note: str | None = Field(default=None, max_length=4000)


@router.post("/clients/payments/{invoice_id}")
def decide_payment(invoice_id: int, body: PaymentDecision, session: Session = Depends(get_session),
                   container: Container = Depends(get_container),
                   op: User = Depends(operator("clients"))) -> dict[str, Any]:
    return decide_invoice(session, container, invoice_id, op.email or "operator", body.decision == "paid", body.note)


WAY_RECEIPT = {"kaspi_transfer": "перевод Kaspi", "kaspi_link": "Kaspi Pay, ссылка", "kaspi_qr": "Kaspi QR",
               "kaspi_invoice": "счёт Kaspi", "bank_invoice": "банковский перевод по счёту"}


def receipt_text(session: Session, container: Container, inv: Invoice, where: str) -> str:
    """PAYMENT_RECEIPT_EMAIL: the letter after the desk confirms — amount, date, what was bought, the link. It is a
    payment confirmation, not a fiscal receipt (that comes from a cash register: Kaspi Касса for Kaspi Pay)."""
    from ..core.bill import ITEM_RU, BillWords, money

    st = container.settings
    item = ITEM_RU.get(inv.purpose, ITEM_RU["document"])
    if inv.purpose == "plan":
        item = f"{item} «{PLAN_RU.get(inv.plan or '', inv.plan)}»"
    elif inv.case_id is not None:
        case = session.get(Case, inv.case_id)
        if case is not None and case.scenario_id:
            try:
                item += f" — {container.engine.pack_of(case).localized(container.engine.scenario_of(case).title, 'ru')}"
            except Exception:  # noqa: BLE001 — a removed scenario must not stop the letter
                pass
    at = inv.decided_at or inv.created_at
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    when = at.astimezone(timezone(timedelta(hours=5))).strftime("%d.%m.%Y %H:%M")
    words = BillWords.of(container.engine.billing_pack(session, inv), inv.currency)
    lines = ["Оплата получена. Спасибо!", "",
             f"Сумма: {money(inv.amount)} {words.sign}",
             f"Дата: {when} (Алматы)",
             f"За что: {item}",
             f"Код платежа: {inv.code}, счёт № {inv.id}"]
    if inv.pay_way in WAY_RECEIPT:
        lines.append(f"Способ: {WAY_RECEIPT[inv.pay_way]}")
    if st.payment_llp_name:
        lines.append(f"Продавец: {st.payment_llp_name}"
                     + (f", {words.seller_id} {st.payment_llp_bin}" if st.payment_llp_bin else ""))
    lines += ["", (f"Тариф подключён: {where}" if inv.purpose == "plan"
                   else f"Юрист получил материалы дела: {where}" if inv.purpose == "lawyer"
                   else f"Документ готовится автоматически и появится в карточке дела: {where}"), "",
              "Это письмо — подтверждение оплаты, а не фискальный чек."]
    if st.payment_kaspi_kassa and inv.pay_way in ("kaspi_link", "kaspi_qr", "kaspi_invoice"):
        lines.append("Фискальный чек за оплату через Kaspi Pay приходит в приложение Kaspi.kz.")
    return "\n".join(lines)


def decide_invoice(session: Session, container: Container, invoice_id: int, decided_by: str, paid: bool,
                   note: str | None, later: list | None = None) -> dict[str, Any]:
    """Payment found (the document is made right away) or not found; the client is told by e-mail. Used by the
    clients desk, by the owner's command centre (konsilier/api/command.py) and by the Kaspi Pay push
    (konsilier/kaspi_parse.py), which passes ``later``: the client's e-mail is then sent after the commit, not now."""
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404, "invoice not found")
    try:
        container.engine.decide_payment(session, inv, decided_by, paid, note)
    except EngineError as e:
        raise HTTPException(409, {"code": e.code, "message": e.code}) from e
    if paid and inv.case_id is not None and inv.purpose in ("document", "case"):  # made now, not on the next visit
        def prepare(s: Session) -> None:
            action = container.engine.prepare_after_payment(s, s.get(Invoice, invoice_id))
            if action is not None and not action.pdf_key and action.docx_key:
                s.commit()  # the document is shown now; the PDF follows
                container.engine.ensure_pdf(s, action)
        after_commit(session, container, prepare, "paid-document")
    owner = session.get(User, inv.user_id)
    if owner is not None and owner.email and container.email_sender is not None:
        where = (f"https://konsilier.com/case/{inv.case_id}" if inv.case_id else "https://konsilier.com/plans")
        if paid and container.settings.payment_receipt_email:
            text = receipt_text(session, container, inv, where)
        elif paid and inv.purpose == "lawyer":
            text = f"Оплата получена. Юрист получил материалы дела, подпишите с ним соглашения ЭЦП: {where}"
        elif paid:
            text = (f"Оплата получена. Тариф «{PLAN_RU.get(inv.plan or '', inv.plan)}» подключён: {where}"
                    if inv.purpose == "plan" else f"Оплата получена. Документ готовится автоматически и появится в "
                                                  f"карточке дела: {where}")
        else:
            text = (f"Перевод с кодом {inv.code} не найден. Проверьте сумму и комментарий к переводу и нажмите "
                    f"«Оплатить» ещё раз: {where}")
        to, subject, sender = owner.email, f"Konsilier AI: оплата {inv.code}", container.email_sender

        def send(_s: Session | None = None) -> None:
            try:
                sender.send(to, subject, text)
            except Exception:  # noqa: BLE001
                log.warning("payment e-mail to a client failed", exc_info=True)
        if later is not None:
            later.append(send)
        else:
            send()
    session.flush()
    return invoice_view(session, container, inv)
