"""The courier delivery of a paid document: the order, its bill, placing it with the provider, statuses from webhooks,
polling and the operator, and what each status does in the case (feed, notifications, the response deadline)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.adapters.payment import kz_phone
from ..core.engine import EngineError
from ..core.models import Action, Case, Deadline, Delivery, Filing, Invoice, User, utcnow
from . import providers as P

log = logging.getLogger(__name__)

PURPOSE = "delivery"
CHANNEL = "courier"
RANK = {"awaiting_payment": 0, "paid": 1, P.ORDERED: 2, P.PICKED_UP: 3, P.IN_TRANSIT: 4, P.DELIVERED: 5,
        P.REFUSED: 5, P.RETURNED: 6, P.CANCELLED: 9}
LIVE = ("awaiting_payment", "paid", P.ORDERED, P.PICKED_UP, P.IN_TRANSIT)  # not finished yet
POLLED = (P.ORDERED, P.PICKED_UP, P.IN_TRANSIT)
REORDER_AFTER = (P.CANCELLED, P.REFUSED)  # a new courier may be ordered after these
CANCELLABLE_BY_OPS = ("awaiting_payment", "paid", P.ORDERED)
GOV_KINDS = ("authority", "forum")
NOTIFIED_ALWAYS = (P.DELIVERED, P.REFUSED, P.RETURNED, P.CANCELLED)
PLACE_RETRY = timedelta(minutes=10)
MAX_ATTEMPTS = 10
RETURN_WATCH = timedelta(days=30)  # after delivery the return of the second copy is followed this long


class CourierError(Exception):
    def __init__(self, code: str, status: int = 409, **extra: Any):
        super().__init__(code)
        self.code, self.status, self.extra = code, status, extra


# ------------------------------------------------------------------ the pack's courier.yaml
@dataclass
class CourierConfig:
    enabled: bool
    price: Decimal
    currency: str | None
    cities: list[dict[str, Any]]
    windows: list[str]
    lead_hours: float = 2
    max_days: int = 14
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    texts: dict[str, dict[str, str]] = field(default_factory=dict)

    def city(self, cid: str | None) -> dict[str, Any] | None:
        return next((c for c in self.cities if c.get("id") == cid), None)

    def text(self, lang: str, key: str, default_lang: str = "ru", **kw: Any) -> str:
        for lg in (lang, default_lang, "en"):
            raw = (self.texts.get(lg) or {}).get(key)
            if raw is not None:
                try:
                    return str(raw).format(**kw)
                except (KeyError, IndexError):
                    return str(raw)
        return ""


_CACHE: dict[Path, tuple[float, CourierConfig | None]] = {}


def config_of(pack: Any) -> CourierConfig | None:
    """The pack's courier settings (``<pack>/courier.yaml``), or None where the pack has no courier."""
    path = Path(pack.root) / "courier.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    cfg = CourierConfig(
        enabled=bool(data.get("enabled", True)), price=Decimal(str(data.get("price") or 0)),
        currency=data.get("currency") or pack.currency, cities=list(data.get("cities") or []),
        windows=[str(w) for w in data.get("windows") or []], lead_hours=float(data.get("lead_hours", 2)),
        max_days=int(data.get("max_days", 14)),
        providers={k: v for k, v in data.items() if k in ("cdek", "alemtat") and isinstance(v, dict)},
        texts={k: v for k, v in (data.get("texts") or {}).items() if isinstance(v, dict)})
    _CACHE[path] = (mtime, cfg)
    return cfg


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | date | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _window(w: str) -> tuple[str, str] | None:
    a, _, b = w.partition("-")
    a, b = a.strip(), b.strip()
    try:
        if time.fromisoformat(a) >= time.fromisoformat(b):
            return None
    except ValueError:
        return None
    return a, b


def _clean(value: Any, lo: int, hi: int) -> str | None:
    v = " ".join(str(value or "").split())
    return v if lo <= len(v) <= hi else None


