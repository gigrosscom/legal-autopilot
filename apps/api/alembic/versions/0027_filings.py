"""Filings: proof that a document was filed with a state body — the manual eOtinish bridge (stage 1 of
docs/integrations-plan.md, 7.1/7.3): the body and category, the appeal number and date the person entered, the
receipt (evidence) and the SHA-256 of the document we gave.

Revision ID: 0027
Revises: 0026 (claude/team-email-delivery). Until that migration is merged the chain points at 0025; set
down_revision to "0026" when both are merged.
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0025"  # → "0026" once claude/team-email-delivery is merged
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "filings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("action_id", sa.Uuid(), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("body_key", sa.String(100), nullable=True),
        sa.Column("appeal_type", sa.String(16), nullable=True),
        sa.Column("category", sa.String(300), nullable=True),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("filed_at", sa.Date(), nullable=False),
        sa.Column("receipt_evidence_id", sa.Uuid(), sa.ForeignKey("evidence.id"), nullable=True),
        sa.Column("doc_format", sa.String(8), nullable=True),
        sa.Column("doc_sha256", sa.String(64), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="client_entered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("action_id", name="uq_filings_action"),
    )
    op.create_index("ix_filings_case_id", "filings", ["case_id"])
    op.create_index("ix_filings_action_id", "filings", ["action_id"])


def downgrade() -> None:
    op.drop_index("ix_filings_action_id", table_name="filings")
    op.drop_index("ix_filings_case_id", table_name="filings")
    op.drop_table("filings")
