from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.asmet_processing import process_max_message
from app.asmet_queries import answer_asmet_question, persist_creator_history_report
from app.models import Base, ConstructiveAsmetMessage, ConstructiveCabinet, ConstructiveEmployee, ConstructiveObject, ConstructiveOrganization, ConstructiveRate, User
from app.security import hash_password


def _fixture() -> tuple[Session, User, ConstructiveOrganization]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    creator = User(email="creator-query@example.local", name="Creator", password_hash=hash_password("secret"))
    db.add(creator)
    db.flush()
    organization = ConstructiveOrganization(name="Constructive", workspace_id="workspace-query")
    db.add(organization)
    db.flush()
    db.add(ConstructiveCabinet(organization_id=organization.id, user_id=creator.id, role="CREATOR"))
    employee = ConstructiveEmployee(organization_id=organization.id, full_name="Иван Петров")
    obj = ConstructiveObject(organization_id=organization.id, name="Объект А", address="Красноярск")
    db.add_all([employee, obj])
    db.flush()
    db.add(ConstructiveRate(organization_id=organization.id, employee_id=employee.id, object_id=obj.id, work_type="Монтаж", amount=1000))
    db.commit()
    return db, creator, organization


def test_asmet_answer_uses_visible_ledger_data():
    db, creator, organization = _fixture()
    process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="9", text="Иван Петров / Объект А / Монтаж / 2")
    answer = answer_asmet_question(db, creator, organization.id, "Сколько начислено?")
    assert answer.recognized is True
    assert "1 строк" in answer.text
    assert "2 000 ₽" in answer.text


def test_history_report_is_private_and_has_exact_rejection_reason():
    db, creator, organization = _fixture()
    start = datetime.utcnow() - timedelta(minutes=1)
    process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="10", text="Иван Петров / Объект А / Монтаж / 2", historical=True)
    process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="11", text="непонятный текст", historical=True)
    report = persist_creator_history_report(db, creator, organization.id, start, datetime.utcnow() + timedelta(minutes=1))
    assert report["messages_processed"] == 2
    assert report["recognized_rows"] == 1
    assert report["rejections_by_reason"] == {"FORMAT_NOT_RECOGNIZED": 1}
    outbound = db.scalar(select(ConstructiveAsmetMessage).where(ConstructiveAsmetMessage.status == "REPORT"))
    assert outbound is not None
    assert outbound.external_chat_id == f"user:{creator.email}"
