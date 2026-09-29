"""notifications: read state for the site's bell and the channels that delivered each one

- notifications.read_at: when the person opened it in the bell (null → unread)
- notifications.sent_via: channels that delivered it ("web,email,sms")
- existing notifications count as read, so the bell does not light up with old news

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column("sent_via", sa.String(64), nullable=True))
    op.execute("UPDATE notifications SET read_at = created_at")


def downgrade() -> None:
    with op.batch_alter_table("notifications") as b:
        b.drop_column("sent_via")
        b.drop_column("read_at")
