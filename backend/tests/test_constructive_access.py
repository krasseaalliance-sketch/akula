from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, User
from app.security import hash_password


def test_constructive_models_and_role_access_are_available():
    from app.constructive_access import visible_constructive_data
    from app.models import ConstructiveOrganization

    assert ConstructiveOrganization.__tablename__ == "constructive_organizations"
    assert callable(visible_constructive_data)


def test_visibility_is_scoped_by_constructive_role_and_period():
    from app.constructive_access import visible_constructive_data
    from app.models import (
        ConstructiveCabinet,
        ConstructiveEmployee,
        ConstructiveLedgerRow,
        ConstructiveObject,
        ConstructiveObjectAssignment,
        ConstructiveOrganization,
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        creator = User(email="creator@example.local", name="Creator", password_hash=hash_password("secret"))
        master = User(email="master@example.local", name="Master", password_hash=hash_password("secret"))
        worker = User(email="worker@example.local", name="Worker", password_hash=hash_password("secret"))
        db.add_all([creator, master, worker])
        db.flush()
        organization = ConstructiveOrganization(name="Constructive", workspace_id="workspace-1")
        db.add(organization)
        db.flush()
        object_one = ConstructiveObject(organization_id=organization.id, name="Object A", address="A")
        object_two = ConstructiveObject(organization_id=organization.id, name="Object B", address="B")
        db.add_all([object_one, object_two])
        db.flush()
        employee = ConstructiveEmployee(organization_id=organization.id, user_id=worker.id, full_name="Worker")
        db.add(employee)
        db.flush()
        db.add(ConstructiveObjectAssignment(organization_id=organization.id, object_id=object_one.id, user_id=master.id, role="MASTER"))
        db.add_all([
            ConstructiveCabinet(organization_id=organization.id, user_id=creator.id, role="CREATOR"),
            ConstructiveCabinet(organization_id=organization.id, user_id=master.id, role="MASTER"),
            ConstructiveCabinet(organization_id=organization.id, user_id=worker.id, role="WORKER"),
        ])
        now = datetime.utcnow()
        db.add(ConstructiveLedgerRow(
            organization_id=organization.id,
            object_id=object_one.id,
            employee_id=employee.id,
            work_date=now,
            work_type="Монтаж",
            quantity=2,
            rate=1000,
            amount=2000,
            raw_line="Worker / Object A / Монтаж / 2",
        ))
        db.commit()

        period_start = now - timedelta(days=1)
        period_end = now + timedelta(days=1)
        creator_data = visible_constructive_data(db, creator, organization.id, period_start, period_end)
        master_data = visible_constructive_data(db, master, organization.id, period_start, period_end)
        worker_data = visible_constructive_data(db, worker, organization.id, period_start, period_end)

        assert len(creator_data["objects"]) == 2
        assert [row["work_type"] for row in master_data["ledger"]] == ["Монтаж"]
        assert [row["work_type"] for row in worker_data["ledger"]] == ["Монтаж"]
