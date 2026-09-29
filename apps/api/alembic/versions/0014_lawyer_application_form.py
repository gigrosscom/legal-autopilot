"""lawyer application form: phone (+7XXXXXXXXXX, duplicate key), e-mail, rejection reason, IP hash for rate limit

Revision ID: 0014_lawyer_form
Revises: 0013
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_lawyer_form"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lawyer_applications") as b:
        b.add_column(sa.Column("phone", sa.String(16), nullable=True))
        b.add_column(sa.Column("email", sa.String(200), nullable=True))
        b.add_column(sa.Column("reject_reason", sa.Text(), nullable=True))
        b.add_column(sa.Column("ip_hash", sa.String(64), nullable=True))
    op.create_index("ix_lawyer_applications_phone", "lawyer_applications", ["phone"])
    op.create_index("ix_lawyer_applications_ip_hash", "lawyer_applications", ["ip_hash"])


def downgrade() -> None:
    op.drop_index("ix_lawyer_applications_ip_hash", table_name="lawyer_applications")
    op.drop_index("ix_lawyer_applications_phone", table_name="lawyer_applications")
    with op.batch_alter_table("lawyer_applications") as b:
        b.drop_column("ip_hash")
        b.drop_column("reject_reason")
        b.drop_column("email")
        b.drop_column("phone")
