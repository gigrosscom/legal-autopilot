"""operations centre: client questions, complaints and suggestions with replies; desk notes

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"])
    op.create_index("ix_support_tickets_created_at", "support_tickets", ["created_at"])
    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(16), nullable=False),
        sa.Column("operator", sa.String(200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_messages_ticket_id", "ticket_messages", ["ticket_id"])
    with op.batch_alter_table("lawyer_applications") as b:
        b.add_column(sa.Column("desk_note", sa.Text(), nullable=True))
    with op.batch_alter_table("lawyer_requests") as b:
        b.add_column(sa.Column("desk_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lawyer_requests") as b:
        b.drop_column("desk_note")
    with op.batch_alter_table("lawyer_applications") as b:
        b.drop_column("desk_note")
    op.drop_index("ix_ticket_messages_ticket_id", table_name="ticket_messages")
    op.drop_table("ticket_messages")
    op.drop_index("ix_support_tickets_created_at", table_name="support_tickets")
    op.drop_index("ix_support_tickets_user_id", table_name="support_tickets")
    op.drop_table("support_tickets")
