"""Add named CHECK constraints for controlled string fields."""

from alembic import op
from app.enum_values import CHECKS, sql_check
from sqlalchemy import inspect

revision = "0002_enum_integrity"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite creates the checks from Base.metadata in the initial migration.
        return
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name, column_name, constraint_name, allowed_values in CHECKS:
        if table_name not in existing_tables:
            continue
        existing = {item["name"] for item in inspector.get_check_constraints(table_name)}
        if constraint_name not in existing:
            op.execute(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                f"CHECK ({sql_check(column_name, allowed_values)})"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    existing_tables = set(inspect(bind).get_table_names())
    for table_name, _column_name, constraint_name, _allowed_values in reversed(CHECKS):
        if table_name not in existing_tables:
            continue
        op.execute(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')
