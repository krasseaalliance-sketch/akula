"""Add independent Campaign Engine and Lead Hunter Monitor runtimes."""

from alembic import op
from app.models import Base

revision = "0008_service_schedulers"
down_revision = "0007_manual_dialog_triage"
branch_labels = None
depends_on = None

TABLES = ["service_runtimes", "service_logs"]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES])


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.drop_table(table_name)
