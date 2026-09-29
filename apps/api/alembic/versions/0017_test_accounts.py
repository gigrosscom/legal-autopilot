"""test accounts: users.is_test — production smoke checks run as a marked user whose cases stay out of the
metrics and the operations centre and never notify the team

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_is_test", "users", ["is_test"])


def downgrade() -> None:
    op.drop_index("ix_users_is_test", "users")
    op.drop_column("users", "is_test")
