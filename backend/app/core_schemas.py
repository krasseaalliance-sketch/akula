"""API contracts for the Core Release 1 foundation."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CoreORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


CoreStatus = Literal["DRAFT", "ACTIVE", "ARCHIVED"]
TaskStatus = Literal[
    "DRAFT", "PLANNED", "IN_PROGRESS", "IN_REVIEW", "ACCEPTED", "RETURNED", "BLOCKED", "CANCELLED"
]
ArtifactType = Literal["DOCUMENT", "LINK", "FILE", "IMAGE", "BUILD", "RELEASE", "TEST_REPORT", "SCREENSHOT", "LOG"]
ArtifactStatus = Literal["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "SUPERSEDED"]
VerificationStatus = Literal["PENDING", "PASS", "FAIL", "BLOCKED"]
VerificationResult = Literal["PASS", "FAIL", "BLOCKED"]


class CoreProductCreate(BaseModel):
    workspace_id: str
    product_key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None


class CoreProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    status: CoreStatus | None = None


class CoreProductResponse(CoreORM):
    id: str
    workspace_id: str
    product_key: str
    name: str
    description: str | None
    status: str


class CoreProjectCreate(BaseModel):
    workspace_id: str
    product_id: str
    name: str = Field(min_length=2, max_length=200)
    objective: str = Field(min_length=2)


class CoreProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    objective: str | None = Field(default=None, min_length=2)
    status: Literal["DRAFT", "ACTIVE", "COMPLETED", "ARCHIVED"] | None = None


class CoreProjectResponse(CoreORM):
    id: str
    workspace_id: str
    product_id: str
    name: str
    objective: str
    status: str


class CoreMissionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    goal: str = Field(min_length=2)
    boundaries: dict[str, Any] = Field(default_factory=dict)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class CoreMissionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    goal: str | None = Field(default=None, min_length=2)
    boundaries: dict[str, Any] | None = None
    risks: list[dict[str, Any]] | None = None
    acceptance_criteria: list[str] | None = None
    status: Literal["DRAFT", "PLANNED", "IN_PROGRESS", "COMPLETED", "BLOCKED", "REJECTED"] | None = None


class CoreMissionResponse(CoreORM):
    id: str
    project_id: str
    title: str
    goal: str
    boundaries: dict[str, Any]
    risks: list[dict[str, Any]]
    acceptance_criteria: list[str]
    status: str


class CoreSprintCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    goal: str = Field(min_length=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CoreSprintPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    goal: str | None = Field(default=None, min_length=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: Literal["PLANNED", "ACTIVE", "COMPLETED", "BLOCKED"] | None = None


class CoreSprintResponse(CoreORM):
    id: str
    project_id: str
    mission_id: str
    name: str
    goal: str
    starts_at: datetime | None
    ends_at: datetime | None
    status: str


class CoreTaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    description: str = Field(min_length=2)
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_competencies: list[str] = Field(default_factory=list)
    priority: int = Field(default=3, ge=1, le=5)
    due_at: datetime | None = None
    agent_id: str | None = None


class CoreTaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=240)
    description: str | None = Field(default=None, min_length=2)
    acceptance_criteria: list[str] | None = None
    required_competencies: list[str] | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    due_at: datetime | None = None
    agent_id: str | None = None


class CoreTaskStatusPatch(BaseModel):
    status: TaskStatus
    result_summary: str | None = None
    return_reason: str | None = None


class CoreTaskResponse(CoreORM):
    id: str
    workspace_id: str
    project_id: str
    sprint_id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    required_competencies: list[str]
    priority: int
    due_at: datetime | None
    status: str
    agent_id: str | None
    parent_task_id: str | None
    remediation_verification_id: str | None
    result_summary: str | None
    return_reason: str | None


class CoreArtifactCreate(BaseModel):
    artifact_key: str | None = Field(default=None, min_length=2, max_length=120)
    artifact_type: ArtifactType
    name: str = Field(min_length=2, max_length=240)
    uri: str = Field(min_length=1, max_length=1000)
    version: str = Field(default="1", max_length=80)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None


class CoreArtifactVersionCreate(BaseModel):
    artifact_type: ArtifactType
    name: str = Field(min_length=2, max_length=240)
    uri: str = Field(min_length=1, max_length=1000)
    version: str = Field(min_length=1, max_length=80)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None


class CoreArtifactPatch(BaseModel):
    status: ArtifactStatus


class CoreArtifactResponse(CoreORM):
    id: str
    workspace_id: str
    task_id: str
    run_id: str | None
    artifact_key: str
    artifact_type: str
    name: str
    uri: str
    version: str
    metadata_json: dict[str, Any]
    status: str
    created_by: str
    created_at: datetime


class CoreVerificationCreate(BaseModel):
    qa_agent_id: str | None = None
    artifact_id: str | None = None
    checked_artifact_version: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=160)
    result: VerificationResult | None = None
    status: Literal["PENDING", "PASS", "FAIL", "BLOCKED"] = "PENDING"
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class CoreVerificationComplete(BaseModel):
    status: VerificationStatus
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None
    defect: str | None = None
    remediation_action: str | None = None


class CoreVerificationResponse(CoreORM):
    id: str
    workspace_id: str
    task_id: str
    artifact_id: str | None
    qa_agent_id: str | None
    verifier_id: str
    status: VerificationStatus
    result: str
    checklist: list[dict[str, Any]]
    evidence: dict[str, Any]
    notes: str | None
    checked_artifact_version: str | None
    idempotency_key: str | None
    defect: str | None
    remediation_action: str | None
    remediation_task_id: str | None
    created_at: datetime
    completed_at: datetime | None


class CoreProductionEvidenceCreate(BaseModel):
    run_id: str | None = None
    public_url: str = Field(min_length=8, max_length=1000)
    build_id: str = Field(min_length=2, max_length=240)
    checked_at: datetime
    screenshot_uri: str = Field(min_length=1, max_length=1000)
    logs_uri: str = Field(min_length=1, max_length=1000)
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    result: Literal["PASS", "FAIL"]


class CoreProductionEvidenceResponse(CoreORM):
    id: str
    workspace_id: str
    task_id: str
    run_id: str | None
    artifact_id: str
    public_url: str
    build_id: str
    checked_at: datetime
    executor_id: str
    screenshot_uri: str
    logs_uri: str
    checklist: list[dict[str, Any]]
    result: Literal["PASS", "FAIL"]
    created_at: datetime
    artifact: CoreArtifactResponse


class CoreAgentResponse(CoreORM):
    id: str
    workspace_id: str
    agent_key: str
    name: str
    role: str
    description: str
    competencies: list[str]
    allowed_tools: list[str]
    allowed_actions: list[str]
    limits: dict[str, Any]
    concurrency_limit: int
    available: bool
    status: str


class CoreAgentAssignmentCreate(BaseModel):
    agent_id: str


class CoreAgentAssignmentResponse(CoreORM):
    id: str
    workspace_id: str
    project_id: str
    task_id: str
    agent_id: str
    assigned_by: str
    assigned_at: datetime
    released_at: datetime | None
    release_reason: str | None


class CoreRunContext(BaseModel):
    goal: str = Field(min_length=2)
    constraints: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class CoreRunCreate(CoreRunContext):
    pass


RunStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]


class CoreRunTransition(BaseModel):
    status: RunStatus
    result_summary: str | None = None
    error_reason: str | None = None


class CoreRunResponse(CoreORM):
    id: str
    workspace_id: str
    project_id: str
    task_id: str
    agent_id: str
    initiated_by: str
    status: RunStatus
    context: dict[str, Any]
    result_summary: str | None
    error_reason: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class CoreRouteStepResponse(BaseModel):
    step: int
    agent_id: str
    agent_key: str
    name: str
    competencies: list[str]
    confirmed: bool = False


class CoreRouteResponse(BaseModel):
    task_id: str
    steps: list[CoreRouteStepResponse]
    next_step: int | None


class CoreDependencyCreate(BaseModel):
    predecessor_task_id: str


class CoreDependencyResponse(CoreORM):
    id: str
    workspace_id: str
    project_id: str
    dependent_task_id: str
    predecessor_task_id: str
    created_by: str
    created_at: datetime


class CoreEventResponse(CoreORM):
    id: str
    workspace_id: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    evidence: dict[str, Any] | None
    event_hash: str
    created_at: datetime
