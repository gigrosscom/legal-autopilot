"""Deliveries — «Доставить курьером» (konsilier/courier, pilot «Курьер», owner 01.10.2026): the pickup from the client,
the hand-delivery to the addressee against a signature and the return of the second copy, with the provider's order,
tracking number, statuses and event log. Paid by a bill with invoices.purpose = "delivery" (no new column there).

Numbered 0032 and revising 0030 (the deploy branch head) on purpose: «Kaspi one tap» (branch claude/team-kaspi-onetap)
adds 0031_invoice_trusted, also on 0030. Either can be merged first; with both in, `alembic upgrade heads`
(Dockerfile) applies the two heads. For a single head once 0031 is merged: set down_revision = "0031" here.

Revision ID: 0032
Revises: 0030
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0030"
branch_labels = None
depends_on = None

INDEXED = ("case_id", "action_id", "user_id", "invoice_id", "status", "external_id")


def upgrade() -> None:
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("action_id", sa.Uuid(), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("filing_id", sa.Uuid(), sa.ForeignKey("filings.id"), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("city", sa.String(32), nullable=False),
        sa.Column("pickup_address", sa.String(500), nullable=False),
        sa.Column("pickup_date", sa.Date(), nullable=False),
        sa.Column("pickup_from", sa.String(5), nullable=False),
        sa.Column("pickup_to", sa.String(5), nullable=False),
        sa.Column("contact_name", sa.String(200), nullable=False),
        sa.Column("contact_phone", sa.String(20), nullable=False),
        sa.Column("recipient_name", sa.String(500), nullable=False),
        sa.Column("recipient_address", sa.String(500), nullable=False),
        sa.Column("recipient_phone", sa.String(20), nullable=True),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("tracking", sa.String(100), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signer_name", sa.String(200), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in INDEXED:
        op.create_index(f"ix_deliveries_{col}", "deliveries", [col])


def downgrade() -> None:
    for col in reversed(INDEXED):
        op.drop_index(f"ix_deliveries_{col}", table_name="deliveries")
    op.drop_table("deliveries")
