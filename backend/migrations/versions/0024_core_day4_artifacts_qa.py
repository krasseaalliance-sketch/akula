"""Make Core artifacts versioned and QA requests independently auditable."""

import sqlalchemy as sa
from alembic import op


revision = "0024_core_day4_artifacts_qa"
down_revision = "0023_core_day3_runs"
branch_labels = None
depends_on = None


def _upgrade_postgresql() -> None:
    # Batch recreation drops a table primary-key constraint before replacing
    # the table. PostgreSQL rejects that while Core child tables still hold
    # foreign keys to the primary key. Alter these tables in place instead.
    op.add_column("core_agents", sa.Column("user_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_core_agents_user_id", "core_agents", "users", ["user_id"], ["id"])
    op.create_index("ix_core_agents_user_id", "core_agents", ["user_id"])

    op.add_column("core_tasks", sa.Column("parent_task_id", sa.String(36), nullable=True))
    op.add_column("core_tasks", sa.Column("remediation_verification_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_core_tasks_parent_task_id", "core_tasks", "core_tasks", ["parent_task_id"], ["id"])
    op.create_foreign_key("fk_core_tasks_remediation_verification_id", "core_tasks", "core_verifications", ["remediation_verification_id"], ["id"])
    op.create_index("ix_core_tasks_parent_task_id", "core_tasks", ["parent_task_id"])
    op.create_index("ix_core_tasks_remediation_verification_id", "core_tasks", ["remediation_verification_id"])

    op.add_column("core_artifacts", sa.Column("run_id", sa.String(36), nullable=True))
    op.add_column("core_artifacts", sa.Column("artifact_key", sa.String(120), nullable=True))
    op.execute("UPDATE core_artifacts SET artifact_key = id WHERE artifact_key IS NULL")
    op.execute("UPDATE core_artifacts SET status = 'DRAFT' WHERE status = 'PENDING'")
    op.execute("UPDATE core_artifacts SET status = 'APPROVED' WHERE status = 'VERIFIED'")
    op.alter_column("core_artifacts", "artifact_key", existing_type=sa.String(120), nullable=False)
    op.drop_constraint("ck_core_artifacts_status", "core_artifacts", type_="check")
    op.create_check_constraint("ck_core_artifacts_type", "core_artifacts", "artifact_type IN ('DOCUMENT', 'LINK', 'FILE', 'IMAGE', 'BUILD', 'RELEASE', 'TEST_REPORT', 'SCREENSHOT', 'LOG')")
    op.create_check_constraint("ck_core_artifacts_status", "core_artifacts", "status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SUPERSEDED')")
    op.create_unique_constraint("uq_core_artifact_version", "core_artifacts", ["workspace_id", "artifact_key", "version"])
    op.create_foreign_key("fk_core_artifacts_run_id", "core_artifacts", "core_runs", ["run_id"], ["id"])
    op.create_index("ix_core_artifacts_run_id", "core_artifacts", ["run_id"])
    op.create_index("ix_core_artifacts_artifact_key", "core_artifacts", ["artifact_key"])

    op.add_column("core_verifications", sa.Column("qa_agent_id", sa.String(36), nullable=True))
    op.add_column("core_verifications", sa.Column("status", sa.String(12), nullable=True, server_default="PENDING"))
    op.add_column("core_verifications", sa.Column("checked_artifact_version", sa.String(80), nullable=True))
    op.add_column("core_verifications", sa.Column("idempotency_key", sa.String(160), nullable=True))
    op.add_column("core_verifications", sa.Column("defect", sa.Text(), nullable=True))
    op.add_column("core_verifications", sa.Column("remediation_action", sa.Text(), nullable=True))
    op.add_column("core_verifications", sa.Column("remediation_task_id", sa.String(36), nullable=True))
    op.add_column("core_verifications", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.drop_constraint("ck_core_verifications_result", "core_verifications", type_="check")
    op.create_check_constraint("ck_core_verifications_status", "core_verifications", "status IN ('PENDING', 'PASS', 'FAIL', 'BLOCKED')")
    op.create_foreign_key("fk_core_verifications_qa_agent_id", "core_verifications", "core_agents", ["qa_agent_id"], ["id"])
    op.create_foreign_key("fk_core_verifications_remediation_task_id", "core_verifications", "core_tasks", ["remediation_task_id"], ["id"])
    op.create_index("ix_core_verifications_qa_agent_id", "core_verifications", ["qa_agent_id"])
    op.create_index("ix_core_verifications_remediation_task_id", "core_verifications", ["remediation_task_id"])
    op.create_unique_constraint("uq_core_verification_idempotency", "core_verifications", ["workspace_id", "idempotency_key"])
    op.execute("UPDATE core_verifications SET status = result WHERE status = 'PENDING' AND result <> 'PENDING'")


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        _upgrade_postgresql()
        return

    with op.batch_alter_table("core_agents", recreate="always") as batch:
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_core_agents_user_id", "users", ["user_id"], ["id"])
        batch.create_index("ix_core_agents_user_id", ["user_id"])

    with op.batch_alter_table("core_tasks", recreate="always") as batch:
        batch.add_column(sa.Column("parent_task_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("remediation_verification_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_core_tasks_parent_task_id", "core_tasks", ["parent_task_id"], ["id"])
        batch.create_foreign_key("fk_core_tasks_remediation_verification_id", "core_verifications", ["remediation_verification_id"], ["id"])
        batch.create_index("ix_core_tasks_parent_task_id", ["parent_task_id"])
        batch.create_index("ix_core_tasks_remediation_verification_id", ["remediation_verification_id"])

    op.add_column("core_artifacts", sa.Column("run_id", sa.String(36), nullable=True))
    op.add_column("core_artifacts", sa.Column("artifact_key", sa.String(120), nullable=True))
    op.execute("UPDATE core_artifacts SET artifact_key = id WHERE artifact_key IS NULL")
    op.execute("UPDATE core_artifacts SET status = 'DRAFT' WHERE status = 'PENDING'")
    op.execute("UPDATE core_artifacts SET status = 'APPROVED' WHERE status = 'VERIFIED'")
    with op.batch_alter_table("core_artifacts", recreate="always") as batch:
        batch.alter_column("artifact_key", existing_type=sa.String(120), nullable=False)
        batch.drop_constraint("ck_core_artifacts_status", type_="check")
        batch.create_check_constraint("ck_core_artifacts_type", "artifact_type IN ('DOCUMENT', 'LINK', 'FILE', 'IMAGE', 'BUILD', 'RELEASE', 'TEST_REPORT', 'SCREENSHOT', 'LOG')")
        batch.create_check_constraint("ck_core_artifacts_status", "status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SUPERSEDED')")
        batch.create_unique_constraint("uq_core_artifact_version", ["workspace_id", "artifact_key", "version"])
        batch.create_foreign_key("fk_core_artifacts_run_id", "core_runs", ["run_id"], ["id"])
        batch.create_index("ix_core_artifacts_run_id", ["run_id"])
        batch.create_index("ix_core_artifacts_artifact_key", ["artifact_key"])

    with op.batch_alter_table("core_verifications", recreate="always") as batch:
        batch.add_column(sa.Column("qa_agent_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("status", sa.String(12), nullable=True, server_default="PENDING"))
        batch.add_column(sa.Column("checked_artifact_version", sa.String(80), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(160), nullable=True))
        batch.add_column(sa.Column("defect", sa.Text(), nullable=True))
        batch.add_column(sa.Column("remediation_action", sa.Text(), nullable=True))
        batch.add_column(sa.Column("remediation_task_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        batch.drop_constraint("ck_core_verifications_result", type_="check")
        batch.create_check_constraint("ck_core_verifications_status", "status IN ('PENDING', 'PASS', 'FAIL', 'BLOCKED')")
        batch.create_foreign_key("fk_core_verifications_qa_agent_id", "core_agents", ["qa_agent_id"], ["id"])
        batch.create_foreign_key("fk_core_verifications_remediation_task_id", "core_tasks", ["remediation_task_id"], ["id"])
        batch.create_index("ix_core_verifications_qa_agent_id", ["qa_agent_id"])
        batch.create_index("ix_core_verifications_remediation_task_id", ["remediation_task_id"])
        batch.create_unique_constraint("uq_core_verification_idempotency", ["workspace_id", "idempotency_key"])
    op.execute("UPDATE core_verifications SET status = result WHERE status = 'PENDING' AND result <> 'PENDING'")


def downgrade() -> None:
    raise NotImplementedError("Core Day 4 migration is append-only and must not be downgraded destructively")
