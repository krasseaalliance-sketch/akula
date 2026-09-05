"""Allow one support forum topic per customer campaign."""
import sqlalchemy as sa
from alembic import op

revision = "0016_support_campaign_topics"
down_revision = "0015_support_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_threads", sa.Column("campaign_id", sa.String(36), sa.ForeignKey("product_campaigns.id"), nullable=True))
    op.add_column("support_threads", sa.Column("topic_title", sa.String(240), nullable=True))
    op.create_index("ix_support_threads_campaign_id", "support_threads", ["campaign_id"])
    op.drop_constraint("uq_support_threads_workspace_user", "support_threads", type_="unique")
    op.create_unique_constraint("uq_support_threads_workspace_user_campaign", "support_threads", ["workspace_id", "user_id", "campaign_id"])


def downgrade() -> None:
    op.drop_constraint("uq_support_threads_workspace_user_campaign", "support_threads", type_="unique")
    op.create_unique_constraint("uq_support_threads_workspace_user", "support_threads", ["workspace_id", "user_id"])
    op.drop_index("ix_support_threads_campaign_id", table_name="support_threads")
    op.drop_column("support_threads", "topic_title")
    op.drop_column("support_threads", "campaign_id")
