"""Core domain models for Release 1.

These models deliberately own orchestration state and references, not the
canonical data of Scout, Constructive, or other products.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, new_id


class CoreProduct(Base):
    __tablename__ = "core_products"
    __table_args__ = (
        UniqueConstraint("workspace_id", "product_key", name="uq_core_products_workspace_key"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name="ck_core_products_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CoreProject(Base):
    __tablename__ = "core_projects"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'COMPLETED', 'ARCHIVED')", name="ck_core_projects_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("core_products.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CoreMission(Base):
    __tablename__ = "core_missions"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'PLANNED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED', 'REJECTED')", name="ck_core_missions_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("core_projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text)
    boundaries: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CoreSprint(Base):
    __tablename__ = "core_sprints"
    __table_args__ = (
        CheckConstraint("status IN ('PLANNED', 'ACTIVE', 'COMPLETED', 'BLOCKED')", name="ck_core_sprints_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("core_projects.id"), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("core_missions.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CoreAgent(Base):
    __tablename__ = "core_agents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_key", name="uq_core_agents_workspace_key"),
        CheckConstraint("status IN ('AVAILABLE', 'BUSY', 'PAUSED', 'DISABLED')", name="ck_core_agents_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    competencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=1)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CoreTask(Base):
    __tablename__ = "core_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'PLANNED', 'IN_PROGRESS', 'IN_REVIEW', 'ACCEPTED', 'RETURNED', 'BLOCKED', 'CANCELLED')", name="ck_core_tasks_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("core_projects.id"), index=True)
    sprint_id: Mapped[str] = mapped_column(ForeignKey("core_sprints.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_competencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("core_agents.id"), nullable=True, index=True)
    parent_task_id: Mapped[str | None] = mapped_column(ForeignKey("core_tasks.id"), nullable=True, index=True)
    remediation_verification_id: Mapped[str | None] = mapped_column(ForeignKey("core_verifications.id"), nullable=True, index=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CoreTaskDependency(Base):
    __tablename__ = "core_task_dependencies"
    __table_args__ = (
        UniqueConstraint("dependent_task_id", "predecessor_task_id", name="uq_core_task_dependency_edge"),
        CheckConstraint("dependent_task_id <> predecessor_task_id", name="ck_core_task_dependency_not_self"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("core_projects.id"), index=True)
    dependent_task_id: Mapped[str] = mapped_column(ForeignKey("core_tasks.id"), index=True)
    predecessor_task_id: Mapped[str] = mapped_column(ForeignKey("core_tasks.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoreTaskAssignment(Base):
    __tablename__ = "core_task_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("core_projects.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("core_tasks.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("core_agents.id"), index=True)
    assigned_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CoreRun(Base):
    __tablename__ = "core_runs"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')", name="ck_core_runs_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("core_projects.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("core_tasks.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("core_agents.id"), index=True)
    initiated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CoreArtifact(Base):
    __tablename__ = "core_artifacts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "artifact_key", "version", name="uq_core_artifact_version"),
        CheckConstraint("artifact_type IN ('DOCUMENT', 'LINK', 'FILE', 'IMAGE', 'BUILD', 'RELEASE', 'TEST_REPORT', 'SCREENSHOT', 'LOG')", name="ck_core_artifacts_type"),
        CheckConstraint("status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SUPERSEDED')", name="ck_core_artifacts_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("core_tasks.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core_runs.id"), nullable=True, index=True)
    artifact_key: Mapped[str] = mapped_column(String(120), default=new_id, index=True)
    artifact_type: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(240))
    uri: Mapped[str] = mapped_column(String(1000))
    version: Mapped[str] = mapped_column(String(80), default="1")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoreVerification(Base):
    __tablename__ = "core_verifications"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_core_verification_idempotency"),
        CheckConstraint("status IN ('PENDING', 'PASS', 'FAIL', 'BLOCKED')", name="ck_core_verifications_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("core_tasks.id"), index=True)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("core_artifacts.id"), nullable=True, index=True)
    qa_agent_id: Mapped[str | None] = mapped_column(ForeignKey("core_agents.id"), nullable=True, index=True)
    verifier_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    result: Mapped[str] = mapped_column(String(12), default="PENDING")
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_artifact_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    defect: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_task_id: Mapped[str | None] = mapped_column(ForeignKey("core_tasks.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CoreProductionEvidence(Base):
    __tablename__ = "core_production_evidence"
    __table_args__ = (
        CheckConstraint("result IN ('PASS', 'FAIL')", name="ck_core_production_evidence_result"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("core_tasks.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core_runs.id"), nullable=True, index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("core_artifacts.id"), index=True)
    public_url: Mapped[str] = mapped_column(String(1000))
    build_id: Mapped[str] = mapped_column(String(240))
    checked_at: Mapped[datetime] = mapped_column(DateTime)
    executor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    screenshot_uri: Mapped[str] = mapped_column(String(1000))
    logs_uri: Mapped[str] = mapped_column(String(1000))
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    result: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoreEvent(Base):
    __tablename__ = "core_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    event_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
