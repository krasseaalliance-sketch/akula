"""Store community ranking and join state for daily discovery."""

from alembic import op
import sqlalchemy as sa


revision = "0010_community_rank_join"
down_revision = "0009_lead_message_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("telegram_community_candidates", sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("telegram_community_candidates", sa.Column("rank_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("telegram_community_candidates", sa.Column("rank_position", sa.Integer(), nullable=True))
    op.add_column("telegram_community_candidates", sa.Column("join_status", sa.String(length=32), nullable=False, server_default="NOT_ATTEMPTED"))
    op.add_column("telegram_community_candidates", sa.Column("joined_at", sa.DateTime(), nullable=True))
    op.add_column("telegram_community_candidates", sa.Column("join_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("telegram_community_candidates", "join_error")
    op.drop_column("telegram_community_candidates", "joined_at")
    op.drop_column("telegram_community_candidates", "join_status")
    op.drop_column("telegram_community_candidates", "rank_position")
    op.drop_column("telegram_community_candidates", "rank_score")
    op.drop_column("telegram_community_candidates", "member_count")
