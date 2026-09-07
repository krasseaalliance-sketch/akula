"""Add manually controlled Core agent runs."""

import sqlalchemy as sa
from alembic import op


revision = "0023_core_day3_runs"
down_revision = "0022_core_day3_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "core_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("core_projects.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("core_tasks.id"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("core_agents.id"), nullable=False),
        sa.Column("initiated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')", name="ck_core_runs_status"),
    )
    for column in ("workspace_id", "project_id", "task_id", "agent_id", "status", "queued_at"):
        op.create_index(f"ix_core_runs_{column}", "core_runs", [column])


def downgrade() -> None:
    op.drop_table("core_runs")
