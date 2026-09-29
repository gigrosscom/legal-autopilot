"""plans: a paid document unlocks one document; «Дело под ключ» the whole case; «Бизнес» subscriptions

- invoices.purpose (document | case | plan; existing bills paid for the whole case → "case"), invoices.plan,
  invoices.case_id nullable (a subscription bill has no case)
- cases.doc_credits: paid single documents not used yet
- actions.unlocked_by: what paid for the document; documents prepared before this migration → "legacy"
- subscriptions

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invoices") as b:
        b.add_column(sa.Column("purpose", sa.String(16), nullable=False, server_default="case"))
        b.add_column(sa.Column("plan", sa.String(16), nullable=True))
        b.alter_column("case_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("cases", sa.Column("doc_credits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("actions", sa.Column("unlocked_by", sa.String(32), nullable=True))
    op.execute("UPDATE actions SET unlocked_by = 'legacy' WHERE docx_key IS NOT NULL")
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False),
        sa.Column("documents", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_ends_at", "subscriptions", ["ends_at"])


def downgrade() -> None:
    op.drop_index("ix_subscriptions_ends_at", "subscriptions")
    op.drop_index("ix_subscriptions_user_id", "subscriptions")
    op.drop_table("subscriptions")
    op.drop_column("actions", "unlocked_by")
    op.drop_column("cases", "doc_credits")
    with op.batch_alter_table("invoices") as b:
        b.drop_column("plan")
        b.drop_column("purpose")
