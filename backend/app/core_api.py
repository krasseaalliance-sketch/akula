"""HTTP API for the Core Release 1 foundation."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user
from .core_models import CoreAgent, CoreArtifact, CoreEvent, CoreMission, CoreProductionEvidence, CoreProduct, CoreProject, CoreRun, CoreSprint, CoreTask, CoreTaskAssignment, CoreTaskDependency, CoreVerification
from . import core_services
from .core_schemas import (
    CoreAgentAssignmentCreate, CoreAgentAssignmentResponse, CoreAgentResponse, CoreArtifactCreate, CoreArtifactPatch, CoreArtifactResponse, CoreArtifactVersionCreate, CoreDependencyCreate,
    CoreDependencyResponse, CoreEventResponse, CoreMissionCreate, CoreMissionPatch,
    CoreMissionResponse, CoreProductCreate, CoreProductPatch, CoreProductResponse,
    CoreProjectCreate, CoreProjectPatch, CoreProjectResponse, CoreSprintCreate,
    CoreSprintPatch, CoreSprintResponse, CoreTaskCreate, CoreTaskPatch, CoreTaskResponse,
    CoreTaskStatusPatch, CoreRunCreate, CoreRunResponse, CoreRunTransition, CoreRouteResponse, CoreRouteStepResponse, CoreVerificationComplete, CoreVerificationCreate, CoreVerificationResponse, CoreProductionEvidenceCreate, CoreProductionEvidenceResponse,
)
from .core_services import active_run_count, agent_snapshot, assign_agent, complete_verification, create_artifact_version, create_run, create_verification, ensure_workspace_entity, incomplete_blockers, mission_for, project_for, qa_agent_for_user, record_event, require_core_workspace, require_product, sprint_for, store_artifact_upload, transition_artifact, transition_run, transition_task, verify_and_accept_task, would_create_cycle
from .db import get_db
from .models import User
from .services import model_dict, role_for


router = APIRouter(prefix="/api/core", tags=["core"])


@router.get("/products", response_model=list[CoreProductResponse])
def list_products(workspace_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, workspace_id)
    return list(db.scalars(select(CoreProduct).where(CoreProduct.workspace_id == workspace_id).order_by(CoreProduct.name)).all())


@router.post("/products", response_model=CoreProductResponse, status_code=201)
def create_product(payload: CoreProductCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, payload.workspace_id, "core.manage")
    existing = db.scalar(select(CoreProduct).where(CoreProduct.workspace_id == payload.workspace_id, CoreProduct.product_key == payload.product_key))
    if existing:
        raise HTTPException(status_code=409, detail="Core product key already exists")
    product = CoreProduct(**payload.model_dump(), created_by=user.id)
    db.add(product)
    db.flush()
    record_event(db, workspace_id=product.workspace_id, actor_id=user.id, action="product.created", entity_type="CoreProduct", entity_id=product.id, after=model_dict(product))
    db.commit()
    return product


@router.get("/products/{product_id}", response_model=CoreProductResponse)
def get_product(product_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ensure_workspace_entity(db, user, db.get(CoreProduct, product_id))


@router.patch("/products/{product_id}", response_model=CoreProductResponse)
def patch_product(product_id: str, payload: CoreProductPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = ensure_workspace_entity(db, user, db.get(CoreProduct, product_id), "core.manage")
    before = model_dict(product)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    record_event(db, workspace_id=product.workspace_id, actor_id=user.id, action="product.updated", entity_type="CoreProduct", entity_id=product.id, before=before, after=model_dict(product))
    db.commit()
    return product


@router.get("/projects", response_model=list[CoreProjectResponse])
def list_projects(workspace_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, workspace_id)
    return list(db.scalars(select(CoreProject).where(CoreProject.workspace_id == workspace_id).order_by(CoreProject.created_at.desc())).all())


@router.post("/projects", response_model=CoreProjectResponse, status_code=201)
def create_project(payload: CoreProjectCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, payload.workspace_id, "core.manage")
    product = require_product(db, user, payload.product_id, payload.workspace_id)
    project = CoreProject(workspace_id=payload.workspace_id, product_id=product.id, name=payload.name, objective=payload.objective, created_by=user.id)
    db.add(project)
    db.flush()
    record_event(db, workspace_id=project.workspace_id, actor_id=user.id, action="project.created", entity_type="CoreProject", entity_id=project.id, after=model_dict(project))
    db.commit()
    return project


@router.get("/projects/{project_id}", response_model=CoreProjectResponse)
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ensure_workspace_entity(db, user, db.get(CoreProject, project_id))


@router.patch("/projects/{project_id}", response_model=CoreProjectResponse)
def patch_project(project_id: str, payload: CoreProjectPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = ensure_workspace_entity(db, user, db.get(CoreProject, project_id), "core.manage")
    before = model_dict(project)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    record_event(db, workspace_id=project.workspace_id, actor_id=user.id, action="project.updated", entity_type="CoreProject", entity_id=project.id, before=before, after=model_dict(project))
    db.commit()
    return project


@router.get("/projects/{project_id}/structure")
def project_structure(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = ensure_workspace_entity(db, user, db.get(CoreProject, project_id))
    missions = list(db.scalars(select(CoreMission).where(CoreMission.project_id == project.id).order_by(CoreMission.created_at)).all())
    sprints = list(db.scalars(select(CoreSprint).where(CoreSprint.project_id == project.id).order_by(CoreSprint.created_at)).all())
    tasks = list(db.scalars(select(CoreTask).where(CoreTask.project_id == project.id).order_by(CoreTask.created_at)).all())
    dependencies = list(db.scalars(select(CoreTaskDependency).where(CoreTaskDependency.project_id == project.id).order_by(CoreTaskDependency.created_at)).all())
    return {"project": model_dict(project), "missions": [model_dict(item) for item in missions], "sprints": [model_dict(item) for item in sprints], "tasks": [model_dict(item) for item in tasks], "dependencies": [model_dict(item) for item in dependencies]}


@router.post("/projects/{project_id}/missions", response_model=CoreMissionResponse, status_code=201)
def create_mission(project_id: str, payload: CoreMissionCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = ensure_workspace_entity(db, user, db.get(CoreProject, project_id), "core.manage")
    mission = CoreMission(project_id=project.id, created_by=user.id, **payload.model_dump())
    db.add(mission)
    db.flush()
    record_event(db, workspace_id=project.workspace_id, actor_id=user.id, action="mission.created", entity_type="CoreMission", entity_id=mission.id, after=model_dict(mission))
    db.commit()
    return mission


@router.get("/missions", response_model=list[CoreMissionResponse])
def list_missions(project_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = ensure_workspace_entity(db, user, db.get(CoreProject, project_id))
    return list(db.scalars(select(CoreMission).where(CoreMission.project_id == project.id).order_by(CoreMission.created_at.desc())).all())


@router.get("/missions/{mission_id}", response_model=CoreMissionResponse)
def get_mission(mission_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mission = db.get(CoreMission, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Core mission not found")
    project = ensure_workspace_entity(db, user, db.get(CoreProject, mission.project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Core mission not found")
    return mission


@router.patch("/missions/{mission_id}", response_model=CoreMissionResponse)
def patch_mission(mission_id: str, payload: CoreMissionPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mission = db.get(CoreMission, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Core mission not found")
    project = ensure_workspace_entity(db, user, db.get(CoreProject, mission.project_id), "core.manage")
    before = model_dict(mission)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(mission, key, value)
    record_event(db, workspace_id=project.workspace_id, actor_id=user.id, action="mission.updated", entity_type="CoreMission", entity_id=mission.id, before=before, after=model_dict(mission))
    db.commit()
    return mission


@router.post("/projects/{project_id}/missions/{mission_id}/sprints", response_model=CoreSprintResponse, status_code=201)
def create_sprint(project_id: str, mission_id: str, payload: CoreSprintCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = ensure_workspace_entity(db, user, db.get(CoreProject, project_id), "core.manage")
    mission_for(db, mission_id, project.id)
    sprint = CoreSprint(project_id=project.id, mission_id=mission_id, created_by=user.id, **payload.model_dump())
    db.add(sprint)
    db.flush()
    record_event(db, workspace_id=project.workspace_id, actor_id=user.id, action="sprint.created", entity_type="CoreSprint", entity_id=sprint.id, after=model_dict(sprint))
    db.commit()
    return sprint


@router.get("/sprints", response_model=list[CoreSprintResponse])
def list_sprints(project_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = ensure_workspace_entity(db, user, db.get(CoreProject, project_id))
    return list(db.scalars(select(CoreSprint).where(CoreSprint.project_id == project.id).order_by(CoreSprint.created_at.desc())).all())


@router.get("/sprints/{sprint_id}", response_model=CoreSprintResponse)
def get_sprint(sprint_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sprint = db.get(CoreSprint, sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail="Core sprint not found")
    ensure_workspace_entity(db, user, db.get(CoreProject, sprint.project_id))
    return sprint


@router.patch("/sprints/{sprint_id}", response_model=CoreSprintResponse)
def patch_sprint(sprint_id: str, payload: CoreSprintPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sprint = db.get(CoreSprint, sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail="Core sprint not found")
    project = ensure_workspace_entity(db, user, db.get(CoreProject, sprint.project_id), "core.manage")
    before = model_dict(sprint)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sprint, key, value)
    record_event(db, workspace_id=project.workspace_id, actor_id=user.id, action="sprint.updated", entity_type="CoreSprint", entity_id=sprint.id, before=before, after=model_dict(sprint))
    db.commit()
    return sprint


@router.post("/projects/{project_id}/sprints/{sprint_id}/tasks", response_model=CoreTaskResponse, status_code=201)
def create_task(project_id: str, sprint_id: str, payload: CoreTaskCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = ensure_workspace_entity(db, user, db.get(CoreProject, project_id), "core.manage")
    sprint = sprint_for(db, sprint_id, project.id)
    if payload.agent_id:
        agent = db.get(CoreAgent, payload.agent_id)
        if agent is None or agent.workspace_id != project.workspace_id:
            raise HTTPException(status_code=404, detail="Core agent not found")
    task_payload = payload.model_dump()
    requested_agent_id = task_payload.pop("agent_id", None)
    task = CoreTask(workspace_id=project.workspace_id, project_id=project.id, sprint_id=sprint.id, created_by=user.id, agent_id=None, **task_payload)
    db.add(task)
    db.flush()
    if requested_agent_id:
        assignment_agent = db.get(CoreAgent, requested_agent_id)
        if assignment_agent is None or assignment_agent.workspace_id != task.workspace_id:
            raise HTTPException(status_code=404, detail="Core agent not found")
        assign_agent(db, task=task, agent=assignment_agent, assigned_by=user.id)
    record_event(db, workspace_id=project.workspace_id, actor_id=user.id, action="task.created", entity_type="CoreTask", entity_id=task.id, after=model_dict(task))
    db.commit()
    return task


@router.get("/tasks", response_model=list[CoreTaskResponse])
def list_tasks(workspace_id: str = Query(...), sprint_id: str | None = Query(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, workspace_id)
    query = select(CoreTask).where(CoreTask.workspace_id == workspace_id)
    if sprint_id:
        query = query.where(CoreTask.sprint_id == sprint_id)
    return list(db.scalars(query.order_by(CoreTask.created_at.desc())).all())


@router.get("/tasks/{task_id}")
def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id))
    artifacts = list(db.scalars(select(CoreArtifact).where(CoreArtifact.task_id == task.id).order_by(CoreArtifact.created_at.desc())).all())
    verifications = list(db.scalars(select(CoreVerification).where(CoreVerification.task_id == task.id).order_by(CoreVerification.created_at.desc())).all())
    dependencies = list(db.scalars(select(CoreTaskDependency).where(CoreTaskDependency.dependent_task_id == task.id).order_by(CoreTaskDependency.created_at)).all())
    events = list(db.scalars(select(CoreEvent).where(CoreEvent.workspace_id == task.workspace_id, CoreEvent.entity_id == task.id).order_by(CoreEvent.created_at.desc())).all())
    blockers = incomplete_blockers(db, task.id)
    return {"task": model_dict(task), "artifacts": [model_dict(item) for item in artifacts], "verifications": [model_dict(item) for item in verifications], "dependencies": [model_dict(item) for item in dependencies], "blockers": [model_dict(item) for item in blockers], "events": [model_dict(item) for item in events]}


@router.patch("/tasks/{task_id}", response_model=CoreTaskResponse)
def patch_task(task_id: str, payload: CoreTaskPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    updates = payload.model_dump(exclude_unset=True)
    requested_agent_id = updates.pop("agent_id", None) if "agent_id" in updates else None
    if requested_agent_id and requested_agent_id != task.agent_id:
        agent = db.get(CoreAgent, requested_agent_id)
        if agent is None or agent.workspace_id != task.workspace_id:
            raise HTTPException(status_code=404, detail="Core agent not found")
        assign_agent(db, task=task, agent=agent, assigned_by=user.id)
    elif "agent_id" in payload.model_fields_set and requested_agent_id is None:
        task.agent_id = None
    before = model_dict(task)
    for key, value in updates.items():
        setattr(task, key, value)
    record_event(db, workspace_id=task.workspace_id, actor_id=user.id, action="task.updated", entity_type="CoreTask", entity_id=task.id, before=before, after=model_dict(task))
    db.commit()
    return task


@router.patch("/tasks/{task_id}/status", response_model=CoreTaskResponse)
def patch_task_status(task_id: str, payload: CoreTaskStatusPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    transition_task(db, task, payload.status, user.id, result_summary=payload.result_summary, return_reason=payload.return_reason)
    db.commit()
    return task


@router.post("/tasks/{task_id}/dependencies", response_model=CoreDependencyResponse, status_code=201)
def create_dependency(task_id: str, payload: CoreDependencyCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dependent = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    predecessor = ensure_workspace_entity(db, user, db.get(CoreTask, payload.predecessor_task_id), "core.manage")
    if predecessor.project_id != dependent.project_id:
        raise HTTPException(status_code=409, detail="Dependencies must stay inside one project")
    if predecessor.id == dependent.id:
        raise HTTPException(status_code=409, detail="A task cannot depend on itself")
    if db.scalar(select(CoreTaskDependency).where(CoreTaskDependency.dependent_task_id == dependent.id, CoreTaskDependency.predecessor_task_id == predecessor.id)):
        raise HTTPException(status_code=409, detail="Dependency already exists")
    if would_create_cycle(db, dependent_task_id=dependent.id, predecessor_task_id=predecessor.id):
        raise HTTPException(status_code=409, detail="Dependency would create a cycle")
    dependency = CoreTaskDependency(workspace_id=dependent.workspace_id, project_id=dependent.project_id, dependent_task_id=dependent.id, predecessor_task_id=predecessor.id, created_by=user.id)
    db.add(dependency)
    db.flush()
    record_event(db, workspace_id=dependent.workspace_id, actor_id=user.id, action="task.dependency_created", entity_type="CoreTaskDependency", entity_id=dependency.id, after=model_dict(dependency))
    db.commit()
    return dependency


@router.delete("/dependencies/{dependency_id}", status_code=204)
def delete_dependency(dependency_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dependency = ensure_workspace_entity(db, user, db.get(CoreTaskDependency, dependency_id), "core.manage")
    before = model_dict(dependency)
    record_event(db, workspace_id=dependency.workspace_id, actor_id=user.id, action="task.dependency_deleted", entity_type="CoreTaskDependency", entity_id=dependency.id, before=before)
    db.delete(dependency)
    db.commit()


@router.get("/tasks/{task_id}/blockers")
def task_blockers(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id))
    blockers = incomplete_blockers(db, task.id)
    return {"task_id": task.id, "blocked": bool(blockers), "blockers": [model_dict(item) for item in blockers]}


@router.post("/tasks/{task_id}/artifacts", response_model=CoreArtifactResponse, status_code=201)
def create_artifact(task_id: str, payload: CoreArtifactCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    artifact = create_artifact_version(db, task=task, actor_id=user.id, payload=payload.model_dump())
    record_event(db, workspace_id=task.workspace_id, actor_id=user.id, action="artifact.created", entity_type="CoreArtifact", entity_id=artifact.id, after=model_dict(artifact))
    db.commit()
    return artifact


@router.post("/tasks/{task_id}/artifacts/upload", response_model=CoreArtifactResponse, status_code=201)
async def upload_artifact(
    task_id: str,
    request: Request,
    artifact_type: str = Query(...),
    name: str = Query(..., min_length=1, max_length=240),
    version: str = Query("1", min_length=1, max_length=80),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    content = await request.body()
    original_name = request.headers.get("x-file-name") or name
    content_type = request.headers.get("content-type") or "application/octet-stream"
    artifact = store_artifact_upload(
        db,
        task=task,
        actor_id=user.id,
        artifact_type=artifact_type,
        name=name,
        version=version,
        original_name=original_name,
        content_type=content_type,
        content=content,
    )
    record_event(
        db,
        workspace_id=task.workspace_id,
        actor_id=user.id,
        action="artifact.uploaded",
        entity_type="CoreArtifact",
        entity_id=artifact.id,
        after=model_dict(artifact),
        evidence={"filename": original_name, "size": len(content), "content_type": content_type},
    )
    db.commit()
    return artifact


@router.get("/tasks/{task_id}/artifacts", response_model=list[CoreArtifactResponse])
def list_task_artifacts(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id))
    return list(db.scalars(select(CoreArtifact).where(CoreArtifact.task_id == task.id).order_by(CoreArtifact.artifact_key, CoreArtifact.version)).all())


@router.get("/artifacts/{artifact_id}", response_model=CoreArtifactResponse)
def get_artifact(artifact_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ensure_workspace_entity(db, user, db.get(CoreArtifact, artifact_id))


@router.get("/artifacts/{artifact_id}/content")
def get_artifact_content(artifact_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artifact = ensure_workspace_entity(db, user, db.get(CoreArtifact, artifact_id))
    if artifact.artifact_type not in {"FILE", "IMAGE"}:
        raise HTTPException(status_code=409, detail="Only FILE and IMAGE artifacts have binary content")
    path = core_services.ARTIFACT_STORAGE_ROOT / artifact.workspace_id / artifact.task_id / artifact.id
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact content is unavailable")
    metadata = artifact.metadata_json or {}
    return FileResponse(
        path,
        media_type=metadata.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": "inline"},
    )


@router.patch("/artifacts/{artifact_id}", response_model=CoreArtifactResponse)
def patch_artifact(artifact_id: str, payload: CoreArtifactPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artifact = ensure_workspace_entity(db, user, db.get(CoreArtifact, artifact_id), "core.manage")
    transition_artifact(db, artifact=artifact, actor_id=user.id, status=payload.status)
    db.commit()
    return artifact


@router.post("/artifacts/{artifact_id}/versions", response_model=CoreArtifactResponse, status_code=201)
def create_artifact_version_endpoint(artifact_id: str, payload: CoreArtifactVersionCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    previous = ensure_workspace_entity(db, user, db.get(CoreArtifact, artifact_id), "core.manage")
    task = ensure_workspace_entity(db, user, db.get(CoreTask, previous.task_id), "core.manage")
    artifact = create_artifact_version(db, task=task, actor_id=user.id, payload=payload.model_dump(), artifact_key=previous.artifact_key)
    for sibling in db.scalars(select(CoreArtifact).where(CoreArtifact.workspace_id == task.workspace_id, CoreArtifact.artifact_key == previous.artifact_key, CoreArtifact.id != artifact.id, CoreArtifact.status != "SUPERSEDED")).all():
        transition_artifact(db, artifact=sibling, actor_id=user.id, status="SUPERSEDED")
    record_event(db, workspace_id=task.workspace_id, actor_id=user.id, action="artifact.version_created", entity_type="CoreArtifact", entity_id=artifact.id, after=model_dict(artifact), evidence={"supersedes_id": previous.id})
    db.commit()
    return artifact


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artifact = ensure_workspace_entity(db, user, db.get(CoreArtifact, artifact_id), "core.manage")
    if artifact.status != "SUPERSEDED":
        transition_artifact(db, artifact=artifact, actor_id=user.id, status="SUPERSEDED")
    record_event(db, workspace_id=artifact.workspace_id, actor_id=user.id, action="artifact.deleted", entity_type="CoreArtifact", entity_id=artifact.id, after=model_dict(artifact), evidence={"physical_delete": False})
    db.commit()
    return None


@router.post("/tasks/{task_id}/qa", response_model=CoreVerificationResponse, status_code=201)
def create_qa_request(task_id: str, payload: CoreVerificationCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.accept")
    qa_agent = db.get(CoreAgent, payload.qa_agent_id) if payload.qa_agent_id else qa_agent_for_user(db, workspace_id=task.workspace_id, user_id=user.id)
    if qa_agent is not None and qa_agent.workspace_id != task.workspace_id:
        raise HTTPException(status_code=404, detail="QA agent not found")
    if payload.idempotency_key:
        existing = db.scalar(select(CoreVerification).where(CoreVerification.workspace_id == task.workspace_id, CoreVerification.idempotency_key == payload.idempotency_key))
        if existing:
            return JSONResponse(status_code=200, content=model_dict(existing))
    verification = create_verification(db, task=task, user=user, qa_agent=qa_agent, artifact_id=payload.artifact_id, checked_artifact_version=payload.checked_artifact_version, idempotency_key=payload.idempotency_key)
    db.commit()
    return verification


@router.get("/tasks/{task_id}/qa", response_model=list[CoreVerificationResponse])
def list_qa_requests(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id))
    return list(db.scalars(select(CoreVerification).where(CoreVerification.task_id == task.id).order_by(CoreVerification.created_at.desc())).all())


@router.post("/qa/{verification_id}/complete", response_model=CoreVerificationResponse)
def complete_qa_request(verification_id: str, payload: CoreVerificationComplete, user: User = Depends(current_user), db: Session = Depends(get_db)):
    verification = ensure_workspace_entity(db, user, db.get(CoreVerification, verification_id), "core.accept")
    task = ensure_workspace_entity(db, user, db.get(CoreTask, verification.task_id), "core.accept")
    complete_verification(db, verification=verification, task=task, user=user, status=payload.status, checklist=payload.checklist, evidence=payload.evidence, comment=payload.comment, defect=payload.defect, remediation_action=payload.remediation_action)
    db.commit()
    return verification


@router.post("/tasks/{task_id}/verifications", response_model=CoreVerificationResponse, status_code=201)
def verify_task(task_id: str, payload: CoreVerificationCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Compatibility endpoint for the Day 1 acceptance contract."""
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.accept")
    qa_agent = db.get(CoreAgent, payload.qa_agent_id) if payload.qa_agent_id else qa_agent_for_user(db, workspace_id=task.workspace_id, user_id=user.id)
    verification = create_verification(db, task=task, user=user, qa_agent=qa_agent, artifact_id=payload.artifact_id, checked_artifact_version=payload.checked_artifact_version, idempotency_key=payload.idempotency_key)
    if payload.result:
        complete_verification(db, verification=verification, task=task, user=user, status=payload.result, checklist=payload.checklist, evidence=payload.evidence, comment=payload.notes, defect=None, remediation_action=None)
    db.commit()
    return verification


