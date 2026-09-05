"""Add customer support threads and Telegram forwarding state."""
import sqlalchemy as sa
from alembic import op

revision = "0015_support_chat"
down_revision = "0014_stage4_customer_product"
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", sa.String(length=36), primary_key=True)


def _timestamps():
    return [sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False)]


def upgrade() -> None:
    op.create_table("support_threads", _id(), *_timestamps(), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"), sa.Column("telegram_chat_id", sa.String(200)), sa.Column("telegram_thread_id", sa.String(200)), sa.Column("last_message_at", sa.DateTime()), sa.UniqueConstraint("workspace_id", "user_id", name="uq_support_threads_workspace_user"))
    op.create_index("ix_support_threads_workspace_id", "support_threads", ["workspace_id"])
    op.create_index("ix_support_threads_user_id", "support_threads", ["user_id"])
    op.create_table("support_messages", _id(), *_timestamps(), sa.Column("thread_id", sa.String(36), sa.ForeignKey("support_threads.id"), nullable=False), sa.Column("sender_type", sa.String(32), nullable=False, server_default="CUSTOMER"), sa.Column("sender_id", sa.String(36), sa.ForeignKey("users.id")), sa.Column("content", sa.Text(), nullable=False), sa.Column("telegram_status", sa.String(40), nullable=False, server_default="NOT_CONFIGURED"), sa.Column("telegram_message_id", sa.String(200)), sa.Column("telegram_error", sa.String(240)))
    op.create_index("ix_support_messages_thread_id", "support_messages", ["thread_id"])
    op.create_index("ix_support_messages_sender_id", "support_messages", ["sender_id"])


def downgrade() -> None:
    op.drop_table("support_messages")
    op.drop_table("support_threads")
