from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    Base,
    ConstructiveEmployee,
    ConstructiveLedgerRow,
    ConstructiveObject,
    ConstructiveOrganization,
    ConstructiveRate,
    User,
)
from app.security import hash_password


def _fixture() -> tuple[Session, ConstructiveOrganization, ConstructiveEmployee, ConstructiveObject]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    actor = User(email="creator-asmet@example.local", name="Creator", password_hash=hash_password("secret"))
    db.add(actor)
    db.flush()
    organization = ConstructiveOrganization(name="Constructive", workspace_id="workspace-asmet")
    employee = ConstructiveEmployee(organization_id=organization.id, full_name="Иван Петров")
    obj = ConstructiveObject(organization_id=organization.id, name="Объект А", address="А")
    db.add(organization)
    db.flush()
    employee.organization_id = organization.id
    obj.organization_id = organization.id
    db.add_all([employee, obj])
    db.flush()
    db.add(ConstructiveRate(organization_id=organization.id, employee_id=employee.id, object_id=obj.id, work_type="Монтаж", amount=1000))
    db.commit()
    return db, organization, employee, obj


def test_max_message_is_idempotent_and_edit_replaces_rows_without_second_ack():
    from app.asmet_processing import process_max_message

    db, organization, _employee, _obj = _fixture()
    first = process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="7", text="Иван Петров / Объект А / Монтаж / 2")
    duplicate = process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="7", text="Иван Петров / Объект А / Монтаж / 2")
    edited = process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="7", text="Иван Петров / Объект А / Монтаж / 3", edited_at=datetime.utcnow())

    assert first.rows_inserted == 1
    assert first.acknowledgement_required is True
    assert duplicate.acknowledgement_required is False
    assert edited.rows_inserted == 1
    assert edited.acknowledgement_required is False
    rows = list(db.scalars(select(ConstructiveLedgerRow).where(ConstructiveLedgerRow.organization_id == organization.id)).all())
    assert len(rows) == 1
    assert rows[0].quantity == 3
    assert rows[0].amount == 3000


def test_history_processing_records_rejection_without_acknowledgement():
    from app.asmet_processing import process_max_message

    db, organization, _employee, _obj = _fixture()
    result = process_max_message(db, organization_id=organization.id, external_chat_id="max-work", external_message_id="8", text="непонятный текст", historical=True)

    assert result.rows_inserted == 0
    assert result.acknowledgement_required is False
    assert result.rejections[0]["reason"] == "FORMAT_NOT_RECOGNIZED"
    assert result.historical is True
    db.close()

