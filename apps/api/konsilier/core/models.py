"""Persistence model. Country-agnostic: jurisdiction/scenario are just identifiers."""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .state_machine import CaseStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    api_token: Mapped[str] = mapped_column(String(64), unique=True, index=True,
                                           default=lambda: secrets.token_urlsafe(32))
    channel: Mapped[str] = mapped_column(String(16), default="web")  # web | telegram
    external_id: Mapped[str | None] = mapped_column(String(64), index=True)  # telegram chat id
    language: Mapped[str] = mapped_column(String(8), default="ru")
    country: Mapped[str | None] = mapped_column(String(2))
    display_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    # case status reports and next-step reminders by e-mail (only to a verified address)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    cases: Mapped[list["Case"]] = relationship(back_populates="owner", foreign_keys="Case.owner_id")
    identities: Mapped[list["Identity"]] = relationship(back_populates="user")


class Identity(TimestampMixin, Base):
    """A verified way to recognise a person: e-mail, phone, ЭЦП (IIN from the certificate) or eGov Mobile.

    `subject_hash` is an HMAC of the normalised identifier, so the IIN itself is never stored;
    `display` is a masked form for the UI (e.g. "••••••••1234", "a•••@mail.kz").
    """

    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("kind", "subject_hash", name="uq_identity_kind_subject"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # email | phone | iin (ЭЦП or eGov Mobile)
    subject_hash: Mapped[str] = mapped_column(String(64))
    display: Mapped[str] = mapped_column(String(120))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="identities")


class LoginChallenge(TimestampMixin, Base):
    """One sign-in attempt: a one-time code (email/phone) or a nonce to sign (ЭЦП / eGov Mobile)."""

    __tablename__ = "login_challenges"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    target_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    secret_hash: Mapped[str] = mapped_column(String(64))  # HMAC of the code or the nonce
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # eGov: verified signer, until claimed


class Organization(TimestampMixin, Base):
    """A counterparty or authority (seller, bank, MFO, regulator)."""

    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    country: Mapped[str] = mapped_column(String(2))
    kind: Mapped[str] = mapped_column(String(32))  # business | authority | person
    name: Mapped[str] = mapped_column(String(300))
    registration_id: Mapped[str | None] = mapped_column(String(64))  # BIN / VAT / etc.
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)


class Case(TimestampMixin, Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    jurisdiction: Mapped[str | None] = mapped_column(String(2), index=True)  # None until qualified
    ontology_code: Mapped[str | None] = mapped_column(String(64))
    scenario_id: Mapped[str | None] = mapped_column(String(128), index=True)
    scenario_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default=CaseStatus.INTAKE.value, index=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    qualification_confidence: Mapped[float | None] = mapped_column()
    language: Mapped[str] = mapped_column(String(8), default="ru")
    channel: Mapped[str] = mapped_column(String(16), default="web")
    amount_at_stake: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    # Raw facts as collected (real values; never sent to the LLM unredacted).
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    skipped_fields: Mapped[list[Any]] = mapped_column(JSON, default=list)
    pending_field: Mapped[str | None] = mapped_column(String(64))
    initial_text: Mapped[str | None] = mapped_column(Text)
    narrative: Mapped[str | None] = mapped_column(Text)
    # Stable label ↔ value map for PII redaction ({"[IIN_1]": "900101300123"}).
    pii_map: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    # Coverage level (ADR 0001): verified scenario | universal path | lawyer handoff
    coverage_level: Mapped[str] = mapped_column(String(16), default="verified", server_default="verified",
                                                index=True)
    # nullable: rows created before migration 0004 have no value
    taxonomy: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict, nullable=True)  # {dispute_id, role, …}
    forum_id: Mapped[str | None] = mapped_column(String(128))
    route_reasons: Mapped[list[Any] | None] = mapped_column(JSON, default=list, nullable=True)
    formal_demands: Mapped[str | None] = mapped_column(Text)  # universal path: demands paragraph
    # Case is held for manual review (suspected abuse, false report risk) until an admin releases it.
    # status reports: what the last report described, when it went out, reminders sent since without progress
    report_state: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_nudges: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lawyer_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    lawyer_application_id: Mapped[int | None] = mapped_column(ForeignKey("lawyer_applications.id"), nullable=True)
    hold_reason: Mapped[str | None] = mapped_column(String(64), index=True)

    owner: Mapped[User] = relationship(back_populates="cases", foreign_keys="Case.owner_id")
    parties: Mapped[list["Party"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case", cascade="all, delete-orphan",
                                                      order_by="Evidence.created_at")
    claims: Mapped[list["Claim"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    actions: Mapped[list["Action"]] = relationship(back_populates="case", cascade="all, delete-orphan",
                                                   order_by="Action.sequence")
    deadlines: Mapped[list["Deadline"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    outcome: Mapped["Outcome | None"] = relationship(back_populates="case", uselist=False,
                                                     cascade="all, delete-orphan")


class Party(Base):
    __tablename__ = "parties"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))  # applicant | respondent | authority | ...
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    display_name: Mapped[str | None] = mapped_column(String(300))

    case: Mapped[Case] = relationship(back_populates="parties")
    organization: Mapped[Organization | None] = relationship()


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))  # receipt | order_screenshot | response | ...
    filename: Mapped[str | None] = mapped_column(String(300))
    content_type: Mapped[str | None] = mapped_column(String(100))
    storage_key: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str | None] = mapped_column(Text)  # extracted/forwarded text
    extracted_facts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    case: Mapped[Case] = relationship(back_populates="evidence")


