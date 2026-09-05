"""Add Stage 3.2 Campaign Intelligence persistence."""

from alembic import op
from app.models import Base

revision = "0006_campaign_intelligence"
down_revision = "0005_stage3_1_human_writing"
branch_labels = None
depends_on = None

TABLES = [
    "campaign_audience_profiles",
    "campaign_intelligence_runs",
    "campaign_community_scores",
    "campaign_cost_records",
    "campaign_learning_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES])


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.drop_table(table_name)
