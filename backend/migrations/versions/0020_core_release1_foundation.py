"""Create the Core Release 1 foundation and acceptance evidence tables."""

import sqlalchemy as sa
from alembic import op


revision = "0020_core_release1_foundation"
down_revision = "0019_asmet_message_sent_at"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "core_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("product_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("workspace_id", "product_key", name="uq_core_products_workspace_key"),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name="ck_core_products_status"),
    )
    op.create_table(
        "core_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("core_products.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'COMPLETED', 'ARCHIVED')", name="ck_core_projects_status"),
    )
    op.create_table(
        "core_missions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("core_projects.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("boundaries", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('DRAFT', 'PLANNED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED', 'REJECTED')", name="ck_core_missions_status"),
    )
    op.create_table(
        "core_sprints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("core_projects.id"), nullable=False),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("core_missions.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime()),
        sa.Column("ends_at", sa.DateTime()),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('PLANNED', 'ACTIVE', 'COMPLETED', 'BLOCKED')", name="ck_core_sprints_status"),
    )
    op.create_table(
        "core_agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("agent_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("role", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("competencies", sa.JSON(), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE"),
        *_timestamps(),
        sa.UniqueConstraint("workspace_id", "agent_key", name="uq_core_agents_workspace_key"),
        sa.CheckConstraint("status IN ('AVAILABLE', 'BUSY', 'PAUSED', 'DISABLED')", name="ck_core_agents_status"),
    )
    op.create_table(
        "core_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("core_projects.id"), nullable=False),
        sa.Column("sprint_id", sa.String(36), sa.ForeignKey("core_sprints.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("core_agents.id")),
        sa.Column("result_summary", sa.Text()),
        sa.Column("return_reason", sa.Text()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('DRAFT', 'PLANNED', 'IN_PROGRESS', 'IN_REVIEW', 'ACCEPTED', 'RETURNED', 'BLOCKED', 'CANCELLED')", name="ck_core_tasks_status"),
    )
    op.create_table(
        "core_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("core_tasks.id"), nullable=False),
        sa.Column("artifact_type", sa.String(60), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("uri", sa.String(1000), nullable=False),
        sa.Column("version", sa.String(80), nullable=False, server_default="1"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('PENDING', 'VERIFIED', 'REJECTED')", name="ck_core_artifacts_status"),
    )
    op.create_table(
        "core_verifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("core_tasks.id"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("core_artifacts.id")),
        sa.Column("verifier_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("result", sa.String(12), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("result IN ('PASS', 'FAIL', 'BLOCKED')", name="ck_core_verifications_result"),
    )
    op.create_table(
        "core_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("evidence", sa.JSON()),
        sa.Column("event_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for table, columns in {
        "core_products": ["workspace_id"],
        "core_projects": ["workspace_id", "product_id"],
        "core_missions": ["project_id"],
        "core_sprints": ["project_id", "mission_id"],
        "core_agents": ["workspace_id"],
        "core_tasks": ["workspace_id", "project_id", "sprint_id", "agent_id"],
        "core_artifacts": ["workspace_id", "task_id"],
        "core_verifications": ["workspace_id", "task_id", "artifact_id"],
        "core_events": ["workspace_id", "actor_id", "entity_id", "created_at"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ["core_events", "core_verifications", "core_artifacts", "core_tasks", "core_agents", "core_sprints", "core_missions", "core_projects", "core_products"]:
        op.drop_table(table)
