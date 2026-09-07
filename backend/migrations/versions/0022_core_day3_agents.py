"""Add agent capabilities, workload limits and assignment history."""

import sqlalchemy as sa
from alembic import op


revision = "0022_core_day3_agents"
down_revision = "0021_core_day2_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("core_agents", sa.Column("allowed_actions", sa.JSON(), nullable=True))
    op.add_column("core_agents", sa.Column("concurrency_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("core_agents", sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("core_tasks", sa.Column("required_competencies", sa.JSON(), nullable=True))
    op.create_table(
        "core_task_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("core_projects.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("core_tasks.id"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("core_agents.id"), nullable=False),
        sa.Column("assigned_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
    )
    for column in ("workspace_id", "project_id", "task_id", "agent_id", "assigned_at"):
        op.create_index(f"ix_core_task_assignments_{column}", "core_task_assignments", [column])


def downgrade() -> None:
    op.drop_table("core_task_assignments")
    op.drop_column("core_tasks", "required_competencies")
    op.drop_column("core_agents", "available")
    op.drop_column("core_agents", "concurrency_limit")
    op.drop_column("core_agents", "allowed_actions")
