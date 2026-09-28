"""requests to be put in touch with a lawyer

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lawyer_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lawyer_ref", sa.String(100), nullable=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lawyer_requests_case_id", "lawyer_requests", ["case_id"])
    op.create_index("ix_lawyer_requests_created_at", "lawyer_requests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_lawyer_requests_created_at", table_name="lawyer_requests")
    op.drop_index("ix_lawyer_requests_case_id", table_name="lawyer_requests")
    op.drop_table("lawyer_requests")
