"""Add task deadlines and dependency edges for Core Day 2."""

import sqlalchemy as sa
from alembic import op


revision = "0021_core_day2_workflow"
down_revision = "0020_core_release1_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("core_tasks", sa.Column("due_at", sa.DateTime(), nullable=True))
    op.create_index("ix_core_tasks_due_at", "core_tasks", ["due_at"])
    op.create_table(
        "core_task_dependencies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("core_projects.id"), nullable=False),
        sa.Column("dependent_task_id", sa.String(36), sa.ForeignKey("core_tasks.id"), nullable=False),
        sa.Column("predecessor_task_id", sa.String(36), sa.ForeignKey("core_tasks.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("dependent_task_id", "predecessor_task_id", name="uq_core_task_dependency_edge"),
        sa.CheckConstraint("dependent_task_id <> predecessor_task_id", name="ck_core_task_dependency_not_self"),
    )
    for column in ("workspace_id", "project_id", "dependent_task_id", "predecessor_task_id", "created_at"):
        op.create_index(f"ix_core_task_dependencies_{column}", "core_task_dependencies", [column])


def downgrade() -> None:
    op.drop_table("core_task_dependencies")
    op.drop_index("ix_core_tasks_due_at", table_name="core_tasks")
    op.drop_column("core_tasks", "due_at")