# ------------------------------------------------------------------ the service
class Courier:
    """Held by the container (``container.courier``)."""

    def __init__(self, container: Any, provider: P.CourierProvider):
        self.c = container
        self.provider = provider

    @property
    def engine(self) -> Any:
        return self.c.engine

    def cfg(self, case: Case) -> CourierConfig | None:
        return config_of(self.engine.pack_of(case)) if case.scenario_id else None

    # -- what the case page shows
    def reason(self, case: Case, action: Action) -> str | None:
        """Why a courier cannot be ordered for this document now (None: it can)."""
        cfg = self.cfg(case)
        if not self.c.settings.courier_enabled or cfg is None or not cfg.enabled or not cfg.cities or cfg.price <= 0:
            return "off"
        if action.kind != "document" or action.status not in ("ready", "submitted"):
            return "not_ready"
        if not (case.paid or action.unlocked_by not in (None, "free")):
            return "payment_required"
        if (action.addressee or {}).get("kind") in GOV_KINDS:
            return "gov"
        if not self.engine.payments.available():
            return "payment_unavailable"
        return None

    def current(self, session: Session, action_id: Any) -> Delivery | None:
        return session.scalar(select(Delivery).where(Delivery.action_id == action_id)
                              .order_by(Delivery.created_at.desc()).limit(1))

    def state(self, session: Session, case: Case, action: Action) -> dict[str, Any] | None:
        """For the case view: may a courier be ordered, and the latest delivery of this document."""
        reason = self.reason(case, action)
        d = self.current(session, action.id)
        if reason == "off" and d is None:
            return None
        cfg = self.cfg(case)
        can = reason is None and (d is None or d.status in REORDER_AFTER)
        return {"available": can, "reason": reason, "price": float(cfg.price) if cfg else None,
                "currency": cfg.currency if cfg else None, "delivery": self.view(session, d, case) if d else None}

    def form(self, session: Session, case: Case, action: Action, user: User) -> dict[str, Any]:
        """What the order form needs: price, cities, windows, the dates allowed and what we already know."""
        from ..contacts import find_contacts

        state = self.state(session, case, action) or {"available": False, "reason": "off", "delivery": None}
        cfg = self.cfg(case)
        if cfg is None:
            return state
        pack = self.engine.pack_of(case)
        lang = case.language
        today = pack.local_now().date()
        addressee = action.addressee or {}
        contacts = find_contacts(case, action, own={x for x in (user.email, user.phone) if x})
        phone = next((c["value"] for c in contacts if c["kind"] in ("phone", "whatsapp")), None)
        address = addressee.get("address") or next((c["value"] for c in contacts if c["kind"] == "address"), "")
        sig = next((g for g in reversed(action.signatures) if g.role == "applicant"), None)
        return {**state,
                "cities": [{"id": c["id"], "name": pack.localized(c.get("name") or {"ru": c["id"]}, lang)}
                           for c in cfg.cities],
                "windows": cfg.windows, "min_date": today.isoformat(),
                "max_date": (today + timedelta(days=cfg.max_days)).isoformat(),
                "provider": self.provider.name, "recipient_phone_required": self.provider.name == "cdek",
                "note": cfg.text(lang, "price_note"), "print_hint": cfg.text(lang, "print_hint"),
                "defaults": {"recipient_name": addressee.get("name") or "", "recipient_address": address or "",
                             "recipient_phone": phone, "contact_phone": user.phone,
                             "contact_name": (sig.signer_name if sig else None) or user.display_name or ""}}

    # -- the order and its bill
    def create(self, session: Session, case: Case, action: Action, user: User, data: dict[str, Any]) -> Delivery:
        reason = self.reason(case, action)
        if reason is not None:
            raise CourierError(reason, 402 if reason == "payment_required" else 409)
        prev = self.current(session, action.id)
        if prev is not None and prev.status not in REORDER_AFTER:
            raise CourierError("already_ordered")
        cfg = self.cfg(case)
        assert cfg is not None
        pack = self.engine.pack_of(case)
        city = cfg.city(data.get("city") or (cfg.cities[0]["id"] if len(cfg.cities) == 1 else None))
        if city is None:
            raise CourierError("bad_city", 422)
        if data.get("window") not in cfg.windows or _window(str(data.get("window"))) is None:
            raise CourierError("bad_window", 422)
        start, end = _window(str(data["window"]))  # type: ignore[misc]
        try:
            day = date.fromisoformat(str(data.get("date")))
        except ValueError as e:
            raise CourierError("bad_date", 422) from e
        now = pack.local_now()
        earliest = now + timedelta(hours=cfg.lead_hours)
        if day > now.date() + timedelta(days=cfg.max_days) or \
                datetime.combine(day, time.fromisoformat(start), tzinfo=pack.tz) < earliest:
            raise CourierError("bad_date", 422)
        fields = {"pickup_address": _clean(data.get("pickup_address"), 5, 500),
                  "recipient_name": _clean(data.get("recipient_name"), 2, 500),
                  "recipient_address": _clean(data.get("recipient_address"), 5, 500),
                  "contact_name": _clean(data.get("contact_name"), 2, 200)}
        for k, v in fields.items():
            if v is None:
                raise CourierError(f"bad_{k}", 422)
        contact_phone = kz_phone(data.get("contact_phone"))
        if contact_phone is None:
            raise CourierError("bad_contact_phone", 422)
        recipient_phone = None
        if (data.get("recipient_phone") or "").strip():
            recipient_phone = kz_phone(data.get("recipient_phone"))
            if recipient_phone is None:
                raise CourierError("bad_recipient_phone", 422)
        elif self.provider.name == "cdek":
            raise CourierError("recipient_phone_required", 422)
        try:
            self.engine._stop_if_unpaid(session, case.owner_id)
        except EngineError as e:
            raise CourierError(e.code, 409, message=str(e)) from e
        payments = self.engine.payments
        bill = payments.create_invoice(case_id=str(case.id), amount=cfg.price, currency=cfg.currency)
        inv = Invoice(case_id=case.id, user_id=case.owner_id, purpose=PURPOSE, code=bill.id, method=payments.method,
                      amount=bill.amount, currency=bill.currency, status=bill.status)
        session.add(inv)
        session.flush()
        now_utc = utcnow()
        d = Delivery(case_id=case.id, action_id=action.id, user_id=case.owner_id, invoice_id=inv.id,
                     provider=self.provider.name, status="awaiting_payment", city=city["id"],
                     pickup_date=day, pickup_from=start, pickup_to=end, contact_phone=contact_phone,
                     recipient_phone=recipient_phone, comment=_clean(data.get("comment"), 1, 500),
                     price=inv.amount, currency=inv.currency, meta={}, attempts=0,
                     events=[{"at": now_utc.isoformat(), "status": "awaiting_payment", "source": "client"}],
                     **fields)
        session.add(d)
        session.flush()
        actor = f"user:{user.id}"
        self.engine.audit(session, case, actor, "invoice_created", invoice=inv.code, purpose=PURPOSE,
                          status=inv.status, amount=str(inv.amount), currency=inv.currency)
        self.engine.audit(session, case, actor, "courier_requested", delivery=str(d.id), action=action.action_id,
                          city=d.city, date=day.isoformat(), window=data["window"])
        if bill.status == "paid":  # the stub adapter (development): paid at once
            inv.decided_at = now_utc
            self.engine._apply_paid(session, inv)
        return d

    def invoice(self, session: Session, d: Delivery) -> Invoice | None:
        return session.get(Invoice, d.invoice_id) if d.invoice_id else None

    def cancel_unpaid(self, session: Session, d: Delivery, actor: str) -> None:
        """The client changes their mind before paying."""
        if d.status != "awaiting_payment":
            raise CourierError("cannot_cancel")
        inv = self.invoice(session, d)
        if inv is not None and inv.status == "awaiting_confirmation":
            raise CourierError("invoice_awaiting_confirmation")
        if inv is not None and inv.status in self.engine.OPEN:
            inv.status = "cancelled"
        self.set_status(session, d, P.CANCELLED, source=actor, notify=False)

    # -- paid → order the courier
    def apply_paid(self, session: Session, inv: Invoice) -> None:
        """engine.paid_hooks["delivery"]: the bill is paid (the desk, a Kaspi Pay push, a webhook or the stub)."""
        d = session.scalar(select(Delivery).where(Delivery.invoice_id == inv.id))
        if d is None or d.status != "awaiting_payment":
            return
        case = session.get(Case, d.case_id)
        action = session.get(Action, d.action_id)
        now = utcnow()
        d.status, d.paid_at = "paid", now
        d.events = [*(d.events or []), {"at": now.isoformat(), "status": "paid", "source": "payment",
                                        "invoice": inv.code}]
        d.filing_id = self._filing(session, case, action, d).id
        self.engine.audit(session, case, "system", "courier_paid", delivery=str(d.id), invoice=inv.code)
        self._tell(session, case, d, "paid")
        if self.provider.has_api and d.provider == self.provider.name:
            from ..api.background import after_commit

            did = d.id
            after_commit(session, self.c, lambda s: self.place(s, s.get(Delivery, did)), "courier-order")
        else:
            self._tell_desk(session, case, d, "Курьер: закажите доставку",
                            "Клиент оплатил доставку курьером. Закажите курьера и внесите номер отслеживания и "
                            "статусы в оперативном центре (Операции → Курьер).")

    def _filing(self, session: Session, case: Case, action: Action, d: Delivery) -> Filing:
        """The proof row (the one ``filings`` table): created when the delivery is paid, closed on delivery."""
        key = action.pdf_key or action.docx_key
        sha = hashlib.sha256(self.c.storage.get(key)).hexdigest() if key else None
        addressee = action.addressee or {}
        sig = next((g for g in reversed(action.signatures) if g.role == "applicant"), None)
        f = Filing(case_id=case.id, action_id=action.id, user_id=d.user_id, channel=CHANNEL,
                   signature_id=sig.id if sig else None,
                   recipient=f"{d.recipient_name}, {d.recipient_address}"[:500],
                   body=str(addressee.get("name"))[:500] if addressee.get("name") else None,
                   body_key=f"{addressee['kind']}:{addressee['key']}"[:100]
                   if addressee.get("key") and addressee.get("kind") else None,
                   status="sending", doc_format="pdf" if action.pdf_key else "docx" if key else None,
                   doc_sha256=sha, attachments=[], consent_at=utcnow(), consent_text_version="courier-v1",
                   events=[{"at": utcnow().isoformat(), "type": "paid", "source": "courier", "delivery": str(d.id)}])
        session.add(f)
        session.flush()
        return f

    def request(self, session: Session, d: Delivery) -> P.OrderRequest:
        case = session.get(Case, d.case_id)
        cfg = self.cfg(case)
        city = (cfg.city(d.city) if cfg else None) or {"id": d.city}
        return P.OrderRequest(
            reference=str(d.id), city=city, pickup_address=d.pickup_address, pickup_date=d.pickup_date,
            pickup_from=d.pickup_from, pickup_to=d.pickup_to, sender_name=d.contact_name,
            sender_phone=d.contact_phone, recipient_name=d.recipient_name, recipient_address=d.recipient_address,
            recipient_phone=d.recipient_phone, comment=d.comment or "",
            config=(cfg.providers.get(self.provider.name) if cfg else None) or {})

    def place(self, session: Session, d: Delivery | None) -> bool:
        """Order the courier with the provider's API. A failure is kept on the delivery and retried by the job;
        the desk is told on the first and the third failure (then it may take the order over by hand)."""
        if d is None or d.status != "paid" or d.external_id or not self.provider.has_api \
                or d.provider != self.provider.name:
            return False
        case = session.get(Case, d.case_id)
        d.attempts = (d.attempts or 0) + 1
        d.polled_at = utcnow()
        req = self.request(session, d)
        try:
            placed = self.provider.create_order(req)
        except P.ProviderError as e:
            d.error = f"{e.code}: {e.detail}"[:300] if e.detail else e.code
            d.events = [*(d.events or []), {"at": utcnow().isoformat(), "status": "error", "source": self.provider.name,
                                            "code": e.code}]
            log.warning("courier order %s failed (%s), attempt %s", d.id, e.code, d.attempts)
            if d.attempts in (1, 3):
                self._tell_desk(session, case, d, f"Курьер: ошибка заказа ({self.provider.name})",
                                f"Заказ курьера не прошёл: {d.error}. Попытка {d.attempts}; сервер повторит сам. "
                                f"Можно заказать вручную и внести номер в оперативном центре (Операции → Курьер).")
            if d.attempts == 3:
                self._tell(session, case, d, "problem")
            return False
        d.external_id, d.error = placed.external_id[:100], None
        d.tracking = (placed.tracking or d.tracking or "")[:100] or None
        d.meta = {**(d.meta or {}), **placed.meta}
        try:
            q = self.provider.quote(req)
            if q.amount is not None:
                d.meta = {**d.meta, "cost": str(q.amount), "cost_currency": q.currency}
        except P.ProviderError:
            pass  # the cost is for the desk only
        self.set_status(session, d, P.ORDERED, source=self.provider.name)
        return True

    # -- statuses
    def refresh(self, session: Session, d: Delivery, source: str) -> bool:
        """Ask the provider and apply what is new. False when the provider could not be asked."""
        if not d.external_id or not self.provider.has_api or d.provider != self.provider.name:
            return False
        d.polled_at = utcnow()
        try:
            snap = self.provider.status(d.external_id, dict(d.meta or {}))
        except P.ProviderError as e:
            log.warning("courier status %s: %s", d.id, e.code)
            return False
        if snap.tracking:
            d.tracking = str(snap.tracking)[:100]
        if snap.meta:
            d.meta = {**(d.meta or {}), **snap.meta}
        applied = [e for e in snap.events
                   if self.set_status(session, d, e.status, at=e.at, source=source, code=e.code, text=e.text,
                                      signer=e.signer, notify=False)]
        if applied:
            case = session.get(Case, d.case_id)
            last = applied[-1].status
            for e in applied:
                if e.status in NOTIFIED_ALWAYS or e.status == last:
                    self._tell(session, case, d, e.status)
        return True

    def set_status(self, session: Session, d: Delivery, status: str, *, at: datetime | None = None,
                   source: str, code: str | None = None, text: str | None = None, signer: str | None = None,
                   notify: bool = True) -> bool:
        """Move the delivery forward (never back; a repeated status is ignored). Delivered starts the response
        deadline and closes the proof; every change goes to the case's log and, by default, to the client."""
        if status not in RANK or d.status == P.CANCELLED:
            return False
        if status == P.CANCELLED:
            if d.status not in CANCELLABLE_BY_OPS:
                return False
        elif RANK[status] <= RANK.get(d.status, 0):
            return False
        at = _aware(at) or utcnow()
        case = session.get(Case, d.case_id)
        d.status = status
        entry: dict[str, Any] = {"at": at.isoformat(), "status": status, "source": source}
        if code:
            entry["code"] = str(code)[:60]
        if text:
            entry["text"] = str(text)[:200]
        d.events = [*(d.events or []), entry]
        if signer:
            d.signer_name = signer[:200]
        if status == P.ORDERED:
            d.ordered_at = d.ordered_at or at
        elif status in (P.PICKED_UP, P.IN_TRANSIT):
            d.picked_up_at = d.picked_up_at or at
        elif status == P.DELIVERED:
            d.delivered_at = at
            d.picked_up_at = d.picked_up_at or at
        elif status == P.RETURNED:
            d.returned_at = at
        self._filing_event(session, d, status, at, source)
        self.engine.audit(session, case, source if ":" in source else f"courier:{source}", f"courier_{status}",
                          delivery=str(d.id), tracking=d.tracking)
        if status == P.DELIVERED:
            self._delivered(session, case, d, at)
        if status == P.REFUSED:
            self._tell_desk(session, case, d, "Курьер: получатель отказался",
                            f"Получатель {d.recipient_name} отказался принять документ. Отказ зафиксирован курьером. "
                            f"Предложите клиенту копию по e-mail и повторное вручение.")
        if notify:
            self._tell(session, case, d, status)
        return True

    def _filing_event(self, session: Session, d: Delivery, status: str, at: datetime, source: str) -> None:
        f = session.get(Filing, d.filing_id) if d.filing_id else None
        if f is None:
            return
        f.events = [*(f.events or []), {"at": at.isoformat(), "type": status, "source": source}]
        f.external_id = d.tracking or d.external_id
        if status == P.DELIVERED:
            f.status, f.delivered_at, f.sent_at = "delivered", at, at
        elif status == P.REFUSED:
            f.status = "refused"
        elif status == P.CANCELLED:
            f.status = "failed"

    def _delivered(self, session: Session, case: Case, d: Delivery, at: datetime) -> None:
        """The response deadline runs from the day of delivery (the local date), as for an e-mail sending."""
        action = session.get(Action, d.action_id)
        if action is None or action.status != "ready" or case.status != "action_ready":
            return  # already filed another way: its deadline stands
        pack = self.engine.pack_of(case)
        try:
            self.engine.mark_submitted(session, case, action, "system:courier", via=CHANNEL,
                                       submitted_on=at.astimezone(pack.tz).date(), sent=True)
        except EngineError as e:
            log.warning("courier delivered, not marked submitted: %s", e.code)

    # -- telling people
    def _tell(self, session: Session, case: Case, d: Delivery, key: str) -> None:
        cfg = self.cfg(case)
        if cfg is None:
            return
        pack = self.engine.pack_of(case)
        lang = case.language
        dl = pack.manifest.default_language
        loc = lambda dt: _aware(dt).astimezone(pack.tz).strftime("%d.%m.%Y") if dt else ""  # noqa: E731
        due = ""
        if key == P.DELIVERED:
            row = session.scalar(select(Deadline).where(Deadline.action_id == d.action_id, Deadline.status == "active"))
            if row is not None:
                due = cfg.text(lang, "due", dl, due=row.due_date.strftime("%d.%m.%Y"))
        tracking = cfg.text(lang, "tracking", dl, tracking=d.tracking) if d.tracking else ""
        day = loc(d.delivered_at) if key == P.DELIVERED else d.pickup_date.strftime("%d.%m.%Y")
        text = cfg.text(
            lang, key, dl, date=day, window=f"{d.pickup_from}–{d.pickup_to}",
            address=d.pickup_address, recipient=d.recipient_name, tracking=tracking,
            provider=cfg.text(lang, f"provider_{d.provider}", dl) or d.provider,
            signer=cfg.text(lang, "signer", dl, name=d.signer_name) if d.signer_name else "",
            due=due, reason="")
        if text:
            self.engine.notifier.notify(session, case, "delivery", text)

    def _tell_desk(self, session: Session, case: Case, d: Delivery, subject: str, text: str) -> None:
        from ..team import notify_team

        owner = session.get(User, case.owner_id)
        site = self.c.settings.public_site_url.rstrip("/")
        body = (f"{text}\n\nДело {case.id}. Забор: {d.pickup_date:%d.%m.%Y} {d.pickup_from}–{d.pickup_to}, "
                f"{d.pickup_address}, {d.contact_name}, {d.contact_phone}.\nПолучатель: {d.recipient_name}, "
                f"{d.recipient_address}{', ' + d.recipient_phone if d.recipient_phone else ''}.\n\n"
                f"Оперативный центр: {site}/ops?tab=ops")
        notify_team(self.c, subject, body, desk="clients", also=self.c.settings.payment_notify_emails,
                    test=bool(owner and owner.is_test))

    # -- the operator (/ops)
    def ops_update(self, session: Session, d: Delivery, operator: str, *, status: str | None = None,
                   tracking: str | None = None, signer_name: str | None = None, at: datetime | None = None,
                   note: str | None = None) -> None:
        """Manual orders (and taking over a failed API order): the tracking number, the statuses, who signed."""
        if tracking is not None:
            d.tracking = tracking.strip()[:100] or None
        if note:
            d.events = [*(d.events or []), {"at": utcnow().isoformat(), "status": "note", "source": f"ops:{operator}",
                                            "text": note[:200]}]
        if status is None:
            return
        if status == P.CANCELLED:
            self.ops_cancel(session, d, operator)
            return
        if status not in RANK or RANK[status] < RANK[P.ORDERED]:
            raise CourierError("bad_status", 422)
        if d.status == "awaiting_payment":
            raise CourierError("not_paid")
        if RANK[status] <= RANK.get(d.status, 0):
            raise CourierError("status_not_forward")
        if d.provider != "manual" and not d.external_id:
            d.provider, d.error = "manual", None  # the operator took the order over: no API calls for it
        self.set_status(session, d, status, at=at, source=f"ops:{operator}", signer=signer_name)

    def ops_cancel(self, session: Session, d: Delivery, operator: str) -> None:
        if d.status not in CANCELLABLE_BY_OPS:
            raise CourierError("cannot_cancel")
        if d.external_id and self.provider.has_api and d.provider == self.provider.name:
            try:
                self.provider.cancel(d.external_id, dict(d.meta or {}))
            except P.ProviderError as e:
                d.error = f"cancel: {e.code}"
        inv = self.invoice(session, d)
        if inv is not None and inv.status in self.engine.OPEN:
            inv.status = "cancelled"
        self.set_status(session, d, P.CANCELLED, source=f"ops:{operator}")

    # -- the scheduler: place what is paid, poll what is on its way
    def job(self, session: Session, now: datetime) -> int:
        if not self.provider.has_api:
            return 0
        done = 0
        name = self.provider.name
        for d in session.scalars(select(Delivery).where(Delivery.status == "paid", Delivery.external_id.is_(None),
                                                        Delivery.provider == name)).all():
            last = _aware(d.polled_at)
            if (d.attempts or 0) >= MAX_ATTEMPTS or (last is not None and last > now - PLACE_RETRY):
                continue
            try:
                with session.begin_nested():
                    done += self.place(session, d)
            except Exception:  # noqa: BLE001 — one order never stops the rest
                log.exception("courier: placing %s failed", d.id)
        every = timedelta(minutes=max(1, self.c.settings.courier_poll_minutes))
        rows = session.scalars(select(Delivery).where(
            Delivery.provider == name, Delivery.external_id.is_not(None),
            Delivery.status.in_((*POLLED, P.DELIVERED, P.REFUSED)), Delivery.returned_at.is_(None))).all()
        for d in rows:
            last = _aware(d.polled_at)
            if last is not None and last > now - every:
                continue
            if d.status in (P.DELIVERED, P.REFUSED):  # only the return of the second copy is still awaited
                end = _aware(d.delivered_at) or _aware(d.updated_at) or now
                if end < now - RETURN_WATCH:
                    continue
            try:
                with session.begin_nested():
                    done += self.refresh(session, d, "poll")
            except Exception:  # noqa: BLE001
                log.exception("courier: polling %s failed", d.id)
        return done

    def webhook(self, session: Session, provider: str, payload: Any) -> dict[str, Any]:
        """A provider's webhook names an order; its status is read from the provider's API."""
        if provider != self.provider.name or not self.provider.has_api:
            return {"ok": True, "matched": False}
        ref = self.provider.webhook_ref(payload)
        if not ref:
            return {"ok": True, "matched": False}
        d = session.scalar(select(Delivery).where(Delivery.external_id == ref, Delivery.provider == provider))
        if d is None:  # the return order of «Реверс»
            d = next((x for x in session.scalars(select(Delivery).where(
                Delivery.provider == provider, Delivery.status.in_((P.DELIVERED, P.REFUSED)),
                Delivery.returned_at.is_(None))).all() if (x.meta or {}).get("return_uuid") == ref), None)
        if d is None:
            return {"ok": True, "matched": False}
        self.refresh(session, d, "webhook")
        return {"ok": True, "matched": True, "status": d.status}

    # -- views
    def view(self, session: Session, d: Delivery, case: Case | None = None, *, ops: bool = False) -> dict[str, Any]:
        case = case or session.get(Case, d.case_id)
        cfg = self.cfg(case)
        inv = self.invoice(session, d)
        lang = case.language
        out: dict[str, Any] = {
            "id": str(d.id), "status": d.status, "provider": d.provider,
            "provider_label": (cfg.text(lang, f"provider_{d.provider}") if cfg else "") or d.provider,
            "city": d.city, "pickup_address": d.pickup_address, "pickup_date": d.pickup_date.isoformat(),
            "pickup_from": d.pickup_from, "pickup_to": d.pickup_to, "contact_name": d.contact_name,
            "contact_phone": d.contact_phone, "recipient_name": d.recipient_name,
            "recipient_address": d.recipient_address, "recipient_phone": d.recipient_phone,
            "price": float(d.price), "currency": d.currency, "tracking": d.tracking, "signer_name": d.signer_name,
            "paid_at": _iso(d.paid_at), "ordered_at": _iso(d.ordered_at), "picked_up_at": _iso(d.picked_up_at),
            "delivered_at": _iso(d.delivered_at), "returned_at": _iso(d.returned_at), "created_at": _iso(d.created_at),
            "events": [{"at": e.get("at"), "status": e.get("status")} for e in d.events or []
                       if e.get("status") in RANK],
            "invoice": self.engine.invoice_details(inv)
            if inv is not None and d.status == "awaiting_payment" and inv.status != "cancelled" else None,
            "print_hint": cfg.text(lang, "print_hint") if cfg else None,
        }
        if ops:
            owner = session.get(User, d.user_id)
            out.update({"case_id": str(d.case_id), "external_id": d.external_id, "error": d.error,
                        "attempts": d.attempts, "meta": d.meta or {}, "comment": d.comment,
                        "client": (owner.email or owner.phone) if owner else None,
                        "invoice_code": inv.code if inv else None, "invoice_status": inv.status if inv else None,
                        "log": d.events or []})
        return out
