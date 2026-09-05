"""Add Stage 3.1 human writing and automatic community classification persistence."""

from alembic import op
from app.models import Base
from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, String, Text, inspect

revision = "0005_stage3_1_human_writing"
down_revision = "0004_stage3_intelligence"
branch_labels = None
depends_on = None


ADDITIONS = {
    "communities": [
        Column("region", String(120), nullable=True),
        Column("ai_tags", JSON(), nullable=True),
        Column("classification_status", String(32), nullable=False, server_default="AUTO_CLASSIFIED"),
        Column("classification_source", String(32), nullable=False, server_default="AUTO"),
        Column("manual_classification_override", Boolean(), nullable=False, server_default="false"),
        Column("classification_confidence", Float(), nullable=False, server_default="0"),
        Column("classification_reason", Text(), nullable=True),
    ],
    "message_drafts": [
        Column("human_writing_run_id", String(36), ForeignKey("human_writing_runs.id"), nullable=True),
        Column("human_variant_id", String(36), ForeignKey("human_writing_variants.id"), nullable=True),
        Column("naturalness_score", Float(), nullable=True),
        Column("human_similarity_score", Float(), nullable=True),
        Column("human_critic", JSON(), nullable=True),
    ],
}

NEW_TABLES = [
    "community_collections",
    "community_collection_memberships",
    "community_tags",
    "community_tag_memberships",
    "community_style_profiles",
    "human_writing_runs",
    "human_writing_variants",
    "human_writing_style_memory",
    "human_writing_style_evolution",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in NEW_TABLES])
    inspector = inspect(bind)
    for table_name, columns in ADDITIONS.items():
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table_name, column)


def downgrade() -> None:
    for table_name, columns in reversed(list(ADDITIONS.items())):
        for column in reversed(columns):
            op.drop_column(table_name, column.name)
    for table_name in reversed(NEW_TABLES):
        op.drop_table(table_name)
