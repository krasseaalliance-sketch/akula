from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db import get_db
from app.core_models import CoreAgent, CoreTask
from app.main import app
from app.models import Base, User, Workspace, WorkspaceMember
from app.security import create_access_token, hash_password


def _db_and_owner():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    owner = User(email="core-owner@example.local", name="Core Owner", password_hash=hash_password("secret"))
    qa = User(email="core-qa@example.local", name="Core QA", password_hash=hash_password("secret"))
    db.add_all([owner, qa])
    db.flush()
    workspace = Workspace(name="Core Workspace", slug="core-workspace", owner_id=owner.id)
    db.add(workspace)
    db.flush()
    db.add_all([
        WorkspaceMember(workspace_id=workspace.id, user_id=owner.id, role="OWNER", status="ACTIVE"),
        WorkspaceMember(workspace_id=workspace.id, user_id=qa.id, role="ANALYST", status="ACTIVE"),
    ])
    db.add(CoreAgent(
        workspace_id=workspace.id,
        user_id=qa.id,
        agent_key="qa-fixture",
        name="QA Fixture",
        role="QA-инженер",
        description="Independent QA fixture",
        competencies=["qa"],
        allowed_tools=[],
        allowed_actions=["execute_task"],
        limits={},
    ))
    db.commit()
    return db, owner, qa, workspace


def test_core_api_builds_and_accepts_only_with_artifact_and_evidence():
    db, owner, qa, workspace = _db_and_owner()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    try:
        product = client.post("/api/core/products", headers=headers, json={
            "workspace_id": workspace.id,
            "product_key": "scout",
            "name": "Scout",
        })
        assert product.status_code == 201, product.text
        project = client.post("/api/core/projects", headers=headers, json={
            "workspace_id": workspace.id,
            "product_id": product.json()["id"],
            "name": "Scout Release 1",
            "objective": "Поставить рабочий контур",
        })
        assert project.status_code == 201, project.text
        mission = client.post(f"/api/core/projects/{project.json()['id']}/missions", headers=headers, json={
            "title": "Рабочее ядро",
            "goal": "Довести задачу от постановки до QA",
            "acceptance_criteria": ["Есть доказательство результата"],
        })
        sprint = client.post(f"/api/core/projects/{project.json()['id']}/missions/{mission.json()['id']}/sprints", headers=headers, json={
            "name": "Неделя 1",
            "goal": "Foundation",
        })
        task = client.post(f"/api/core/projects/{project.json()['id']}/sprints/{sprint.json()['id']}/tasks", headers=headers, json={
            "title": "Проверить acceptance gate",
            "description": "Серверная проверка",
            "acceptance_criteria": ["PASS с evidence"],
        })
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]
        for status in ("PLANNED", "IN_PROGRESS"):
            response = client.patch(f"/api/core/tasks/{task_id}/status", headers=headers, json={"status": status})
            assert response.status_code == 200, response.text
        response = client.patch(f"/api/core/tasks/{task_id}/status", headers=headers, json={"status": "ACCEPTED"})
        assert response.status_code == 409
        response = client.patch(f"/api/core/tasks/{task_id}/status", headers=headers, json={"status": "IN_REVIEW", "result_summary": "Сценарий проверен"})
        assert response.status_code == 200, response.text
        artifact = client.post(f"/api/core/tasks/{task_id}/artifacts", headers=headers, json={
            "artifact_type": "TEST_REPORT",
            "name": "Core gate test",
            "uri": "test://core-release1",
        })
        assert artifact.status_code == 201, artifact.text
        qa_headers = {"Authorization": f"Bearer {create_access_token(qa.id)}"}
        verification = client.post(f"/api/core/tasks/{task_id}/verifications", headers=qa_headers, json={
            "artifact_id": artifact.json()["id"],
            "result": "PASS",
            "checklist": [{"name": "evidence", "passed": True}],
            "evidence": {"test": "pytest", "status": "passed"},
        })
        assert verification.status_code == 201, verification.text
        assert db.get(CoreTask, task_id).status == "ACCEPTED"
        events = client.get(f"/api/core/events?workspace_id={workspace.id}", headers=headers)
        assert events.status_code == 200
        assert any(item["action"] == "task.accepted" for item in events.json())
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_core_scope_rejects_foreign_workspace():
    db, owner, _qa, workspace = _db_and_owner()
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.get("/api/core/products?workspace_id=foreign", headers={"Authorization": f"Bearer {create_access_token(owner.id)}"})
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
