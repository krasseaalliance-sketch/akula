"""Store community ranking and join state for daily discovery."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0010_community_rank_join"
down_revision = "0009_lead_message_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("telegram_community_candidates")}
    additions = {
        "member_count": sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        "rank_score": sa.Column("rank_score", sa.Float(), nullable=False, server_default="0"),
        "rank_position": sa.Column("rank_position", sa.Integer(), nullable=True),
        "join_status": sa.Column("join_status", sa.String(length=32), nullable=False, server_default="NOT_ATTEMPTED"),
        "joined_at": sa.Column("joined_at", sa.DateTime(), nullable=True),
        "join_error": sa.Column("join_error", sa.Text(), nullable=True),
    }
    for name, column in additions.items():
        if name not in existing:
            op.add_column("telegram_community_candidates", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("telegram_community_candidates")}
    for name in ("join_error", "joined_at", "join_status", "rank_position", "rank_score", "member_count"):
        if name in existing:
            op.drop_column("telegram_community_candidates", name)
