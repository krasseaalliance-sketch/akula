"""Add Constructive organizations, cabinets and ledger entities."""
import sqlalchemy as sa
from alembic import op

revision = "0017_constructive_domain"
down_revision = "0016_support_campaign_topics"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table("constructive_organizations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), *_timestamps())
    op.create_index("ix_constructive_organizations_workspace_id", "constructive_organizations", ["workspace_id"], unique=True)
    op.create_table("constructive_objects", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("address", sa.String(500)), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), *_timestamps())
    op.create_index("ix_constructive_objects_organization_id", "constructive_objects", ["organization_id"])
    op.create_table("constructive_object_assignments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("object_id", sa.String(36), sa.ForeignKey("constructive_objects.id"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("role", sa.String(32), nullable=False, server_default="WORKER"), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), *_timestamps())
    op.create_unique_constraint("uq_constructive_object_user", "constructive_object_assignments", ["object_id", "user_id"])
    op.create_index("ix_constructive_object_assignments_organization_id", "constructive_object_assignments", ["organization_id"])
    op.create_index("ix_constructive_object_assignments_object_id", "constructive_object_assignments", ["object_id"])
    op.create_index("ix_constructive_object_assignments_user_id", "constructive_object_assignments", ["user_id"])
    op.create_table("constructive_employees", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")), sa.Column("full_name", sa.String(200), nullable=False), sa.Column("telegram_username", sa.String(160)), sa.Column("role", sa.String(32), nullable=False, server_default="WORKER"), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), *_timestamps())
    op.create_unique_constraint("uq_constructive_employee_user", "constructive_employees", ["organization_id", "user_id"])
    op.create_index("ix_constructive_employees_organization_id", "constructive_employees", ["organization_id"])
    op.create_index("ix_constructive_employees_user_id", "constructive_employees", ["user_id"])
    op.create_table("constructive_warehouses", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("address", sa.String(500)), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), *_timestamps())
    op.create_index("ix_constructive_warehouses_organization_id", "constructive_warehouses", ["organization_id"])
    op.create_table("constructive_rates", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("employee_id", sa.String(36), sa.ForeignKey("constructive_employees.id"), nullable=False), sa.Column("object_id", sa.String(36), sa.ForeignKey("constructive_objects.id")), sa.Column("work_type", sa.String(160), nullable=False), sa.Column("amount", sa.Float(), nullable=False), sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"), sa.Column("valid_from", sa.DateTime()), sa.Column("valid_to", sa.DateTime()), *_timestamps())
    op.create_unique_constraint("uq_constructive_rate_key", "constructive_rates", ["organization_id", "employee_id", "object_id", "work_type"])
    op.create_index("ix_constructive_rates_organization_id", "constructive_rates", ["organization_id"])
    op.create_index("ix_constructive_rates_employee_id", "constructive_rates", ["employee_id"])
    op.create_index("ix_constructive_rates_object_id", "constructive_rates", ["object_id"])
    op.create_table("constructive_ledger_rows", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("source_message_id", sa.String(200)), sa.Column("object_id", sa.String(36), sa.ForeignKey("constructive_objects.id"), nullable=False), sa.Column("employee_id", sa.String(36), sa.ForeignKey("constructive_employees.id"), nullable=False), sa.Column("work_date", sa.DateTime(), nullable=False), sa.Column("work_type", sa.String(160), nullable=False), sa.Column("quantity", sa.Float(), nullable=False), sa.Column("rate", sa.Float(), nullable=False), sa.Column("amount", sa.Float(), nullable=False), sa.Column("raw_line", sa.Text(), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), *_timestamps())
    for column in ("organization_id", "source_message_id", "object_id", "employee_id", "work_date"):
        op.create_index(f"ix_constructive_ledger_rows_{column}", "constructive_ledger_rows", [column])
    op.create_table("constructive_cabinets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("role", sa.String(32), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), *_timestamps())
    op.create_unique_constraint("uq_constructive_cabinet_user", "constructive_cabinets", ["organization_id", "user_id"])
    op.create_index("ix_constructive_cabinets_organization_id", "constructive_cabinets", ["organization_id"])
    op.create_index("ix_constructive_cabinets_user_id", "constructive_cabinets", ["user_id"])
    op.create_table("constructive_cabinet_invites", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("role", sa.String(32), nullable=False, server_default="MASTER"), sa.Column("token_hash", sa.String(128), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("used_at", sa.DateTime()), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False), *_timestamps())
    op.create_unique_constraint("uq_constructive_cabinet_invite_token", "constructive_cabinet_invites", ["token_hash"])
    op.create_index("ix_constructive_cabinet_invites_organization_id", "constructive_cabinet_invites", ["organization_id"])
    op.create_index("ix_constructive_cabinet_invites_email", "constructive_cabinet_invites", ["email"])


def downgrade() -> None:
    for table in ("constructive_cabinet_invites", "constructive_cabinets", "constructive_ledger_rows", "constructive_rates", "constructive_warehouses", "constructive_employees", "constructive_object_assignments", "constructive_objects", "constructive_organizations"):
        op.drop_table(table)
