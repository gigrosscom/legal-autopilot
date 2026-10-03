"""universal coverage: coverage level, taxonomy, forum, demand signals, consents, forum drafts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.add_column(sa.Column("coverage_level", sa.String(length=16), server_default="verified",
                                      nullable=False))
        batch_op.add_column(sa.Column("taxonomy", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("forum_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("route_reasons", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("formal_demands", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("hold_reason", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_cases_coverage_level", ["coverage_level"])
        batch_op.create_index("ix_cases_hold_reason", ["hold_reason"])

    op.create_table(
        "demand_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("branch", sa.String(length=64), nullable=True),
        sa.Column("dispute_type", sa.String(length=128), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("country", "branch", "dispute_type"):
        op.create_index(f"ix_demand_signals_{col}", "demand_signals", [col])

    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consents_case_id", "consents", ["case_id"])

    op.create_table(
        "forum_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("forum_id", sa.String(length=128), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forum_drafts_country", "forum_drafts", ["country"])


def downgrade() -> None:
    op.drop_index("ix_forum_drafts_country", table_name="forum_drafts")
    op.drop_table("forum_drafts")
    op.drop_index("ix_consents_case_id", table_name="consents")
    op.drop_table("consents")
    for col in ("country", "branch", "dispute_type"):
        op.drop_index(f"ix_demand_signals_{col}", table_name="demand_signals")
    op.drop_table("demand_signals")
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.drop_index("ix_cases_hold_reason")
        batch_op.drop_index("ix_cases_coverage_level")
        for col in ("hold_reason", "formal_demands", "route_reasons", "forum_id", "taxonomy", "coverage_level"):
            batch_op.drop_column(col)
