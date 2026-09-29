"""merge the two 0014 branches: document invoices (#29) and the lawyer application form (#32)

Revision ID: 0015
Revises: 0014, 0014_lawyer_form
Create Date: 2026-09-29
"""
from __future__ import annotations

revision = "0015"
down_revision = ("0014", "0014_lawyer_form")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
