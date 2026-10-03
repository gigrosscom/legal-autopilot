"""ЭЦП signatures over prepared documents

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_signatures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("signer_user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("display", sa.String(length=120), nullable=False),
        sa.Column("signer_name", sa.String(length=200), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("file_format", sa.String(length=8), nullable=False),
        sa.Column("doc_sha256", sa.String(length=64), nullable=False),
        sa.Column("cms_key", sa.String(length=300), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["signer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_signatures_case_id", "document_signatures", ["case_id"])
    op.create_index("ix_document_signatures_action_id", "document_signatures", ["action_id"])


def downgrade() -> None:
    op.drop_index("ix_document_signatures_action_id", table_name="document_signatures")
    op.drop_index("ix_document_signatures_case_id", table_name="document_signatures")
    op.drop_table("document_signatures")