class Claim(TimestampMixin, Base):
    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    norm_refs: Mapped[list[Any]] = mapped_column(JSON, default=list)

    case: Mapped[Case] = relationship(back_populates="claims")


class Action(TimestampMixin, Base):
    """One step of a scenario executed for a case (a document or a hand-off)."""

    __tablename__ = "actions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    action_id: Mapped[str] = mapped_column(String(64))  # id from the scenario
    kind: Mapped[str] = mapped_column(String(16))  # document | handoff
    # draft → pending_approval → ready → submitted → responded
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # not_required | pending | approved | rejected
    approval_status: Mapped[str] = mapped_column(String(16), default="not_required", index=True)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approval_note: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(32))
    submitted_via: Mapped[str | None] = mapped_column(String(32))
    addressee: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    docx_key: Mapped[str | None] = mapped_column(String(300))
    pdf_key: Mapped[str | None] = mapped_column(String(300))
    instructions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    is_draft_scenario: Mapped[bool] = mapped_column(Boolean, default=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_class: Mapped[str | None] = mapped_column(String(16))
    response_summary: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship(back_populates="actions")
    signatures: Mapped[list["DocumentSignature"]] = relationship(back_populates="action",
                                                                 order_by="DocumentSignature.signed_at")


class DocumentSignature(TimestampMixin, Base):
    """An ЭЦП signature over a prepared document: CMS with the document inside, checked by the verifier.

    The signer's identifier is kept only as an HMAC (`subject_hash`) and a masked `display`.
    """

    __tablename__ = "document_signatures"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actions.id"), index=True, nullable=True)
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agreements.id"), index=True, nullable=True)
    signer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(16), default="applicant")  # applicant | lawyer
    subject_hash: Mapped[str] = mapped_column(String(64))
    display: Mapped[str] = mapped_column(String(120))
    signer_name: Mapped[str | None] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(16))  # ncalayer | egov
    file_format: Mapped[str] = mapped_column(String(8))  # pdf | docx
    doc_sha256: Mapped[str] = mapped_column(String(64))
    cms_key: Mapped[str] = mapped_column(String(300))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    action: Mapped[Action | None] = relationship(back_populates="signatures")
    agreement: Mapped["Agreement | None"] = relationship(back_populates="signatures")


class Agreement(TimestampMixin, Base):
    """Customer ↔ lawyer paper for a case (consent, engagement), signed by both with ЭЦП: customer first."""

    __tablename__ = "agreements"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # consent | engagement
    lawyer_application_id: Mapped[int] = mapped_column(ForeignKey("lawyer_applications.id"))
    docx_key: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    template_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="awaiting_customer")  # → awaiting_lawyer → signed

    signatures: Mapped[list[DocumentSignature]] = relationship(back_populates="agreement",
                                                               order_by="DocumentSignature.signed_at")


class Deadline(TimestampMixin, Base):
    __tablename__ = "deadlines"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    action_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actions.id"), index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    norm_ref: Mapped[str | None] = mapped_column(String(200))
    remind_before_days: Mapped[list[Any]] = mapped_column(JSON, default=list)
    reminders_sent: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|met|expired|cancelled

    case: Mapped[Case] = relationship(back_populates="deadlines")


class Outcome(TimestampMixin, Base):
    """How the case ended — the main data asset. Always filled on close."""

    __tablename__ = "outcomes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), unique=True)
    result: Mapped[str] = mapped_column(String(32))  # won | partial | lost | abandoned | settled
    amount_recovered: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    days_to_resolution: Mapped[int] = mapped_column(Integer)
    resolved_at_step: Mapped[str | None] = mapped_column(String(64))
    scenario_id: Mapped[str | None] = mapped_column(String(128))
    scenario_version: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="outcome")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), index=True)
    actor: Mapped[str] = mapped_column(String(100))  # user:<id> | admin:<name> | system | scheduler
    event: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base):
    """Outbox of messages to users; web reads it as an inbox, other channels deliver it."""

    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    channel: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WaitlistEntry(Base):
    __tablename__ = "waitlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    contact: Mapped[str] = mapped_column(String(200))
    problem: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LawyerApplication(Base):
    """A lawyer / advocate / human-rights defender applying to join (partner programme)."""

    __tablename__ = "lawyer_applications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))  # advocate | legal_consultant | human_rights | other
    organization: Mapped[str | None] = mapped_column(String(300))
    license_number: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    specializations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    contact: Mapped[str] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    referred_by: Mapped[str | None] = mapped_column(String(16), index=True)
    wants_expert: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # scenario expert
    status: Mapped[str] = mapped_column(String(16), default="new")  # new | verified | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # set when the applicant was signed in with ЭЦП: who they are, per the certificate
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    iin_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ecp_name: Mapped[str | None] = mapped_column(String(200), nullable=True)


class DemandSignal(Base):
    """Anonymous demand analytics for the universal path: which scenarios to package next. No PII."""

    __tablename__ = "demand_signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country: Mapped[str | None] = mapped_column(String(2), index=True)
    branch: Mapped[str | None] = mapped_column(String(64), index=True)
    dispute_type: Mapped[str | None] = mapped_column(String(128), index=True)
    level: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Consent(Base):
    """Explicit consent, e.g. to processing special categories of data (health, religion, criminal record)."""

    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))  # special_category:health | false_report_ack
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ForumDraft(Base):
    """An admin's proposed change to a pack's forum registry; exported to YAML for a reviewed PR."""

    __tablename__ = "forum_drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    forum_id: Mapped[str] = mapped_column(String(128))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # full Forum record (validated)
    note: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | exported | discarded
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
