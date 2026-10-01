"""zann articles: the collected adilet acts split into articles for the Zann search («ищет и цитирует»)

- zann_articles: one row per article (or piece of an act without articles): act code, language, number, heading,
  text, act title / type / status, adilet URL; optional embedding (float16 bytes) and its model; on PostgreSQL a
  generated tsvector column (the 'russian' configuration for ru, 'simple' for kk) with a GIN index
- zann_indexed: which sha256 of each corpus file is indexed (incremental re-indexing)

Numbered 0028: 0026 and 0027 are taken by migrations on other branches (claude/team-delivery,
claude/team-eotinish-bridge). Whichever lands later on the deploy branch must set its down_revision to the
previous head so the chain stays linear.

Revision ID: 0028
Revises: 0025
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zann_articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("lang", sa.String(2), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(16), nullable=False, server_default=""),
        sa.Column("heading", sa.String(500), nullable=True),
        sa.Column("act_title", sa.String(1000), nullable=True),
        sa.Column("act_type", sa.String(8), nullable=False, server_default=""),
        sa.Column("status", sa.String(8), nullable=False, server_default=""),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("emb_model", sa.String(32), nullable=True),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zann_articles_code_lang", "zann_articles", ["code", "lang", "number"])
    op.create_index("ix_zann_articles_number", "zann_articles", ["number"])
    op.create_index("ix_zann_articles_emb_model", "zann_articles", ["emb_model"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE zann_articles ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector("
            "CASE WHEN lang = 'ru' THEN 'russian'::regconfig ELSE 'simple'::regconfig END, "
            "coalesce(heading, '') || ' ' || text)) STORED")
        op.execute("CREATE INDEX ix_zann_articles_tsv ON zann_articles USING gin (tsv)")
    op.create_table(
        "zann_indexed",
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("lang", sa.String(2), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default=""),
        sa.Column("articles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("code", "lang"),
    )


def downgrade() -> None:
    op.drop_table("zann_indexed")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_zann_articles_tsv")
    op.drop_index("ix_zann_articles_emb_model", table_name="zann_articles")
    op.drop_index("ix_zann_articles_number", table_name="zann_articles")
    op.drop_index("ix_zann_articles_code_lang", table_name="zann_articles")
    op.drop_table("zann_articles")
