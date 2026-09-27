"""lawyers tied to ЭЦП, case assignment, customer–lawyer agreements signed by both

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lawyer_applications", schema=None) as b:
        b.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("iin_hash", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("ecp_name", sa.String(length=200), nullable=True))
        b.create_index("ix_lawyer_applications_user_id", ["user_id"])
        b.create_foreign_key("fk_lawyer_applications_user_id", "users", ["user_id"], ["id"])

    with op.batch_alter_table("cases", schema=None) as b:
        b.add_column(sa.Column("lawyer_user_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("lawyer_application_id", sa.Integer(), nullable=True))
        b.create_index("ix_cases_lawyer_user_id", ["lawyer_user_id"])
        b.create_foreign_key("fk_cases_lawyer_user_id", "users", ["lawyer_user_id"], ["id"])
        b.create_foreign_key("fk_cases_lawyer_application_id", "lawyer_applications", ["lawyer_application_id"], ["id"])

    op.create_table(
        "agreements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("lawyer_application_id", sa.Integer(), nullable=False),
        sa.Column("docx_key", sa.String(length=300), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("template_reviewed", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["lawyer_application_id"], ["lawyer_applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agreements_case_id", "agreements", ["case_id"])

    with op.batch_alter_table("document_signatures", schema=None) as b:
        b.alter_column("action_id", existing_type=sa.Uuid(), nullable=True)
        b.add_column(sa.Column("agreement_id", sa.Uuid(), nullable=True))
        b.create_index("ix_document_signatures_agreement_id", ["agreement_id"])
        b.create_foreign_key("fk_document_signatures_agreement_id", "agreements", ["agreement_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("document_signatures", schema=None) as b:
        b.drop_constraint("fk_document_signatures_agreement_id", type_="foreignkey")
        b.drop_index("ix_document_signatures_agreement_id")
        b.drop_column("agreement_id")
        b.alter_column("action_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index("ix_agreements_case_id", table_name="agreements")
    op.drop_table("agreements")
    with op.batch_alter_table("cases", schema=None) as b:
        b.drop_constraint("fk_cases_lawyer_application_id", type_="foreignkey")
        b.drop_constraint("fk_cases_lawyer_user_id", type_="foreignkey")
        b.drop_index("ix_cases_lawyer_user_id")
        b.drop_column("lawyer_application_id")
        b.drop_column("lawyer_user_id")
    with op.batch_alter_table("lawyer_applications", schema=None) as b:
        b.drop_constraint("fk_lawyer_applications_user_id", type_="foreignkey")
        b.drop_index("ix_lawyer_applications_user_id")
        b.drop_column("ecp_name")
        b.drop_column("iin_hash")
        b.drop_column("user_id")
