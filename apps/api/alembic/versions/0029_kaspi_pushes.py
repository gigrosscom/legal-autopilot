"""Kaspi Pay pushes (konsilier/core/kaspi_push.py): every notification the payments phone forwards, as it came, with
the amount and payer read from it and the bill it was matched to; and invoices.pay_reminded_at — the one soft
reminder to a client whose «Оплатить» no push matched.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kaspi_pushes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.String(64), nullable=True),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("digest", sa.String(64), nullable=True),
        sa.Column("duplicate_of", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("payer", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("decided_by", sa.String(200), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_kaspi_pushes_received_at", "kaspi_pushes", ["received_at"])
    op.create_index("ix_kaspi_pushes_status", "kaspi_pushes", ["status"])
    op.create_index("ix_kaspi_pushes_invoice_id", "kaspi_pushes", ["invoice_id"])
    op.create_index("ix_kaspi_pushes_digest", "kaspi_pushes", ["digest"], unique=True)
    op.add_column("invoices", sa.Column("pay_reminded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "pay_reminded_at")
    op.drop_index("ix_kaspi_pushes_digest", table_name="kaspi_pushes")
    op.drop_index("ix_kaspi_pushes_invoice_id", table_name="kaspi_pushes")
    op.drop_index("ix_kaspi_pushes_status", table_name="kaspi_pushes")
    op.drop_index("ix_kaspi_pushes_received_at", table_name="kaspi_pushes")
    op.drop_table("kaspi_pushes")
