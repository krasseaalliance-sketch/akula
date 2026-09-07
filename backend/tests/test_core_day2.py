from fastapi.testclient import TestClient
from app.core_models import CoreAgent
from app.db import get_db
from app.main import app
from app.security import create_access_token
from test_core_release1 import _db_and_owner


def _headers(owner):
    return {"Authorization": f"Bearer {create_access_token(owner.id)}"}


def _tree(client, workspace_id, headers, prefix="A"):
    product = client.post("/api/core/products", headers=headers, json={"workspace_id": workspace_id, "product_key": f"{prefix.lower()}-product", "name": f"Product {prefix}"}).json()
    project = client.post("/api/core/projects", headers=headers, json={"workspace_id": workspace_id, "product_id": product["id"], "name": f"Project {prefix}", "objective": "Objective"}).json()
    mission = client.post(f"/api/core/projects/{project['id']}/missions", headers=headers, json={"title": f"Mission {prefix}", "goal": "Goal"}).json()
    sprint = client.post(f"/api/core/projects/{project['id']}/missions/{mission['id']}/sprints", headers=headers, json={"name": f"Sprint {prefix}", "goal": "Sprint goal"}).json()
    task_one = client.post(f"/api/core/projects/{project['id']}/sprints/{sprint['id']}/tasks", headers=headers, json={"title": f"Task {prefix}1", "description": "First"}).json()
    task_two = client.post(f"/api/core/projects/{project['id']}/sprints/{sprint['id']}/tasks", headers=headers, json={"title": f"Task {prefix}2", "description": "Second"}).json()
    return product, project, mission, sprint, task_one, task_two


def test_day2_dependency_blocks_run_and_is_visible():
    db, owner, _qa, workspace = _db_and_owner()
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    headers = _headers(owner)
    try:
        _product, project, _mission, _sprint, first, dependent = _tree(client, workspace.id, headers)
        response = client.post(f"/api/core/tasks/{dependent['id']}/dependencies", headers=headers, json={"predecessor_task_id": first["id"]})
        assert response.status_code == 201, response.text
        blockers = client.get(f"/api/core/tasks/{dependent['id']}/blockers", headers=headers)
        assert blockers.status_code == 200
        assert blockers.json()["blocked"] is True
        response = client.patch(f"/api/core/tasks/{dependent['id']}/status", headers=headers, json={"status": "PLANNED"})
        assert response.status_code == 200
        response = client.patch(f"/api/core/tasks/{dependent['id']}/status", headers=headers, json={"status": "IN_PROGRESS"})
        assert response.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_day2_rejects_cycles_and_cross_project_dependencies():
    db, owner, _qa, workspace = _db_and_owner()
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    headers = _headers(owner)
    try:
        _product, project, _mission, _sprint, first, second = _tree(client, workspace.id, headers)
        assert client.post(f"/api/core/tasks/{second['id']}/dependencies", headers=headers, json={"predecessor_task_id": first["id"]}).status_code == 201
        cycle = client.post(f"/api/core/tasks/{first['id']}/dependencies", headers=headers, json={"predecessor_task_id": second["id"]})
        assert cycle.status_code == 409
        _other_product, other_project, _other_mission, _other_sprint, other_first, _other_second = _tree(client, workspace.id, headers, prefix="B")
        cross = client.post(f"/api/core/tasks/{second['id']}/dependencies", headers=headers, json={"predecessor_task_id": other_first["id"]})
        assert cross.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_day2_edit_archive_and_detail_keep_audit_without_delete():
    db, owner, _qa, workspace = _db_and_owner()
    agent = CoreAgent(workspace_id=workspace.id, agent_key="developer", name="Developer", role="Developer", description="Builds", competencies=[], allowed_tools=[], allowed_actions=["execute_task"], limits={})
    db.add(agent)
    db.commit()
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    headers = _headers(owner)
    try:
        _product, project, _mission, _sprint, first, _dependent = _tree(client, workspace.id, headers)
        edited = client.patch(f"/api/core/tasks/{first['id']}", headers=headers, json={"title": "Renamed", "agent_id": agent.id, "priority": 1})
        assert edited.status_code == 200, edited.text
        archived = client.patch(f"/api/core/projects/{project['id']}", headers=headers, json={"status": "ARCHIVED"})
        assert archived.status_code == 200
        assert archived.json()["status"] == "ARCHIVED"
        detail = client.get(f"/api/core/tasks/{first['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["task"]["title"] == "Renamed"
        assert any(item["action"] == "task.updated" for item in detail.json()["events"])
        assert any(item["action"] == "project.updated" for item in client.get(f"/api/core/events?workspace_id={workspace.id}", headers=headers).json())
        assert db.get(__import__("app.core_models", fromlist=["CoreTask"]).CoreTask, first["id"]) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_day2_workspace_scope_hides_foreign_project_by_id():
    db, owner, _qa, workspace = _db_and_owner()
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    headers = _headers(owner)
    try:
        response = client.get("/api/core/projects/does-not-belong-to-workspace", headers=headers)
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
