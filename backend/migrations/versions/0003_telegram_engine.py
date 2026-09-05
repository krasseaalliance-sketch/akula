"""Add the Stage 2 Telegram Engine core schema."""

from alembic import op
from app.models import Base
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, false, inspect

revision = "0003_telegram_engine"
down_revision = "0002_enum_integrity"
branch_labels = None
depends_on = None


ADDITIONS = {
    "campaigns": [Column("communication_profile", JSON(), nullable=True)],
    "communities": [
        Column("rules_url", String(500), nullable=True),
        Column("allowed_content_types", JSON(), nullable=True),
        Column("allowed_days", JSON(), nullable=True),
        Column("min_interval_hours", Integer(), nullable=True),
        Column("valid_from", DateTime(), nullable=True),
        Column("valid_until", DateTime(), nullable=True),
        Column("evidence", Text(), nullable=True),
        Column("evidence_url", String(500), nullable=True),
        Column("notes", Text(), nullable=True),
    ],
    "community_permissions": [
        Column("allowed_content_types", JSON(), nullable=True),
        Column("allowed_days", JSON(), nullable=True),
        Column("min_interval_hours", Integer(), nullable=True),
        Column("evidence", Text(), nullable=True),
        Column("reviewed_at", DateTime(), nullable=True),
        Column("reviewed_by", String(36), nullable=True),
    ],
    "leads": [
        Column("score_breakdown", JSON(), nullable=True),
        Column("matched_signals", JSON(), nullable=True),
        Column("excluded_signals", JSON(), nullable=True),
        Column("explanation", Text(), nullable=True),
        Column("recommended_action", String(200), nullable=True),
        Column("can_reply_publicly", Boolean(), nullable=False, server_default=false()),
        Column("contact_initiated", Boolean(), nullable=False, server_default=false()),
        Column("direct_message_allowed", Boolean(), nullable=False, server_default=false()),
        Column("model_version", String(80), nullable=True),
        Column("evaluated_at", DateTime(), nullable=True),
    ],
    "message_drafts": [Column("publication_type", String(64), nullable=False, server_default="OTHER")],
    "integration_accounts": [
        Column("account_type", String(32), nullable=True),
        Column("authorization_status", String(40), nullable=True),
        Column("safety_status", String(40), nullable=True),
        Column("connection_status", String(40), nullable=True),
        Column("phone_masked", String(40), nullable=True),
        Column("last_health_check_at", DateTime(), nullable=True),
        Column("flood_wait_until", DateTime(), nullable=True),
    ],
}


NEW_TABLES = [
    "telegram_account_profiles", "telegram_authorization_attempts", "telegram_dialogs",
    "telegram_community_snapshots", "telegram_message_records", "telegram_sync_cursors",
    "telegram_account_incidents", "telegram_publication_results", "discovery_profiles",
    "telegram_discovery_runs", "telegram_community_candidates", "telegram_rule_analyses",
    "telegram_import_runs", "telegram_attributions",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table_name, columns in ADDITIONS.items():
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table_name, column)
    # create_all is deliberately limited to new tables; existing Stage 1 tables are preserved.
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in NEW_TABLES])

    if bind.dialect.name != "sqlite":
        # Stage 2 needs a review state when rules change; do not silently leave the Stage 1 check.
        op.execute('ALTER TABLE "community_permissions" DROP CONSTRAINT IF EXISTS "ck_community_permissions_status"')
        op.execute(
            'ALTER TABLE "community_permissions" ADD CONSTRAINT "ck_community_permissions_status" '
            "CHECK (\"status\" IN ('ACTIVE', 'INACTIVE', 'REVIEW_REQUIRED', 'EXPIRED'))"
        )
        op.create_index("ix_publications_sent_at", "publications", ["sent_at"], unique=False)
        op.create_index("ix_telegram_publications_imported_at", "telegram_message_records", ["imported_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_index("ix_telegram_publications_imported_at", table_name="telegram_message_records")
        op.drop_index("ix_publications_sent_at", table_name="publications")
        op.execute('ALTER TABLE "community_permissions" DROP CONSTRAINT IF EXISTS "ck_community_permissions_status"')
        op.execute(
            'ALTER TABLE "community_permissions" ADD CONSTRAINT "ck_community_permissions_status" '
            "CHECK (\"status\" IN ('ACTIVE', 'INACTIVE', 'ARCHIVED'))"
        )
    for table_name in reversed(NEW_TABLES):
        op.drop_table(table_name)
    for table_name, columns in reversed(list(ADDITIONS.items())):
        for column in reversed(columns):
            op.drop_column(table_name, column.name)
