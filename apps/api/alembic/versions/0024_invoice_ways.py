"""invoices: the way to pay the person chose (Kaspi link / QR / Kaspi bill / bank invoice) and, for a Kaspi bill or
«Счёт на оплату», the payer's phone or company

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("pay_way", sa.String(24), nullable=True))
    op.add_column("invoices", sa.Column("payer_phone", sa.String(20), nullable=True))
    op.add_column("invoices", sa.Column("buyer_name", sa.String(300), nullable=True))
    op.add_column("invoices", sa.Column("buyer_bin", sa.String(12), nullable=True))
    op.add_column("invoices", sa.Column("buyer_address", sa.String(300), nullable=True))


def downgrade() -> None:
    for col in ("buyer_address", "buyer_bin", "buyer_name", "payer_phone", "pay_way"):
        op.drop_column("invoices", col)
