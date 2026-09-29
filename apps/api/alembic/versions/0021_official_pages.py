"""official pages: the nightly-refreshed library of official pages the consultation chat searches

- official_pages: one row per page of an allowed official domain (url unique), its extracted text, content hash,
  ETag / Last-Modified for the conditional GET, when it was fetched and when its text last changed, status
- official_chunks: the page split by headings; on PostgreSQL a generated tsvector column (the 'russian'
  configuration for Russian text, 'simple' for other languages) with a GIN index serves full-text search

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "official_pages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("topic", sa.String(64), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("lang", sa.String(8), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("etag", sa.String(255), nullable=True),
        sa.Column("last_modified", sa.String(64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_official_pages_country", "official_pages", ["country"])
    op.create_index("ix_official_pages_domain", "official_pages", ["domain"])
    op.create_index("ix_official_pages_fetched_at", "official_pages", ["fetched_at"])
    op.create_table(
        "official_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("lang", sa.String(8), nullable=True),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["official_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_official_chunks_page_id", "official_chunks", ["page_id"])
    op.create_index("ix_official_chunks_country", "official_chunks", ["country"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE official_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector("
            "CASE WHEN lang = 'ru' THEN 'russian'::regconfig ELSE 'simple'::regconfig END, "
            "coalesce(heading, '') || ' ' || text)) STORED")
        op.execute("CREATE INDEX ix_official_chunks_tsv ON official_chunks USING gin (tsv)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_official_chunks_tsv")
    op.drop_index("ix_official_chunks_country", table_name="official_chunks")
    op.drop_index("ix_official_chunks_page_id", table_name="official_chunks")
    op.drop_table("official_chunks")
    op.drop_index("ix_official_pages_fetched_at", table_name="official_pages")
    op.drop_index("ix_official_pages_domain", table_name="official_pages")
    op.drop_index("ix_official_pages_country", table_name="official_pages")
    op.drop_table("official_pages")
