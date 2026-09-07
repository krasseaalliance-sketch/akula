"""Widen AI first-contact recommendation values."""

from alembic import op
import sqlalchemy as sa


revision = "0011_widen_lead_recommendation"
down_revision = "0010_community_rank_join"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "leads",
        "first_contact_recommendation",
        existing_type=sa.String(length=40),
        type_=sa.String(length=120),
        existing_nullable=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "leads",
        "first_contact_recommendation",
        existing_type=sa.String(length=120),
        type_=sa.String(length=40),
        existing_nullable=True,
    )
