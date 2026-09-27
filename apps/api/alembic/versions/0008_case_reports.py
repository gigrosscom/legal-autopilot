"""case status reports and next-step reminders by e-mail

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as b:
        b.add_column(sa.Column("notify_email", sa.Boolean(), server_default="true", nullable=False))
    with op.batch_alter_table("cases", schema=None) as b:
        b.add_column(sa.Column("report_state", sa.String(length=500), nullable=True))
        b.add_column(sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("report_nudges", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("cases", schema=None) as b:
        b.drop_column("report_nudges")
        b.drop_column("reported_at")
        b.drop_column("report_state")
    with op.batch_alter_table("users", schema=None) as b:
        b.drop_column("notify_email")
