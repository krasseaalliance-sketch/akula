"""Add direct Telegram message references to leads.

Revision ID: 0009_lead_message_links
Revises: 0008_service_schedulers
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_lead_message_links"
down_revision = "0008_service_schedulers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("source_message_id", sa.String(length=200), nullable=True))
    op.add_column("leads", sa.Column("source_dialog_external_id", sa.String(length=200), nullable=True))
    op.add_column("leads", sa.Column("source_message_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "source_message_url")
    op.drop_column("leads", "source_dialog_external_id")
    op.drop_column("leads", "source_message_id")
