"""Add Stage 3.2.1 manual Telegram dialog triage."""

from alembic import op
from app.models import Base

revision = "0007_manual_dialog_triage"
down_revision = "0006_campaign_intelligence"
branch_labels = None
depends_on = None

TABLES = [
    "dialog_triage_decisions",
    "dialog_triage_collection_definitions",
    "dialog_triage_collections",
    "dialog_triage_tag_definitions",
    "dialog_triage_tags",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES])


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.drop_table(table_name)
