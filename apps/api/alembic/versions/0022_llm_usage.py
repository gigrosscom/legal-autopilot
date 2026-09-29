"""llm_usage: every call of the paid model with its task, tokens and cost — the spend guard's daily and monthly sums

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("task", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_day", "llm_usage", ["day"])
    op.create_index("ix_llm_usage_month", "llm_usage", ["month"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_month", "llm_usage")
    op.drop_index("ix_llm_usage_day", "llm_usage")
    op.drop_table("llm_usage")
