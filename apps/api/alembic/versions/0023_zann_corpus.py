"""zann corpus: acts of old.adilet.zan.kz found for the Zann law corpus, their stored texts, discovery progress

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zann_acts",
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("act_type", sa.String(8), nullable=False, server_default=""),
        sa.Column("status", sa.String(8), nullable=False, server_default=""),
        sa.Column("info", sa.String(1000), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("state", sa.String(8), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index("ix_zann_acts_queue", "zann_acts", ["state", "priority", "code"])
    op.create_index("ix_zann_acts_fetched_at", "zann_acts", ["fetched_at"])
    op.create_table(
        "zann_files",
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("lang", sa.String(2), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("code", "lang"),
    )
    op.create_table(
        "zann_listings",
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("act_type", sa.String(8), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("next_page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("zann_listings")
    op.drop_table("zann_files")
    op.drop_index("ix_zann_acts_fetched_at", "zann_acts")
    op.drop_index("ix_zann_acts_queue", "zann_acts")
    op.drop_table("zann_acts")
