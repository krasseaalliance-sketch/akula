from uuid import uuid4
from fastapi.testclient import TestClient

from app.core_models import CoreAgent, CoreTask
from app.core_api import router
from app.db import get_db
from app.main import app
from app.models import Workspace, WorkspaceMember
from app.security import create_access_token
from test_core_release1 import _db_and_owner


def _client_with_db():
    db, owner, qa, workspace = _db_and_owner()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return db, owner, qa, workspace, TestClient(app)


def _task(client: TestClient, owner, workspace, required: list[str] | None = None) -> dict:
    headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    product = client.post("/api/core/products", headers=headers, json={"workspace_id": workspace.id, "product_key": f"day3-{uuid4().hex[:6]}", "name": "Day 3"}).json()
    project = client.post("/api/core/projects", headers=headers, json={"workspace_id": workspace.id, "product_id": product["id"], "name": "Agent project", "objective": "Run agent work"}).json()
    mission = client.post(f"/api/core/projects/{project['id']}/missions", headers=headers, json={"title": "Mission", "goal": "Goal"}).json()
    sprint = client.post(f"/api/core/projects/{project['id']}/missions/{mission['id']}/sprints", headers=headers, json={"name": "Sprint", "goal": "Goal"}).json()
    return client.post(f"/api/core/projects/{project['id']}/sprints/{sprint['id']}/tasks", headers=headers, json={"title": "Agent task", "description": "Task for agent", "required_competencies": required or ["code"]}).json()


def test_seed_contract_contains_ten_canonical_agents():
    from app.seed import CORE_AGENT_SPECS

    assert len(CORE_AGENT_SPECS) == 10
    assert [item[0] for item in CORE_AGENT_SPECS] == [
        "orchestrator", "product-analyst", "architect", "ux-ui-designer", "data-engineer",
        "developer", "qa-engineer", "project-manager", "copywriter", "editor",
    ]


def test_assignment_checks_competencies_and_records_history():
    db, owner, _qa, workspace, client = _client_with_db()
    try:
        agent = CoreAgent(workspace_id=workspace.id, agent_key="developer", name="Developer", role="Разработчик", description="Code", competencies=["code"], allowed_tools=[], limits={"max_parallel_tasks": 1}, allowed_actions=["execute_task"], concurrency_limit=1, available=True)
        db.add(agent); db.commit()
        task = _task(client, owner, workspace)
        headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
        assigned = client.post(f"/api/core/tasks/{task['id']}/assignment", headers=headers, json={"agent_id": agent.id})
        assert assigned.status_code == 201, assigned.text
        assert assigned.json()["agent_id"] == agent.id
        history = client.get(f"/api/core/agents/{agent.id}/assignments", headers=headers)
        assert history.status_code == 200
        assert len(history.json()) == 1
        assert history.json()[0]["assigned_by"] == owner.id
        bad = _task(client, owner, workspace, ["video"])
        rejected = client.post(f"/api/core/tasks/{bad['id']}/assignment", headers=headers, json={"agent_id": agent.id})
        assert rejected.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_assignment_is_workspace_scoped_and_agent_load_is_live():
    db, owner, _qa, workspace, client = _client_with_db()
    try:
        agent = CoreAgent(workspace_id=workspace.id, agent_key="developer", name="Developer", role="Разработчик", description="Code", competencies=["code"], allowed_tools=[], limits={"max_parallel_tasks": 1}, allowed_actions=["execute_task"], concurrency_limit=1, available=True)
        foreign = Workspace(name="Foreign", slug="foreign", owner_id=owner.id)
        db.add(foreign); db.flush()
        db.add(WorkspaceMember(workspace_id=foreign.id, user_id=owner.id, role="OWNER", status="ACTIVE"))
        foreign_agent = CoreAgent(workspace_id=foreign.id, agent_key="foreign", name="Foreign", role="Разработчик", description="Code", competencies=["code"], allowed_tools=[], limits={}, allowed_actions=["execute_task"], concurrency_limit=1, available=True)
        db.add_all([agent, foreign_agent]); db.commit()
        task = _task(client, owner, workspace)
        headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
        denied = client.post(f"/api/core/tasks/{task['id']}/assignment", headers=headers, json={"agent_id": foreign_agent.id})
        assert denied.status_code == 404
        rows = client.get(f"/api/core/agents?workspace_id={workspace.id}", headers=headers)
        assert rows.status_code == 200
        assert all(item["workspace_id"] == workspace.id for item in rows.json())
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
