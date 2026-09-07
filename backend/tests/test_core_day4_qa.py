from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core_models import CoreAgent, CoreArtifact, CoreTask, CoreVerification
from app.db import get_db
from app.main import app
from app.security import create_access_token
from test_core_release1 import _db_and_owner
from test_core_day2 import _headers, _tree


def _qa_agent(db, workspace_id, user_id, key="qa-day4"):
    agent = CoreAgent(
        workspace_id=workspace_id,
        user_id=user_id,
        agent_key=key,
        name="QA Day 4",
        role="QA-инженер",
        description="Independent QA",
        competencies=["qa", "regression"],
        allowed_tools=[],
        allowed_actions=["execute_task"],
        limits={},
    )
    db.add(agent)
    db.commit()
    return agent


def _review_fixture(client, db, owner, workspace, agent_id=None):
    product, project, mission, sprint, task, _other = _tree(client, workspace.id, _headers(owner), prefix="QA4")
    if agent_id:
        assigned = client.post(f"/api/core/tasks/{task['id']}/assignment", headers=_headers(owner), json={"agent_id": agent_id})
        assert assigned.status_code == 201, assigned.text
    headers = _headers(owner)
    assert client.patch(f"/api/core/tasks/{task['id']}/status", headers=headers, json={"status": "PLANNED"}).status_code == 200
    assert client.patch(f"/api/core/tasks/{task['id']}/status", headers=headers, json={"status": "IN_PROGRESS"}).status_code == 200
    assert client.patch(f"/api/core/tasks/{task['id']}/status", headers=headers, json={"status": "IN_REVIEW", "result_summary": "Build and test result"}).status_code == 200
    artifact = client.post(f"/api/core/tasks/{task['id']}/artifacts", headers=headers, json={
        "artifact_key": "qa-result",
        "artifact_type": "TEST_REPORT",
        "name": "QA result",
        "uri": "file:///qa-result.json",
        "version": "1.0",
    })
    assert artifact.status_code == 201, artifact.text
    return task, artifact.json()


def test_qa_pass_requires_checklist_evidence_and_independent_agent():
    db, owner, qa_user, workspace = _db_and_owner()
    qa_agent = _qa_agent(db, workspace.id, qa_user.id)
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    try:
        task, artifact = _review_fixture(client, db, owner, workspace)
        request = client.post(f"/api/core/tasks/{task['id']}/qa", headers=_headers(owner), json={
            "qa_agent_id": qa_agent.id,
            "artifact_id": artifact["id"],
            "checked_artifact_version": "1.0",
            "idempotency_key": "qa-pass-1",
        })
        assert request.status_code == 201, request.text
        verification_id = request.json()["id"]
        incomplete = client.post(f"/api/core/qa/{verification_id}/complete", headers=_headers(qa_user), json={"status": "PASS"})
        assert incomplete.status_code == 422
        complete = client.post(f"/api/core/qa/{verification_id}/complete", headers=_headers(qa_user), json={
            "status": "PASS",
            "checklist": [{"name": "Regression", "passed": True}],
            "evidence": {"artifact_ids": [artifact["id"]], "url": "https://qa.local/result"},
            "comment": "Independent check passed",
        })
        assert complete.status_code == 200, complete.text
        assert complete.json()["status"] == "PASS"
        assert db.get(CoreTask, task["id"]).status == "ACCEPTED"
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_qa_agent_cannot_accept_own_task_and_terminal_reasons_are_required():
    db, owner, qa_user, workspace = _db_and_owner()
    qa_agent = _qa_agent(db, workspace.id, qa_user.id, key="qa-own")
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    try:
        task, artifact = _review_fixture(client, db, owner, workspace, qa_agent.id)
        request = client.post(f"/api/core/tasks/{task['id']}/qa", headers=_headers(owner), json={
            "qa_agent_id": qa_agent.id,
            "artifact_id": artifact["id"],
            "checked_artifact_version": "1.0",
            "idempotency_key": "qa-own-1",
        })
        assert request.status_code == 201, request.text
        own = client.post(f"/api/core/qa/{request.json()['id']}/complete", headers=_headers(qa_user), json={
            "status": "PASS",
            "checklist": [{"name": "Own result", "passed": True}],
            "evidence": {"url": "https://qa.local/own"},
        })
        assert own.status_code == 403

        blocked_request = client.post(f"/api/core/tasks/{task['id']}/qa", headers=_headers(owner), json={
            "qa_agent_id": qa_agent.id,
            "artifact_id": artifact["id"],
            "checked_artifact_version": "1.0",
            "idempotency_key": "qa-blocked-1",
        })
        assert blocked_request.status_code == 201
        blocked = client.post(f"/api/core/qa/{blocked_request.json()['id']}/complete", headers=_headers(owner), json={"status": "BLOCKED"})
        assert blocked.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_fail_creates_one_remediation_task_and_same_request_is_idempotent():
    db, owner, qa_user, workspace = _db_and_owner()
    qa_agent = _qa_agent(db, workspace.id, qa_user.id, key="qa-fail")
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    try:
        task, artifact = _review_fixture(client, db, owner, workspace)
        payload = {"qa_agent_id": qa_agent.id, "artifact_id": artifact["id"], "checked_artifact_version": "1.0", "idempotency_key": "qa-fail-1"}
        request = client.post(f"/api/core/tasks/{task['id']}/qa", headers=_headers(owner), json=payload)
        assert request.status_code == 201
        fail = client.post(f"/api/core/qa/{request.json()['id']}/complete", headers=_headers(qa_user), json={
            "status": "FAIL",
            "checklist": [{"name": "Smoke", "passed": False}],
            "evidence": {"url": "https://qa.local/failure"},
            "defect": "The acceptance path returns 500",
            "remediation_action": "Fix the acceptance path and rerun QA",
        })
        assert fail.status_code == 200, fail.text
        remediation_id = fail.json()["remediation_task_id"]
        assert remediation_id
        repeated = client.post(f"/api/core/tasks/{task['id']}/qa", headers=_headers(owner), json=payload)
        assert repeated.status_code == 200
        assert repeated.json()["id"] == request.json()["id"]
        count = db.scalar(select(func.count()).select_from(CoreTask).where(CoreTask.parent_task_id == task["id"]))
        assert count == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_production_evidence_requires_complete_packet():
    db, owner, _qa, workspace = _db_and_owner()
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    try:
        task, _artifact = _review_fixture(client, db, owner, workspace)
        missing = client.post(f"/api/core/tasks/{task['id']}/production-evidence", headers=_headers(owner), json={"result": "PASS"})
        assert missing.status_code == 422
        evidence = client.post(f"/api/core/tasks/{task['id']}/production-evidence", headers=_headers(owner), json={
            "public_url": "https://example.local/core",
            "build_id": "build-2026-09-06",
            "checked_at": "2026-09-06T12:00:00Z",
            "screenshot_uri": "file:///evidence/core.png",
            "logs_uri": "file:///evidence/core.log",
            "checklist": [{"name": "Direct URL", "passed": True}],
            "result": "PASS",
        })
        assert evidence.status_code == 201, evidence.text
        assert evidence.json()["artifact"]["artifact_type"] == "RELEASE"
        assert evidence.json()["result"] == "PASS"
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
