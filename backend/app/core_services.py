"""Domain rules for the Core Release 1 workflow."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core_models import CoreAgent, CoreArtifact, CoreEvent, CoreMission, CoreProduct, CoreProject, CoreRun, CoreSprint, CoreTask, CoreTaskAssignment, CoreTaskDependency, CoreVerification
from .models import User, Workspace, new_id
from .services import accessible_workspace_ids, json_safe, model_dict, require_permission, role_for


TASK_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"PLANNED", "CANCELLED"},
    "PLANNED": {"IN_PROGRESS", "BLOCKED", "CANCELLED"},
    "IN_PROGRESS": {"IN_REVIEW", "BLOCKED", "CANCELLED"},
    "IN_REVIEW": {"RETURNED", "BLOCKED"},
    "RETURNED": {"IN_PROGRESS", "CANCELLED"},
    "BLOCKED": {"IN_PROGRESS", "CANCELLED"},
    "ACCEPTED": set(),
    "CANCELLED": set(),
}

ARTIFACT_STORAGE_ROOT = Path(".core_artifacts")

RUN_TRANSITIONS: dict[str, set[str]] = {
    "QUEUED": {"RUNNING", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}

ARTIFACT_TYPES = {"DOCUMENT", "LINK", "FILE", "IMAGE", "BUILD", "RELEASE", "TEST_REPORT", "SCREENSHOT", "LOG"}
ARTIFACT_STATUSES = {"DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "SUPERSEDED"}


def require_core_workspace(db: Session, user: User, workspace_id: str, permission: str = "core.view") -> Workspace:
    if workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        require_permission(db, user.id, workspace_id, permission)
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}") from None
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def ensure_workspace_entity(db: Session, user: User, entity: Any, permission: str = "core.view") -> Any:
    workspace_id = getattr(entity, "workspace_id", None)
    if entity is None or not workspace_id:
        raise HTTPException(status_code=404, detail="Core entity not found")
    require_core_workspace(db, user, workspace_id, permission)
    return entity


def require_product(db: Session, user: User, product_id: str, workspace_id: str, permission: str = "core.manage") -> CoreProduct:
    product = db.get(CoreProduct, product_id)
    if product is None or product.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Core product not found")
    require_core_workspace(db, user, workspace_id, permission)
    return product


def record_event(
    db: Session,
    *,
    workspace_id: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> CoreEvent:
    occurred_at = datetime.utcnow()
    payload = {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before": json_safe(before),
        "after": json_safe(after),
        "evidence": json_safe(evidence),
        "occurred_at": occurred_at.isoformat(),
    }
    event = CoreEvent(
        workspace_id=workspace_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before,
        after_state=after,
        evidence=evidence,
        created_at=occurred_at,
        event_hash=hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    )
    db.add(event)
    return event


def transition_task(db: Session, task: CoreTask, new_status: str, actor_id: str, **changes: Any) -> CoreTask:
    if new_status == "ACCEPTED":
        raise HTTPException(status_code=409, detail="Task acceptance requires a QA verification")
    allowed = TASK_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise HTTPException(status_code=409, detail=f"Invalid task transition: {task.status} -> {new_status}")
    if new_status == "IN_PROGRESS" and incomplete_blockers(db, task.id):
        raise HTTPException(status_code=409, detail="Task is blocked by incomplete dependencies")
    before = model_dict(task)
    task.status = new_status
    for key in ("result_summary", "return_reason"):
        if key in changes:
            setattr(task, key, changes[key])
    record_event(
        db,
        workspace_id=task.workspace_id,
        actor_id=actor_id,
        action="task.status_changed",
        entity_type="CoreTask",
        entity_id=task.id,
        before=before,
        after=model_dict(task),
    )
    return task


def verify_and_accept_task(
    db: Session,
    *,
    task: CoreTask,
    verifier_id: str,
    artifact: CoreArtifact,
    verification: CoreVerification,
) -> None:
    if task.status != "IN_REVIEW":
        raise HTTPException(status_code=409, detail="Only tasks in review can be verified")
    if incomplete_blockers(db, task.id):
        raise HTTPException(status_code=409, detail="Task is blocked by incomplete dependencies")
    if verification.status == "PASS":
        if artifact.task_id != task.id:
            raise HTTPException(status_code=404, detail="Artifact not found for task")
        if not verification.evidence:
            raise HTTPException(status_code=422, detail="PASS verification requires evidence")
        if not verification.checklist or any(item.get("passed") is not True for item in verification.checklist):
            raise HTTPException(status_code=422, detail="PASS verification requires a fully passed checklist")
        if not task.result_summary:
            raise HTTPException(status_code=422, detail="PASS verification requires task result")
        before = model_dict(task)
        task.status = "ACCEPTED"
        artifact.status = "APPROVED"
        record_event(
            db,
            workspace_id=task.workspace_id,
            actor_id=verifier_id,
            action="task.accepted",
            entity_type="CoreTask",
            entity_id=task.id,
            before=before,
            after=model_dict(task),
            evidence={"artifact_id": artifact.id, "verification_id": verification.id, **verification.evidence},
        )
    elif verification.status == "FAIL":
        before = model_dict(task)
        task.status = "RETURNED"
        task.return_reason = verification.notes or "QA verification failed"
        artifact.status = "REJECTED"
        record_event(
            db,
            workspace_id=task.workspace_id,
            actor_id=verifier_id,
            action="task.returned_after_qa",
            entity_type="CoreTask",
            entity_id=task.id,
            before=before,
            after=model_dict(task),
            evidence={"artifact_id": artifact.id, "verification_id": verification.id, **verification.evidence},
        )
    else:
        task.status = "BLOCKED"
        record_event(
            db,
            workspace_id=task.workspace_id,
            actor_id=verifier_id,
            action="task.blocked_after_qa",
            entity_type="CoreTask",
            entity_id=task.id,
            after=model_dict(task),
            evidence={"artifact_id": artifact.id, "verification_id": verification.id, **verification.evidence},
        )


def qa_agent_for_user(db: Session, *, workspace_id: str, user_id: str) -> CoreAgent | None:
    agents = db.scalars(
        select(CoreAgent).where(
            CoreAgent.workspace_id == workspace_id,
            CoreAgent.user_id == user_id,
        )
    ).all()
    return next((agent for agent in agents if "qa" in (agent.role or "").casefold() or "quality" in (agent.role or "").casefold()), None)


def require_qa_actor(db: Session, *, user: User, workspace_id: str, qa_agent: CoreAgent | None) -> None:
    if role_for(db, user.id, workspace_id) == "OWNER":
        return
    if qa_agent is None or qa_agent.workspace_id != workspace_id or qa_agent.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the Creator or assigned QA agent may manage this verification")
    if "qa" not in (qa_agent.role or "").casefold() and "quality" not in (qa_agent.role or "").casefold():
        raise HTTPException(status_code=403, detail="The assigned agent is not a QA agent")


def validate_artifact_reference(db: Session, *, task: CoreTask, artifact_id: str | None, version: str | None = None) -> CoreArtifact | None:
    if artifact_id is None:
        raise HTTPException(status_code=422, detail="A verification requires an artifact")
    artifact = db.get(CoreArtifact, artifact_id)
    if artifact is None or artifact.workspace_id != task.workspace_id or artifact.task_id != task.id:
        raise HTTPException(status_code=404, detail="Artifact not found for task")
    if version is not None and artifact.version != version:
        raise HTTPException(status_code=409, detail="Checked artifact version does not match")
    return artifact


def create_artifact_version(db: Session, *, task: CoreTask, actor_id: str, payload: dict[str, Any], artifact_key: str | None = None) -> CoreArtifact:
    artifact_type = payload.get("artifact_type")
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported artifact type")
    run_id = payload.get("run_id")
    if run_id is not None:
        run = db.get(CoreRun, run_id)
        if run is None or run.workspace_id != task.workspace_id or run.task_id != task.id:
            raise HTTPException(status_code=404, detail="Run not found for task")
    key = artifact_key or payload.get("artifact_key") or new_id()
    artifact = CoreArtifact(
        workspace_id=task.workspace_id,
        task_id=task.id,
        created_by=actor_id,
        artifact_key=key,
        **{key: value for key, value in payload.items() if key != "artifact_key"},
    )
    db.add(artifact)
    db.flush()
    return artifact


def store_artifact_upload(
    db: Session,
    *,
    task: CoreTask,
    actor_id: str,
    artifact_type: str,
    name: str,
    version: str,
    original_name: str,
    content_type: str,
    content: bytes,
) -> CoreArtifact:
    if artifact_type not in {"FILE", "IMAGE"}:
        raise HTTPException(status_code=422, detail="Binary uploads must be FILE or IMAGE artifacts")
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded artifact cannot be empty")
    artifact_id = new_id()
    storage_path = ARTIFACT_STORAGE_ROOT / task.workspace_id / task.id
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / artifact_id).write_bytes(content)
    artifact = CoreArtifact(
        id=artifact_id,
        workspace_id=task.workspace_id,
        task_id=task.id,
        artifact_key=new_id(),
        artifact_type=artifact_type,
        name=name,
        uri=f"/scout/api/core/artifacts/{artifact_id}/content",
        version=version,
        metadata_json={"original_name": original_name, "content_type": content_type, "size": len(content)},
        created_by=actor_id,
    )
    db.add(artifact)
    db.flush()
    return artifact


def transition_artifact(db: Session, *, artifact: CoreArtifact, actor_id: str, status: str) -> CoreArtifact:
    if status not in ARTIFACT_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported artifact status")
    allowed = {
        "DRAFT": {"SUBMITTED", "REJECTED", "SUPERSEDED"},
        "SUBMITTED": {"APPROVED", "REJECTED", "SUPERSEDED"},
        "APPROVED": {"SUPERSEDED"},
        "REJECTED": {"DRAFT", "SUPERSEDED"},
        "SUPERSEDED": set(),
    }
    if status != artifact.status and status not in allowed.get(artifact.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid artifact transition: {artifact.status} -> {status}")
    before = model_dict(artifact)
    artifact.status = status
    record_event(db, workspace_id=artifact.workspace_id, actor_id=actor_id, action="artifact.status_changed", entity_type="CoreArtifact", entity_id=artifact.id, before=before, after=model_dict(artifact))
    return artifact


def create_verification(db: Session, *, task: CoreTask, user: User, qa_agent: CoreAgent | None, artifact_id: str | None, checked_artifact_version: str | None, idempotency_key: str | None) -> CoreVerification:
    require_qa_actor(db, user=user, workspace_id=task.workspace_id, qa_agent=qa_agent)
    if idempotency_key:
        existing = db.scalar(select(CoreVerification).where(CoreVerification.workspace_id == task.workspace_id, CoreVerification.idempotency_key == idempotency_key))
        if existing:
            return existing
    artifact = validate_artifact_reference(db, task=task, artifact_id=artifact_id, version=checked_artifact_version)
    verification = CoreVerification(
        workspace_id=task.workspace_id,
        task_id=task.id,
        artifact_id=artifact.id if artifact else None,
        qa_agent_id=qa_agent.id if qa_agent else None,
        verifier_id=user.id,
        status="PENDING",
        result="PENDING",
        checklist=[],
        evidence={},
        checked_artifact_version=checked_artifact_version or artifact.version,
        idempotency_key=idempotency_key,
    )
    db.add(verification)
    db.flush()
    record_event(db, workspace_id=task.workspace_id, actor_id=user.id, action="qa.created", entity_type="CoreVerification", entity_id=verification.id, after=model_dict(verification), evidence={"artifact_id": artifact.id if artifact else None, "qa_agent_id": qa_agent.id if qa_agent else None})
    return verification


def create_remediation_task(db: Session, *, task: CoreTask, verification: CoreVerification) -> CoreTask:
    existing = db.scalar(select(CoreTask).where(CoreTask.remediation_verification_id == verification.id))
    if existing:
        verification.remediation_task_id = existing.id
        return existing
    failed = [str(item.get("name") or item.get("id") or "Unspecified check") for item in verification.checklist if item.get("passed") is not True]
    status = "BLOCKED" if task.status == "BLOCKED" else "PLANNED"
    remediation = CoreTask(
        workspace_id=task.workspace_id,
        project_id=task.project_id,
        sprint_id=task.sprint_id,
        title=f"Remediation: {task.title}",
        description=f"Defect: {verification.defect}\nAction: {verification.remediation_action}",
        acceptance_criteria=failed or ["Original QA defect is fixed and independently rechecked"],
        required_competencies=list(task.required_competencies or []),
        priority=task.priority,
        status=status,
        agent_id=task.agent_id,
        parent_task_id=task.id,
        remediation_verification_id=verification.id,
        created_by=verification.verifier_id,
    )
    db.add(remediation)
    db.flush()
    verification.remediation_task_id = remediation.id
    record_event(db, workspace_id=task.workspace_id, actor_id=verification.verifier_id, action="qa.remediation_created", entity_type="CoreTask", entity_id=remediation.id, after=model_dict(remediation), evidence={"source_task_id": task.id, "verification_id": verification.id, "failed_checks": failed})
    return remediation


def complete_verification(db: Session, *, verification: CoreVerification, task: CoreTask, user: User, status: str, checklist: list[dict[str, Any]], evidence: dict[str, Any], comment: str | None, defect: str | None, remediation_action: str | None) -> CoreVerification:
    qa_agent = db.get(CoreAgent, verification.qa_agent_id) if verification.qa_agent_id else None
    require_qa_actor(db, user=user, workspace_id=task.workspace_id, qa_agent=qa_agent)
    if verification.status != "PENDING":
        if verification.status == status:
            return verification
        raise HTTPException(status_code=409, detail="QA verification is already complete")
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        raise HTTPException(status_code=422, detail="QA completion requires PASS, FAIL or BLOCKED")
    if qa_agent is not None and task.agent_id == qa_agent.id and qa_agent.user_id == user.id:
        raise HTTPException(status_code=403, detail="A QA agent cannot accept its own task result")
    if status == "PASS":
        if not checklist or any(item.get("passed") is not True for item in checklist):
            raise HTTPException(status_code=422, detail="PASS requires a fully passed checklist")
        if not evidence:
            raise HTTPException(status_code=422, detail="PASS requires evidence")
        artifact = validate_artifact_reference(db, task=task, artifact_id=verification.artifact_id, version=verification.checked_artifact_version)
        if not task.result_summary:
            raise HTTPException(status_code=422, detail="PASS requires a task result")
        verification.artifact_id = artifact.id
    elif status == "BLOCKED" and not (comment or "").strip():
        raise HTTPException(status_code=422, detail="BLOCKED requires a reason")
    elif status == "FAIL":
        if not checklist or not evidence:
            raise HTTPException(status_code=422, detail="FAIL requires checklist and evidence")
        if not (defect or "").strip() or not (remediation_action or "").strip():
            raise HTTPException(status_code=422, detail="FAIL requires a defect and remediation action")
    before = model_dict(verification)
    verification.status = status
    verification.result = status
    verification.checklist = checklist
    verification.evidence = evidence
    verification.notes = comment
    verification.defect = defect
    verification.remediation_action = remediation_action
    verification.completed_at = datetime.utcnow()
    record_event(db, workspace_id=verification.workspace_id, actor_id=user.id, action="qa.completed", entity_type="CoreVerification", entity_id=verification.id, before=before, after=model_dict(verification), evidence=evidence)
    if status == "PASS":
        artifact = db.get(CoreArtifact, verification.artifact_id)
        verify_and_accept_task(db, task=task, verifier_id=user.id, artifact=artifact, verification=verification)
    elif status == "FAIL":
        verify_and_accept_task(db, task=task, verifier_id=user.id, artifact=db.get(CoreArtifact, verification.artifact_id), verification=verification)
        create_remediation_task(db, task=task, verification=verification)
    else:
        verify_and_accept_task(db, task=task, verifier_id=user.id, artifact=db.get(CoreArtifact, verification.artifact_id), verification=verification)
    return verification


def project_for(db: Session, project_id: str, workspace_id: str) -> CoreProject:
    project = db.get(CoreProject, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Core project not found")
    return project


def mission_for(db: Session, mission_id: str, project_id: str) -> CoreMission:
    mission = db.get(CoreMission, mission_id)
    if mission is None or mission.project_id != project_id:
        raise HTTPException(status_code=404, detail="Core mission not found")
    return mission


def sprint_for(db: Session, sprint_id: str, project_id: str) -> CoreSprint:
    sprint = db.get(CoreSprint, sprint_id)
    if sprint is None or sprint.project_id != project_id:
        raise HTTPException(status_code=404, detail="Core sprint not found")
    return sprint


def incomplete_blockers(db: Session, task_id: str) -> list[CoreTask]:
    dependencies = db.scalars(select(CoreTaskDependency).where(CoreTaskDependency.dependent_task_id == task_id)).all()
    if not dependencies:
        return []
    predecessors = db.scalars(select(CoreTask).where(CoreTask.id.in_([item.predecessor_task_id for item in dependencies]))).all()
    return [item for item in predecessors if item.status != "ACCEPTED"]


def would_create_cycle(db: Session, *, dependent_task_id: str, predecessor_task_id: str) -> bool:
    graph: dict[str, set[str]] = {}
    for dependency in db.scalars(select(CoreTaskDependency)).all():
        graph.setdefault(dependency.dependent_task_id, set()).add(dependency.predecessor_task_id)
    graph.setdefault(dependent_task_id, set()).add(predecessor_task_id)
    pending = [predecessor_task_id]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == dependent_task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(graph.get(current, set()))
    return False


def active_run_count(db: Session, agent_id: str) -> int:
    return len(db.scalars(select(CoreRun).where(CoreRun.agent_id == agent_id, CoreRun.status.in_(("QUEUED", "RUNNING")))).all())


def agent_snapshot(db: Session, agent: CoreAgent) -> dict[str, Any]:
    active = db.scalars(select(CoreRun).where(CoreRun.agent_id == agent.id, CoreRun.status.in_(("QUEUED", "RUNNING")))).all()
    return {
        **model_dict(agent),
        "current_load": len(active),
        "active_run_ids": [run.id for run in active],
        "current_task_ids": [run.task_id for run in active],
    }


def assign_agent(db: Session, *, task: CoreTask, agent: CoreAgent, assigned_by: str) -> CoreTaskAssignment:
    if agent.workspace_id != task.workspace_id:
        raise HTTPException(status_code=404, detail="Core agent not found")
    if not agent.available or agent.status in {"DISABLED", "PAUSED"}:
        raise HTTPException(status_code=409, detail="Agent is unavailable")
    required = {item.casefold() for item in (task.required_competencies or [])}
    available = {item.casefold() for item in (agent.competencies or [])}
    missing = sorted(required - available)
    if missing:
        raise HTTPException(status_code=409, detail=f"Agent lacks competencies: {', '.join(missing)}")
    if "execute_task" not in (agent.allowed_actions or []):
        raise HTTPException(status_code=409, detail="Agent is not allowed to execute tasks")
    assignment = CoreTaskAssignment(
        workspace_id=task.workspace_id,
        project_id=task.project_id,
        task_id=task.id,
        agent_id=agent.id,
        assigned_by=assigned_by,
    )
    before = model_dict(task)
    task.agent_id = agent.id
    db.add(assignment)
    record_event(db, workspace_id=task.workspace_id, actor_id=assigned_by, action="task.agent_assigned", entity_type="CoreTask", entity_id=task.id, before=before, after=model_dict(task), evidence={"agent_id": agent.id, "assignment_id": assignment.id})
    return assignment


def create_run(db: Session, *, task: CoreTask, agent: CoreAgent, initiated_by: str, context: dict[str, Any]) -> CoreRun:
    if task.agent_id != agent.id:
        raise HTTPException(status_code=409, detail="Task must be assigned to this agent before launch")
    if incomplete_blockers(db, task.id):
        raise HTTPException(status_code=409, detail="Task is blocked by incomplete dependencies")
    if not agent.available or agent.status in {"DISABLED", "PAUSED"}:
        raise HTTPException(status_code=409, detail="Agent is unavailable")
    if "execute_task" not in (agent.allowed_actions or []):
        raise HTTPException(status_code=409, detail="Agent is not allowed to execute tasks")
    if active_run_count(db, agent.id) >= max(1, agent.concurrency_limit):
        raise HTTPException(status_code=409, detail="Agent concurrency limit reached")
    run = CoreRun(workspace_id=task.workspace_id, project_id=task.project_id, task_id=task.id, agent_id=agent.id, initiated_by=initiated_by, context=context)
    db.add(run)
    db.flush()
    record_event(db, workspace_id=task.workspace_id, actor_id=initiated_by, action="run.queued", entity_type="CoreRun", entity_id=run.id, after=model_dict(run), evidence={"task_id": task.id, "agent_id": agent.id})
    return run


def transition_run(db: Session, *, run: CoreRun, status: str, actor_id: str, result_summary: str | None = None, error_reason: str | None = None) -> CoreRun:
    if status not in RUN_TRANSITIONS.get(run.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid run transition: {run.status} -> {status}")
    if status == "SUCCEEDED" and not result_summary:
        raise HTTPException(status_code=422, detail="Successful run requires result")
    if status in {"FAILED", "CANCELLED"} and not error_reason:
        raise HTTPException(status_code=422, detail="Failed or cancelled run requires reason")
    before = model_dict(run)
    run.status = status
    if status == "RUNNING":
        run.started_at = datetime.utcnow()
    if status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        run.finished_at = datetime.utcnow()
    if result_summary is not None:
        run.result_summary = result_summary
    if status == "SUCCEEDED" and result_summary:
        task = db.get(CoreTask, run.task_id)
        if task is not None:
            before_task = model_dict(task)
            task.result_summary = result_summary
            record_event(
                db,
                workspace_id=task.workspace_id,
                actor_id=actor_id,
                action="task.result_recorded",
                entity_type="CoreTask",
                entity_id=task.id,
                before=before_task,
                after=model_dict(task),
                evidence={"run_id": run.id},
            )
    if error_reason is not None:
        run.error_reason = error_reason
    record_event(db, workspace_id=run.workspace_id, actor_id=actor_id, action=f"run.{status.casefold()}", entity_type="CoreRun", entity_id=run.id, before=before, after=model_dict(run), evidence={"task_id": run.task_id, "agent_id": run.agent_id})
    return run
