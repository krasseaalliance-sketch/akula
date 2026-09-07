from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core_models import CoreArtifact, CoreTask
from app.db import get_db
from app.main import app
from app.models import Workspace, WorkspaceMember
from app.security import create_access_token
from test_core_release1 import _db_and_owner
from test_core_day2 import _headers, _tree


def test_artifacts_are_typed_versioned_audited_and_soft_deleted():
    db, owner, _qa, workspace = _db_and_owner()
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    headers = _headers(owner)
    try:
        _product, project, _mission, _sprint, task, _other = _tree(client, workspace.id, headers, prefix="D4")
        first = client.post(f"/api/core/tasks/{task['id']}/artifacts", headers=headers, json={
            "artifact_key": "release-notes",
            "artifact_type": "DOCUMENT",
            "name": "Release notes",
            "uri": "file:///workspace/release-notes.md",
            "version": "1.0",
        })
        assert first.status_code == 201, first.text
        first_body = first.json()
        assert first_body["status"] == "DRAFT"
        assert first_body["artifact_key"] == "release-notes"

        submitted = client.patch(f"/api/core/artifacts/{first_body['id']}", headers=headers, json={"status": "SUBMITTED"})
        assert submitted.status_code == 200, submitted.text
        approved = client.patch(f"/api/core/artifacts/{first_body['id']}", headers=headers, json={"status": "APPROVED"})
        assert approved.status_code == 200, approved.text

        second = client.post(f"/api/core/artifacts/{first_body['id']}/versions", headers=headers, json={
            "artifact_type": "DOCUMENT",
            "name": "Release notes",
            "uri": "file:///workspace/release-notes-v2.md",
            "version": "2.0",
        })
        assert second.status_code == 201, second.text
        assert second.json()["artifact_key"] == "release-notes"
        assert second.json()["version"] == "2.0"
        rows = client.get(f"/api/core/tasks/{task['id']}/artifacts", headers=headers)
        assert rows.status_code == 200
        assert {row["version"] for row in rows.json()} == {"1.0", "2.0"}
        assert next(row for row in rows.json() if row["version"] == "1.0")["status"] == "SUPERSEDED"

        deleted = client.delete(f"/api/core/artifacts/{first_body['id']}", headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert db.get(CoreArtifact, first_body["id"]) is not None
        assert db.get(CoreArtifact, first_body["id"]).status == "SUPERSEDED"
        events = client.get(f"/api/core/events?workspace_id={workspace.id}", headers=headers).json()
        assert any(item["action"] == "artifact.version_created" for item in events)
        assert any(item["action"] == "artifact.deleted" for item in events)
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_artifact_ids_are_workspace_scoped_and_cannot_be_guessed():
    db, owner, _qa, workspace = _db_and_owner()
    foreign_owner = owner.__class__(email="foreign@example.local", name="Foreign", password_hash=owner.password_hash)
    db.add(foreign_owner)
    db.flush()
    foreign_workspace = Workspace(name="Foreign", slug="foreign", owner_id=foreign_owner.id)
    db.add(foreign_workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=foreign_workspace.id, user_id=foreign_owner.id, role="OWNER", status="ACTIVE"))
    foreign_task = CoreTask(
        workspace_id=foreign_workspace.id,
        project_id="foreign-project",
        sprint_id="foreign-sprint",
        title="Foreign task",
        description="Foreign",
        acceptance_criteria=[],
        required_competencies=[],
        priority=3,
        created_by=foreign_owner.id,
    )
    db.add(foreign_task)
    db.flush()
    artifact = CoreArtifact(
        workspace_id=foreign_workspace.id,
        task_id=foreign_task.id,
        artifact_key="foreign-artifact",
        artifact_type="DOCUMENT",
        name="Foreign artifact",
        uri="file:///foreign",
        version="1",
        created_by=foreign_owner.id,
    )
    db.add(artifact)
    db.commit()
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    try:
        response = client.get(f"/api/core/artifacts/{artifact.id}", headers=_headers(owner))
        assert response.status_code == 404
        response = client.get(f"/api/core/tasks/{foreign_task.id}/artifacts", headers=_headers(owner))
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
