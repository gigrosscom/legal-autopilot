"""Bonus account (owner 02.10, «Бонусный счёт»): users.bonus_balance — points (1 point = 1 unit of the bill currency);
invoices.bonus_used — points a bill took. People invited before it who have not paid yet get the joining points
(1000, REFERRAL_BONUS_POINTS) now, as new invited people do on joining.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bonus_balance", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("bonus_used", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE users SET bonus_balance = 1000 "
               "WHERE referred_by IS NOT NULL AND referral_rewarded_at IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("invoices") as b:
        b.drop_column("bonus_used")
    with op.batch_alter_table("users") as b:
        b.drop_column("bonus_balance")
