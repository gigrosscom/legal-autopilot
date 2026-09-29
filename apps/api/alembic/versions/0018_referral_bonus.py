"""referral bonus: when an invited person pays for the first time, both they and the inviter get one free document

- users.bonus_documents: free documents not used yet (for any case of the person)
- users.referral_rewarded_at: when the invited person's first payment credited the bonus (it is credited once)

Revision ID: 0018
Revises: 0016
Create Date: 2026-09-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bonus_documents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("referral_rewarded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("referral_rewarded_at")
        b.drop_column("bonus_documents")
