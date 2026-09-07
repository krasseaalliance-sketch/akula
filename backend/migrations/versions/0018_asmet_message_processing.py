"""Add idempotent ASmeT/MAX message processing state."""
import sqlalchemy as sa
from alembic import op

revision = "0018_asmet_message_processing"
down_revision = "0017_constructive_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("constructive_asmet_messages", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("constructive_organizations.id"), nullable=False), sa.Column("external_chat_id", sa.String(200), nullable=False), sa.Column("external_message_id", sa.String(200), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("edited_at", sa.DateTime()), sa.Column("processed_at", sa.DateTime()), sa.Column("historical", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("acknowledgement_sent", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("status", sa.String(32), nullable=False, server_default="RECEIVED"), sa.Column("rejections", sa.JSON()), sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("organization_id", "external_chat_id", "external_message_id", name="uq_constructive_asmet_message_identity"))
    op.create_index("ix_constructive_asmet_messages_organization_id", "constructive_asmet_messages", ["organization_id"])
    op.create_index("ix_constructive_asmet_messages_external_chat_id", "constructive_asmet_messages", ["external_chat_id"])
    op.create_index("ix_constructive_asmet_messages_external_message_id", "constructive_asmet_messages", ["external_message_id"])


def downgrade() -> None:
    op.drop_table("constructive_asmet_messages")
