"""Allow one support forum topic per customer campaign."""
import sqlalchemy as sa
from alembic import op

revision = "0016_support_campaign_topics"
down_revision = "0015_support_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("support_threads", recreate="always") as batch:
        batch.add_column(sa.Column("campaign_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("topic_title", sa.String(240), nullable=True))
        batch.create_foreign_key("fk_support_threads_campaign_id", "product_campaigns", ["campaign_id"], ["id"])
        batch.create_index("ix_support_threads_campaign_id", ["campaign_id"])
        batch.drop_constraint("uq_support_threads_workspace_user", type_="unique")
        batch.create_unique_constraint("uq_support_threads_workspace_user_campaign", ["workspace_id", "user_id", "campaign_id"])


def downgrade() -> None:
    with op.batch_alter_table("support_threads", recreate="always") as batch:
        batch.drop_constraint("uq_support_threads_workspace_user_campaign", type_="unique")
        batch.create_unique_constraint("uq_support_threads_workspace_user", ["workspace_id", "user_id"])
        batch.drop_index("ix_support_threads_campaign_id")
        batch.drop_column("topic_title")
        batch.drop_column("campaign_id")
