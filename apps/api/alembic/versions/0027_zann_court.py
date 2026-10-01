"""zann court practice: sud.kz pages walked and the court-practice documents found (normative resolutions,
practice reviews, bulletins of the Supreme Court; court acts imported from a lawful export)

Revises 0025, the latest on the deploy branch. PR #119 (not merged) adds 0026_filings (down 0025): if it merges
first, this revision's down_revision must become "0026".

Revision ID: 0027
Revises: 0025
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zann_court_pages",
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False, server_default="leaf"),
        sa.Column("label", sa.String(300), nullable=True),
        sa.Column("state", sa.String(8), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("url"),
    )
    op.create_table(
        "zann_court_docs",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("court", sa.String(200), nullable=True),
        sa.Column("category", sa.String(16), nullable=False, server_default="other"),
        sa.Column("doc_date", sa.String(32), nullable=True),
        sa.Column("number", sa.String(64), nullable=True),
        sa.Column("lang", sa.String(8), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="99"),
        sa.Column("state", sa.String(8), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("mime", sa.String(100), nullable=True),
        sa.Column("key", sa.String(255), nullable=True),
        sa.Column("text_key", sa.String(255), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zann_court_docs_queue", "zann_court_docs", ["state", "priority", "id"])


def downgrade() -> None:
    op.drop_index("ix_zann_court_docs_queue", "zann_court_docs")
    op.drop_table("zann_court_docs")
    op.drop_table("zann_court_pages")
