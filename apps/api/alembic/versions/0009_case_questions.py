"""legal questions about a case answered from the official texts

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_questions_case_id", "case_questions", ["case_id"])
    op.create_index("ix_case_questions_created_at", "case_questions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_case_questions_created_at", table_name="case_questions")
    op.drop_index("ix_case_questions_case_id", table_name="case_questions")
    op.drop_table("case_questions")
