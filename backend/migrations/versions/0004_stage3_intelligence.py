"""Add Stage 3 live/AI intelligence persistence without rewriting Stage 1/2 tables."""

from alembic import op
from app.models import Base
from sqlalchemy import JSON, Column, DateTime, Float, String, Text, inspect

revision = "0004_stage3_intelligence"
down_revision = "0003_telegram_engine"
branch_labels = None
depends_on = None


ADDITIONS = {
    "communities": [
        Column("community_score", Float(), nullable=False, server_default="0"),
        Column("lead_quality_score", Float(), nullable=False, server_default="0"),
        Column("conversion_rate", Float(), nullable=False, server_default="0"),
        Column("score_breakdown", JSON(), nullable=True),
        Column("last_scored_at", DateTime(), nullable=True),
    ],
    "leads": [
        Column("intent", String(120), nullable=True),
        Column("pain", String(300), nullable=True),
        Column("need", String(300), nullable=True),
        Column("intent_confidence", Float(), nullable=False, server_default="0"),
        Column("pain_confidence", Float(), nullable=False, server_default="0"),
        Column("need_confidence", Float(), nullable=False, server_default="0"),
        Column("offer_match_id", String(36), nullable=True),
        Column("offer_match_score", Float(), nullable=False, server_default="0"),
        Column("first_contact_recommendation", String(40), nullable=True),
        Column("recommendation_reason", Text(), nullable=True),
        Column("ai_provider", String(80), nullable=True),
        Column("ai_model", String(120), nullable=True),
    ],
}

NEW_TABLES = [
    "ai_search_profiles",
    "lead_intelligence_runs",
    "lead_intelligence_analyses",
    "message_recommendations",
    "message_similarity_records",
    "community_score_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table_name, columns in ADDITIONS.items():
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table_name, column)
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in NEW_TABLES])


def downgrade() -> None:
    for table_name in reversed(NEW_TABLES):
        op.drop_table(table_name)
    for table_name, columns in reversed(list(ADDITIONS.items())):
        for column in reversed(columns):
            op.drop_column(table_name, column.name)
