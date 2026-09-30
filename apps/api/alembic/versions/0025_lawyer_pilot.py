"""«Юрист по кнопке» (closed pilot): pilot lawyers with their price, a request addressed to one of them, and a bill
for the lawyer's work paid to the company's account (with the platform's commission)

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lawyer_applications") as b:
        b.add_column(sa.Column("pilot", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("price", sa.Numeric(14, 2), nullable=True))
        b.add_column(sa.Column("price_note", sa.String(300), nullable=True))
    # status (String(16)): new | passed | closed (desk hand-over) and, for the pilot, accepted | declined | paid
    with op.batch_alter_table("lawyer_requests") as b:
        b.add_column(sa.Column("application_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("price", sa.Numeric(14, 2), nullable=True))
        b.add_column(sa.Column("invoice_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
        b.create_foreign_key("fk_lawyer_requests_application", "lawyer_applications", ["application_id"], ["id"])
        b.create_index("ix_lawyer_requests_application_id", ["application_id"])
    with op.batch_alter_table("invoices") as b:
        b.add_column(sa.Column("lawyer_request_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("commission_pct", sa.Numeric(5, 2), nullable=True))
        b.add_column(sa.Column("commission_amount", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invoices") as b:
        for col in ("commission_amount", "commission_pct", "lawyer_request_id"):
            b.drop_column(col)
    with op.batch_alter_table("lawyer_requests") as b:
        b.drop_index("ix_lawyer_requests_application_id")
        b.drop_constraint("fk_lawyer_requests_application", type_="foreignkey")
        for col in ("decided_at", "invoice_id", "price", "application_id"):
            b.drop_column(col)
    with op.batch_alter_table("lawyer_applications") as b:
        for col in ("price_note", "price", "pilot"):
            b.drop_column(col)
