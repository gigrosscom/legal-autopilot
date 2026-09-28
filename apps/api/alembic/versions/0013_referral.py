"""referral programme: invite code, inviter and acquisition channel per user

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("ref_code", sa.String(12), nullable=True))
        b.add_column(sa.Column("referred_by", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("source", sa.String(40), nullable=True))
        b.create_foreign_key("fk_users_referred_by", "users", ["referred_by"], ["id"])
    op.create_index("ix_users_ref_code", "users", ["ref_code"], unique=True)
    op.create_index("ix_users_referred_by", "users", ["referred_by"])


def downgrade() -> None:
    op.drop_index("ix_users_referred_by", table_name="users")
    op.drop_index("ix_users_ref_code", table_name="users")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("fk_users_referred_by", type_="foreignkey")
        b.drop_column("source")
        b.drop_column("referred_by")
        b.drop_column("ref_code")
