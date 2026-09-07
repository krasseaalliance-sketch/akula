from fastapi.testclient import TestClient

from app import core_services
from app.db import get_db
from app.main import app
from test_core_day2 import _headers, _tree
from test_core_release1 import _db_and_owner


def test_file_and_image_uploads_are_stored_and_viewable(tmp_path):
    db, owner, _qa, workspace = _db_and_owner()
    original_root = core_services.ARTIFACT_STORAGE_ROOT
    core_services.ARTIFACT_STORAGE_ROOT = tmp_path
    app.dependency_overrides[get_db] = lambda: (yield from (item for item in [db]))
    client = TestClient(app)
    headers = _headers(owner)
    try:
        _product, _project, _mission, _sprint, task, _other = _tree(client, workspace.id, headers, prefix="D5U")
        cases = [
            ("FILE", "evidence.txt", "text/plain", b"real file evidence"),
            ("IMAGE", "evidence.png", "image/png", b"real image evidence"),
        ]
        for artifact_type, filename, content_type, content in cases:
            response = client.post(
                f"/api/core/tasks/{task['id']}/artifacts/upload",
                headers={**headers, "content-type": content_type, "x-file-name": filename},
                params={"artifact_type": artifact_type, "name": filename, "version": "1.0"},
                content=content,
            )
            assert response.status_code == 201, response.text
            artifact = response.json()
            assert artifact["artifact_type"] == artifact_type
            assert artifact["uri"].endswith(f"/api/core/artifacts/{artifact['id']}/content")
            viewed = client.get(f"/api/core/artifacts/{artifact['id']}/content", headers=headers)
            assert viewed.status_code == 200
            assert viewed.content == content
            assert viewed.headers["content-type"].startswith(content_type)
    finally:
        core_services.ARTIFACT_STORAGE_ROOT = original_root
        app.dependency_overrides.pop(get_db, None)
        db.close()
