"""document payment by manual transfer: invoices with a payment code, confirmed by the clients desk

Cases that already have a prepared document keep access to it (they were issued while documents were free).

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("method", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(200), nullable=True),
        sa.Column("desk_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_invoices_code"),
    )
    op.create_index("ix_invoices_case_id", "invoices", ["case_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_created_at", "invoices", ["created_at"])
    # documents prepared before payment was switched on stay available to their owners
    op.execute("UPDATE cases SET paid = true WHERE id IN (SELECT DISTINCT case_id FROM actions "
               "WHERE docx_key IS NOT NULL)")


def downgrade() -> None:
    op.drop_index("ix_invoices_created_at", table_name="invoices")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_case_id", table_name="invoices")
    op.drop_table("invoices")
