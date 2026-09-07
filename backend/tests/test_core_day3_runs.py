from fastapi.testclient import TestClient

from app.core_models import CoreAgent
from app.db import get_db
from app.main import app
from app.security import create_access_token
from test_core_day3_agents import _client_with_db, _task


def test_manual_run_lifecycle_keeps_context_and_never_accepts_task():
    db, owner, _qa, workspace, client = _client_with_db()
    try:
        agent = CoreAgent(workspace_id=workspace.id, agent_key="developer", name="Developer", role="Разработчик", description="Code", competencies=["code"], allowed_tools=[], limits={"max_parallel_tasks": 1}, allowed_actions=["execute_task"], concurrency_limit=1, available=True)
        db.add(agent); db.commit()
        task = _task(client, owner, workspace)
        headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
        assert client.post(f"/api/core/tasks/{task['id']}/assignment", headers=headers, json={"agent_id": agent.id}).status_code == 201
        route = client.post(f"/api/core/tasks/{task['id']}/route", headers=headers)
        assert route.status_code == 200
        assert route.json()["next_step"] == 1
        body = {"goal": "Implement the change", "constraints": ["No outbound actions"], "input_artifact_ids": [], "decision_ids": [], "acceptance_criteria": ["Independent QA"]}
        queued = client.post(f"/api/core/tasks/{task['id']}/runs", headers=headers, json=body)
        assert queued.status_code == 201, queued.text
        run_id = queued.json()["id"]
        assert queued.json()["status"] == "QUEUED"
        assert client.post(f"/api/core/runs/{run_id}/transition", headers=headers, json={"status": "RUNNING"}).status_code == 200
        succeeded = client.post(f"/api/core/runs/{run_id}/transition", headers=headers, json={"status": "SUCCEEDED", "result_summary": "Implemented"})
        assert succeeded.status_code == 200
        assert succeeded.json()["context"]["goal"] == body["goal"]
        assert client.get(f"/api/core/tasks/{task['id']}", headers=headers).json()["task"]["status"] != "ACCEPTED"
        events = client.get(f"/api/core/events?workspace_id={workspace.id}", headers=headers).json()
        assert any(event["action"] == "run.succeeded" for event in events)
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_runs_reject_blockers_conflicts_invalid_transitions_and_audit_cancel():
    db, owner, _qa, workspace, client = _client_with_db()
    try:
        agent = CoreAgent(workspace_id=workspace.id, agent_key="developer", name="Developer", role="Разработчик", description="Code", competencies=["code"], allowed_tools=[], limits={"max_parallel_tasks": 1}, allowed_actions=["execute_task"], concurrency_limit=1, available=True)
        db.add(agent); db.commit()
        predecessor = _task(client, owner, workspace)
        headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
        dependent = client.post(f"/api/core/projects/{predecessor['project_id']}/sprints/{predecessor['sprint_id']}/tasks", headers=headers, json={"title": "Dependent task", "description": "Task for agent", "required_competencies": ["code"]}).json()
        for task in (predecessor, dependent):
            assert client.post(f"/api/core/tasks/{task['id']}/assignment", headers=headers, json={"agent_id": agent.id}).status_code == 201
        assert client.post(f"/api/core/tasks/{dependent['id']}/dependencies", headers=headers, json={"predecessor_task_id": predecessor["id"]}).status_code == 201
        blocked = client.post(f"/api/core/tasks/{dependent['id']}/runs", headers=headers, json={"goal": "blocked", "acceptance_criteria": []})
        assert blocked.status_code == 409
        free = _task(client, owner, workspace)
        assert client.post(f"/api/core/tasks/{free['id']}/assignment", headers=headers, json={"agent_id": agent.id}).status_code == 201
        active = client.post(f"/api/core/tasks/{predecessor['id']}/runs", headers=headers, json={"goal": "active", "acceptance_criteria": []})
        assert active.status_code == 201
        assert client.post(f"/api/core/tasks/{free['id']}/runs", headers=headers, json={"goal": "conflict", "acceptance_criteria": []}).status_code == 409
        # A separate available agent permits the cancellation transition test.
        second = CoreAgent(workspace_id=workspace.id, agent_key="architect", name="Architect", role="Архитектор", description="Contracts", competencies=["code"], allowed_tools=[], limits={}, allowed_actions=["execute_task"], concurrency_limit=1, available=True)
        db.add(second); db.commit()
        assert client.post(f"/api/core/tasks/{free['id']}/assignment", headers=headers, json={"agent_id": second.id}).status_code == 201
        queued = client.post(f"/api/core/tasks/{free['id']}/runs", headers=headers, json={"goal": "cancel", "acceptance_criteria": []})
        assert queued.status_code == 201
        run_id = queued.json()["id"]
        assert client.post(f"/api/core/runs/{run_id}/transition", headers=headers, json={"status": "SUCCEEDED", "result_summary": "skip"}).status_code == 409
        cancelled = client.post(f"/api/core/runs/{run_id}/transition", headers=headers, json={"status": "CANCELLED", "error_reason": "Creator stopped the run"})
        assert cancelled.status_code == 200
        assert cancelled.json()["error_reason"] == "Creator stopped the run"
        failed_run = client.post(f"/api/core/tasks/{free['id']}/runs", headers=headers, json={"goal": "fail", "acceptance_criteria": []})
        assert failed_run.status_code == 201
        failed_id = failed_run.json()["id"]
        assert client.post(f"/api/core/runs/{failed_id}/transition", headers=headers, json={"status": "RUNNING"}).status_code == 200
        assert client.post(f"/api/core/runs/{failed_id}/transition", headers=headers, json={"status": "FAILED", "error_reason": "Agent error"}).status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
