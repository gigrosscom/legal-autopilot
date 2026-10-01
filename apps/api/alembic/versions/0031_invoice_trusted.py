"""Invoice.trusted_at — Kaspi Pay link paid «on trust» (owner 01.10): «Оплатить» opens Kaspi and the document is given
at once; the bill waits for the clients desk to match it in Kaspi Pay. Not found → the person owes it and gets no
new document until it is paid.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("trusted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "trusted_at")
