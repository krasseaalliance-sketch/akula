"""Create the Stage 1 domain schema."""

from alembic import op
from app.models import Base
from sqlalchemy import Boolean, Column, DateTime, String, inspect, text

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    inspector = inspect(bind)
    additions = {
        "leads": [("dedupe_key", String(128), True)],
        "message_drafts": [("audience_id", String(36), True)],
        "publications": [
            ("queued_at", DateTime(), True),
            ("sent_at", DateTime(), True),
            ("dry_run", Boolean(), False),
        ],
        "integration_accounts": [("safety_lock", Boolean(), False)],
        "audit_events": [("event_hash", String(128), True)],
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, column_type, nullable in columns:
            if name not in existing:
                default = (
                    text("false") if not nullable and isinstance(column_type, Boolean) else None
                )
                op.add_column(
                    table, Column(name, column_type, nullable=nullable, server_default=default)
                )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
