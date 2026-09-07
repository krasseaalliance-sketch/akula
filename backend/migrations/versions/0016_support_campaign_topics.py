"""Allow one support forum topic per customer campaign."""
import sqlalchemy as sa
from alembic import op

revision = "0016_support_campaign_topics"
down_revision = "0015_support_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        # PostgreSQL cannot recreate this table with Alembic batch mode while
        # support_messages still references support_threads' primary-key
        # index. Alter the table in place and keep that FK untouched.
        op.add_column("support_threads", sa.Column("campaign_id", sa.String(36), nullable=True))
        op.add_column("support_threads", sa.Column("topic_title", sa.String(240), nullable=True))
        op.create_foreign_key(
            "fk_support_threads_campaign_id", "support_threads", "product_campaigns", ["campaign_id"], ["id"]
        )
        op.create_index("ix_support_threads_campaign_id", "support_threads", ["campaign_id"])
        op.drop_constraint("uq_support_threads_workspace_user", "support_threads", type_="unique")
        op.create_unique_constraint(
            "uq_support_threads_workspace_user_campaign", "support_threads", ["workspace_id", "user_id", "campaign_id"]
        )
        return

    with op.batch_alter_table("support_threads", recreate="always") as batch:
        batch.add_column(sa.Column("campaign_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("topic_title", sa.String(240), nullable=True))
        batch.create_foreign_key("fk_support_threads_campaign_id", "product_campaigns", ["campaign_id"], ["id"])
        batch.create_index("ix_support_threads_campaign_id", ["campaign_id"])
        batch.drop_constraint("uq_support_threads_workspace_user", type_="unique")
        batch.create_unique_constraint("uq_support_threads_workspace_user_campaign", ["workspace_id", "user_id", "campaign_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("uq_support_threads_workspace_user_campaign", "support_threads", type_="unique")
        op.create_unique_constraint("uq_support_threads_workspace_user", "support_threads", ["workspace_id", "user_id"])
        op.drop_index("ix_support_threads_campaign_id", table_name="support_threads")
        op.drop_constraint("fk_support_threads_campaign_id", "support_threads", type_="foreignkey")
        op.drop_column("support_threads", "topic_title")
        op.drop_column("support_threads", "campaign_id")
        return

    with op.batch_alter_table("support_threads", recreate="always") as batch:
        batch.drop_constraint("uq_support_threads_workspace_user_campaign", type_="unique")
        batch.create_unique_constraint("uq_support_threads_workspace_user", ["workspace_id", "user_id"])
        batch.drop_index("ix_support_threads_campaign_id")
        batch.drop_column("topic_title")
        batch.drop_column("campaign_id")
