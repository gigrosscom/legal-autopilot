"""Filings — «Подача» (docs/integrations-plan.md, 7.3): one table for every way a prepared document reaches its
addressee, with its proof.

* «Мастер отправки»: e-mail through Resend (Reply-To and a copy to the client, attachments with their SHA-256,
  delivery statuses and the event log from Resend's webhook, replies by claims+<token>@…); WhatsApp, Telegram,
  Instagram or an app dispute sent by the client with their screenshot. Several rows per document.
* The manual bridge to the official appeal portal: the state body and category, the appeal number and date read
  from the portal's confirmation or typed (``source``), the confirmation as evidence, the SHA-256 of the document we
  gave. ONE row per document — the partial unique index ``uq_filings_action_appeal`` covers only rows with an
  appeal number, so it never limits the letters of the same document.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

INDEXED = ("case_id", "action_id", "user_id", "status", "external_id", "reply_token")
HAS_APPEAL = sa.text("appeal_number IS NOT NULL")


def upgrade() -> None:
    op.create_table(
        "filings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("action_id", sa.Uuid(), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signature_id", sa.Uuid(), sa.ForeignKey("document_signatures.id"), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("recipient", sa.String(500), nullable=False),
        sa.Column("body", sa.String(500), nullable=True),
        sa.Column("body_key", sa.String(100), nullable=True),
        sa.Column("appeal_type", sa.String(16), nullable=True),
        sa.Column("category", sa.String(300), nullable=True),
        sa.Column("reply_to", sa.String(254), nullable=True),
        sa.Column("cc", sa.String(254), nullable=True),
        sa.Column("sender", sa.String(200), nullable=True),
        sa.Column("subject", sa.String(300), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("appeal_number", sa.String(64), nullable=True),
        sa.Column("filed_at", sa.Date(), nullable=True),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column("doc_format", sa.String(8), nullable=True),
        sa.Column("doc_sha256", sa.String(64), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("consent_text_version", sa.String(32), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("receipt_key", sa.String(300), nullable=True),
        sa.Column("receipt_sha256", sa.String(64), nullable=True),
        sa.Column("receipt_evidence_id", sa.Uuid(), sa.ForeignKey("evidence.id"), nullable=True),
        sa.Column("followup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_token", sa.String(16), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in INDEXED:
        op.create_index(f"ix_filings_{col}", "filings", [col])
    op.create_index("uq_filings_action_appeal", "filings", ["action_id"], unique=True,
                    sqlite_where=HAS_APPEAL, postgresql_where=HAS_APPEAL)


def downgrade() -> None:
    op.drop_index("uq_filings_action_appeal", table_name="filings")
    for col in reversed(INDEXED):
        op.drop_index(f"ix_filings_{col}", table_name="filings")
    op.drop_table("filings")
