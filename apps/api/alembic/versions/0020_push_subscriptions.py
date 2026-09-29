"""push subscriptions: browsers and installed apps that receive web push notifications

- push_subscriptions: one row per device (the push service endpoint and its keys), owned by a person;
  a subscription the push service reports gone (404 / 410) is deleted

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(1024), nullable=False),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
