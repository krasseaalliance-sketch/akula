"""Store the original MAX timestamp for stable ledger work dates."""
import sqlalchemy as sa
from alembic import op

revision = "0019_asmet_message_sent_at"
down_revision = "0018_asmet_message_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("constructive_asmet_messages", sa.Column("sent_at", sa.DateTime(), nullable=True))
    op.create_index("ix_constructive_asmet_messages_sent_at", "constructive_asmet_messages", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_constructive_asmet_messages_sent_at", table_name="constructive_asmet_messages")
    op.drop_column("constructive_asmet_messages", "sent_at")
