"""Create the Stage 1 domain schema."""

from alembic import op
from app.models import Base
from sqlalchemy import Boolean, Column, DateTime, String, inspect, text

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

INITIAL_TABLES = [
    "users",
    "workspaces",
    "workspace_members",
    "companies",
    "brands",
    "offers",
    "campaigns",
    "audiences",
    "communities",
    "community_permissions",
    "leads",
    # These tables are referenced by the current message_drafts model.  Keep
    # their dependency order here so a fresh PostgreSQL database can create
    # the initial table set without referring to a table from a later batch.
    "community_style_profiles",
    "human_writing_runs",
    "human_writing_variants",
    "message_drafts",
    "publications",
    "publication_jobs",
    "conversations",
    "conversation_messages",
    "integration_accounts",
    "audit_events",
    "system_state",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Alembic's default VARCHAR(32) cannot store the current 0025
        # revision identifier.
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=String(32),
            type_=String(128),
            existing_nullable=False,
        )
    Base.metadata.create_all(
        bind=bind,
        tables=[Base.metadata.tables[name] for name in INITIAL_TABLES],
    )
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
