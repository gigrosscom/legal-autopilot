"""«Мастер отправки»: proof of filing — one row per sending of a document to an addressee (e-mail through Resend
with its delivery statuses; WhatsApp, Telegram, Instagram or an app dispute sent by the client with a screenshot),
and the log of events

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


def upgrade() -> None:
    op.create_table(
        "filings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("action_id", sa.Uuid(), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signature_id", sa.Uuid(), sa.ForeignKey("document_signatures.id"), nullable=True),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("recipient", sa.String(254), nullable=False),
        sa.Column("reply_to", sa.String(254), nullable=True),
        sa.Column("cc", sa.String(254), nullable=True),
        sa.Column("sender", sa.String(200), nullable=True),
        sa.Column("subject", sa.String(300), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("doc_sha256", sa.String(64), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("consent_text_version", sa.String(32), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("receipt_key", sa.String(300), nullable=True),
        sa.Column("receipt_sha256", sa.String(64), nullable=True),
        sa.Column("followup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_token", sa.String(16), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_filings_case_id", "filings", ["case_id"])
    op.create_index("ix_filings_action_id", "filings", ["action_id"])
    op.create_index("ix_filings_user_id", "filings", ["user_id"])
    op.create_index("ix_filings_status", "filings", ["status"])
    op.create_index("ix_filings_external_id", "filings", ["external_id"])
    op.create_index("ix_filings_reply_token", "filings", ["reply_token"])


def downgrade() -> None:
    for ix in ("reply_token", "external_id", "status", "user_id", "action_id", "case_id"):
        op.drop_index(f"ix_filings_{ix}", table_name="filings")
    op.drop_table("filings")
