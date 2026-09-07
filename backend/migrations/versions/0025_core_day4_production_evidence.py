"""Add the validated production evidence packet."""

import sqlalchemy as sa
from alembic import op


revision = "0025_core_day4_production_evidence"
down_revision = "0024_core_day4_artifacts_qa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "core_production_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("core_tasks.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("core_runs.id"), nullable=True),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("core_artifacts.id"), nullable=False),
        sa.Column("public_url", sa.String(1000), nullable=False),
        sa.Column("build_id", sa.String(240), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("executor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("screenshot_uri", sa.String(1000), nullable=False),
        sa.Column("logs_uri", sa.String(1000), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("result", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("result IN ('PASS', 'FAIL')", name="ck_core_production_evidence_result"),
    )
    for column in ("workspace_id", "task_id", "run_id", "artifact_id", "executor_id", "created_at"):
        op.create_index(f"ix_core_production_evidence_{column}", "core_production_evidence", [column])


def downgrade() -> None:
    raise NotImplementedError("Core production evidence is append-only and must not be downgraded destructively")
