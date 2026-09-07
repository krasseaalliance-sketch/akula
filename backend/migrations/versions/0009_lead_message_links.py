"""Add direct Telegram message references to leads.

Revision ID: 0009_lead_message_links
Revises: 0008_service_schedulers
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0009_lead_message_links"
down_revision = "0008_service_schedulers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("leads")}
    additions = {
        "source_message_id": sa.String(length=200),
        "source_dialog_external_id": sa.String(length=200),
        "source_message_url": sa.String(length=500),
    }
    for name, column_type in additions.items():
        if name not in existing:
            op.add_column("leads", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("leads")}
    for name in ("source_message_url", "source_dialog_external_id", "source_message_id"):
        if name in existing:
            op.drop_column("leads", name)
