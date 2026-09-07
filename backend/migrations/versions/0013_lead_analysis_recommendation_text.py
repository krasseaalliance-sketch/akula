"""Allow long lead intelligence recommendations."""

from alembic import op
import sqlalchemy as sa


revision = "0013_lead_analysis_rec_text"
down_revision = "0012_lead_recommendation_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column("lead_intelligence_analyses", "recommendation", existing_type=sa.String(length=40), type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column("lead_intelligence_analyses", "recommendation", existing_type=sa.Text(), type_=sa.String(length=40), existing_nullable=True)
