from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from app.main import app
from app.db import get_db
from app.models import Base, ConstructiveCabinet, ConstructiveEmployee, ConstructiveObject, ConstructiveOrganization, ConstructiveRate, User
from app.security import create_access_token, hash_password


def test_asmet_query_and_creator_history_report_are_exposed_as_russian_api():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    creator = User(email="creator-api@example.local", name="Creator", password_hash=hash_password("secret"))
    db.add(creator)
    db.flush()
    organization = ConstructiveOrganization(name="Constructive", workspace_id="workspace-api")
    db.add(organization)
    db.flush()
    db.add(ConstructiveCabinet(organization_id=organization.id, user_id=creator.id, role="CREATOR"))
    employee = ConstructiveEmployee(organization_id=organization.id, full_name="Иван Петров")
    obj = ConstructiveObject(organization_id=organization.id, name="Объект А", address="Красноярск")
    db.add_all([employee, obj])
    db.flush()
    db.add(ConstructiveRate(organization_id=organization.id, employee_id=employee.id, object_id=obj.id, work_type="Монтаж", amount=1000))
    db.commit()

    from app.asmet_processing import process_max_message

    process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="12", text="Иван Петров / Объект А / Монтаж / 2", historical=True)
    creator_id = creator.id
    creator_email = creator.email
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {create_access_token(creator_id)}"}
        answer = client.post("/api/constructive/asmet/query", headers=headers, json={"organization_id": organization.id, "question": "Сколько начислено?"})
        assert answer.status_code == 200
        assert answer.json()["answer"] == "За выбранный период: 1 строк, объём 2, начислено 2 000 ₽."
        report = client.post("/api/constructive/asmet/history/report", headers=headers, json={"organization_id": organization.id, "period_start": (datetime.utcnow() - timedelta(minutes=1)).isoformat(), "period_end": (datetime.utcnow() + timedelta(minutes=1)).isoformat()})
        assert report.status_code == 200
        assert report.json()["private_recipient"] == creator_email
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