@router.post("/tasks/{task_id}/production-evidence", response_model=CoreProductionEvidenceResponse, status_code=201)
def create_production_evidence(task_id: str, payload: CoreProductionEvidenceCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    if not payload.checklist or any(item.get("passed") is not True for item in payload.checklist):
        raise HTTPException(status_code=422, detail="Production evidence requires a fully passed checklist")
    if payload.run_id is not None:
        run = db.get(CoreRun, payload.run_id)
        if run is None or run.workspace_id != task.workspace_id or run.task_id != task.id:
            raise HTTPException(status_code=404, detail="Run not found for task")
    artifact = create_artifact_version(db, task=task, actor_id=user.id, payload={
        "artifact_key": f"production:{payload.build_id}",
        "artifact_type": "RELEASE",
        "name": f"Production evidence {payload.build_id}",
        "uri": payload.public_url,
        "version": payload.build_id,
        "metadata_json": {"public_url": payload.public_url, "build_id": payload.build_id, "checked_at": payload.checked_at.isoformat(), "executor_id": user.id, "screenshot_uri": payload.screenshot_uri, "logs_uri": payload.logs_uri, "checklist": payload.checklist, "result": payload.result},
        "run_id": payload.run_id,
    })
    evidence = CoreProductionEvidence(workspace_id=task.workspace_id, task_id=task.id, run_id=payload.run_id, artifact_id=artifact.id, public_url=payload.public_url, build_id=payload.build_id, checked_at=payload.checked_at, executor_id=user.id, screenshot_uri=payload.screenshot_uri, logs_uri=payload.logs_uri, checklist=payload.checklist, result=payload.result)
    db.add(evidence)
    db.flush()
    record_event(db, workspace_id=task.workspace_id, actor_id=user.id, action="production_evidence.created", entity_type="CoreProductionEvidence", entity_id=evidence.id, after={**model_dict(evidence), "artifact_id": artifact.id})
    db.commit()
    return {**model_dict(evidence), "artifact": artifact}


@router.get("/agents", response_model=list[CoreAgentResponse])
def list_agents(workspace_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, workspace_id)
    return [agent_snapshot(db, agent) for agent in db.scalars(select(CoreAgent).where(CoreAgent.workspace_id == workspace_id).order_by(CoreAgent.agent_key)).all()]


@router.get("/agents/{agent_id}", response_model=CoreAgentResponse)
def get_agent(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    agent = ensure_workspace_entity(db, user, db.get(CoreAgent, agent_id))
    return agent_snapshot(db, agent)


@router.get("/agents/{agent_id}/assignments", response_model=list[CoreAgentAssignmentResponse])
def agent_assignments(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    agent = ensure_workspace_entity(db, user, db.get(CoreAgent, agent_id))
    return list(db.scalars(select(CoreTaskAssignment).where(CoreTaskAssignment.agent_id == agent.id).order_by(CoreTaskAssignment.assigned_at.desc())).all())


@router.post("/tasks/{task_id}/assignment", response_model=CoreAgentAssignmentResponse, status_code=201)
def assign_task_agent(task_id: str, payload: CoreAgentAssignmentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    agent = db.get(CoreAgent, payload.agent_id)
    if agent is None or agent.workspace_id != task.workspace_id:
        raise HTTPException(status_code=404, detail="Core agent not found")
    assignment = assign_agent(db, task=task, agent=agent, assigned_by=user.id)
    db.commit()
    return assignment


@router.get("/runs", response_model=list[CoreRunResponse])
def list_runs(workspace_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, workspace_id)
    return list(db.scalars(select(CoreRun).where(CoreRun.workspace_id == workspace_id).order_by(CoreRun.queued_at.desc())).all())


@router.get("/runs/{run_id}", response_model=CoreRunResponse)
def get_run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ensure_workspace_entity(db, user, db.get(CoreRun, run_id))


@router.post("/tasks/{task_id}/runs", response_model=CoreRunResponse, status_code=201)
def launch_run(task_id: str, payload: CoreRunCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    if task.agent_id is None:
        raise HTTPException(status_code=409, detail="Task must have an assigned agent before launch")
    agent = db.get(CoreAgent, task.agent_id)
    if agent is None or agent.workspace_id != task.workspace_id:
        raise HTTPException(status_code=404, detail="Core agent not found")
    run = create_run(db, task=task, agent=agent, initiated_by=user.id, context=payload.model_dump())
    db.commit()
    return run


@router.post("/runs/{run_id}/transition", response_model=CoreRunResponse)
def update_run(run_id: str, payload: CoreRunTransition, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = ensure_workspace_entity(db, user, db.get(CoreRun, run_id), "core.manage")
    transition_run(db, run=run, status=payload.status, actor_id=user.id, result_summary=payload.result_summary, error_reason=payload.error_reason)
    db.commit()
    return run


@router.post("/tasks/{task_id}/route", response_model=CoreRouteResponse)
def prepare_route(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = ensure_workspace_entity(db, user, db.get(CoreTask, task_id), "core.manage")
    required = {item.casefold() for item in (task.required_competencies or [])}
    candidates = list(db.scalars(select(CoreAgent).where(CoreAgent.workspace_id == task.workspace_id, CoreAgent.available.is_(True), CoreAgent.status.notin_(("DISABLED", "PAUSED")))).all())
    candidates = [agent for agent in candidates if required.issubset({item.casefold() for item in (agent.competencies or [])}) and "execute_task" in (agent.allowed_actions or [])]
    if task.agent_id:
        candidates.sort(key=lambda agent: 0 if agent.id == task.agent_id else 1)
    steps = [CoreRouteStepResponse(step=index, agent_id=agent.id, agent_key=agent.agent_key, name=agent.name, competencies=agent.competencies or []) for index, agent in enumerate(candidates, start=1)]
    return CoreRouteResponse(task_id=task.id, steps=steps, next_step=1 if steps else None)


@router.get("/events", response_model=list[CoreEventResponse])
def list_events(workspace_id: str = Query(...), limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, workspace_id)
    return list(db.scalars(select(CoreEvent).where(CoreEvent.workspace_id == workspace_id).order_by(CoreEvent.created_at.desc()).limit(limit)).all())


@router.get("/events/{entity_type}/{entity_id}", response_model=list[CoreEventResponse])
def entity_events(entity_type: str, entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    events = list(db.scalars(select(CoreEvent).where(CoreEvent.entity_type == entity_type, CoreEvent.entity_id == entity_id).order_by(CoreEvent.created_at.desc()).limit(100)).all())
    if not events:
        raise HTTPException(status_code=404, detail="Core entity not found")
    require_core_workspace(db, user, events[0].workspace_id)
    return events


@router.get("/context")
def core_context(workspace_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace = require_core_workspace(db, user, workspace_id)
    return {"user": {"id": user.id, "email": user.email, "name": user.name}, "workspace": model_dict(workspace), "role": role_for(db, user.id, workspace_id)}


@router.get("/overview")
def overview(workspace_id: str = Query(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_core_workspace(db, user, workspace_id)
    tasks = list(db.scalars(select(CoreTask).where(CoreTask.workspace_id == workspace_id)).all())
    return {
        "workspace_id": workspace_id,
        "projects": len(db.scalars(select(CoreProject).where(CoreProject.workspace_id == workspace_id)).all()),
        "active_sprints": len(db.scalars(select(CoreSprint).where(CoreSprint.project_id.in_(select(CoreProject.id).where(CoreProject.workspace_id == workspace_id)), CoreSprint.status == "ACTIVE")).all()),
        "tasks": {"total": len(tasks), "in_progress": sum(item.status == "IN_PROGRESS" for item in tasks), "in_review": sum(item.status == "IN_REVIEW" for item in tasks), "accepted": sum(item.status == "ACCEPTED" for item in tasks), "blocked": sum(item.status == "BLOCKED" for item in tasks)},
    }
