from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    ConstructiveCabinet,
    ConstructiveEmployee,
    ConstructiveLedgerRow,
    ConstructiveObject,
    ConstructiveObjectAssignment,
    ConstructiveOrganization,
    ConstructiveRate,
    ConstructiveWarehouse,
    User,
)


def constructive_role(db: Session, user_id: str, organization_id: str) -> str | None:
    return db.scalar(
        select(ConstructiveCabinet.role).where(
            ConstructiveCabinet.organization_id == organization_id,
            ConstructiveCabinet.user_id == user_id,
            ConstructiveCabinet.status == "ACTIVE",
        )
    )


def _object_ids(db: Session, user: User, organization_id: str, role: str) -> set[str] | None:
    if role == "CREATOR":
        return None
    assignment_roles = {"MASTER"} if role == "MASTER" else {"BRIGADIER", "WORKER"}
    return set(
        db.scalars(
            select(ConstructiveObjectAssignment.object_id).where(
                ConstructiveObjectAssignment.organization_id == organization_id,
                ConstructiveObjectAssignment.user_id == user.id,
                ConstructiveObjectAssignment.role.in_(assignment_roles),
                ConstructiveObjectAssignment.status == "ACTIVE",
            )
        ).all()
    )


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "source_message_id": row.source_message_id,
        "object_id": row.object_id,
        "employee_id": row.employee_id,
        "work_date": row.work_date.isoformat(),
        "work_type": row.work_type,
        "quantity": row.quantity,
        "rate": row.rate,
        "amount": row.amount,
        "raw_line": row.raw_line,
        "status": row.status,
    }


def visible_constructive_data(
    db: Session,
    user: User,
    organization_id: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    role = constructive_role(db, user.id, organization_id)
    if role is None:
        raise PermissionError("constructive.cabinet.view")
    organization = db.get(ConstructiveOrganization, organization_id)
    if organization is None:
        raise LookupError("constructive organization not found")

    object_ids = _object_ids(db, user, organization_id, role)
    row_query = select(ConstructiveLedgerRow).where(ConstructiveLedgerRow.organization_id == organization_id)
    if object_ids is not None and role != "WORKER":
        if not object_ids:
            row_query = row_query.where(False)
        else:
            row_query = row_query.where(ConstructiveLedgerRow.object_id.in_(object_ids))
    if role == "WORKER":
        employee_ids = set(
            db.scalars(
                select(ConstructiveEmployee.id).where(
                    ConstructiveEmployee.organization_id == organization_id,
                    ConstructiveEmployee.user_id == user.id,
                )
            ).all()
        )
        row_query = row_query.where(ConstructiveLedgerRow.employee_id.in_(employee_ids)) if employee_ids else row_query.where(False)
    if period_start is not None:
        row_query = row_query.where(ConstructiveLedgerRow.work_date >= period_start)
    if period_end is not None:
        row_query = row_query.where(ConstructiveLedgerRow.work_date <= period_end)
    rows = list(db.scalars(row_query.order_by(ConstructiveLedgerRow.work_date.desc())).all())
    visible_row_employee_ids = {row.employee_id for row in rows}

    objects_query = select(ConstructiveObject).where(ConstructiveObject.organization_id == organization_id)
    if object_ids is not None:
        objects_query = objects_query.where(ConstructiveObject.id.in_(object_ids)) if object_ids else objects_query.where(False)
    objects = list(db.scalars(objects_query.order_by(ConstructiveObject.name)).all())

    employee_query = select(ConstructiveEmployee).where(ConstructiveEmployee.organization_id == organization_id)
    if role == "WORKER":
        employee_query = employee_query.where(ConstructiveEmployee.user_id == user.id)
    elif role != "CREATOR":
        employee_query = employee_query.where(ConstructiveEmployee.id.in_(visible_row_employee_ids)) if visible_row_employee_ids else employee_query.where(False)
    employees = list(db.scalars(employee_query.order_by(ConstructiveEmployee.full_name)).all())

    rate_query = select(ConstructiveRate).where(ConstructiveRate.organization_id == organization_id)
    if object_ids is not None:
        rate_query = rate_query.where(or_(ConstructiveRate.object_id.is_(None), ConstructiveRate.object_id.in_(object_ids))) if object_ids else rate_query.where(ConstructiveRate.object_id.is_(None))
    rates = list(db.scalars(rate_query.order_by(ConstructiveRate.work_type)).all())
    warehouses = list(db.scalars(select(ConstructiveWarehouse).where(ConstructiveWarehouse.organization_id == organization_id).order_by(ConstructiveWarehouse.name)).all())

    return {
        "organization": [{"id": organization.id, "workspace_id": organization.workspace_id, "name": organization.name, "role": role}],
        "objects": [{"id": item.id, "name": item.name, "address": item.address, "status": item.status} for item in objects],
        "employees": [{"id": item.id, "user_id": item.user_id, "full_name": item.full_name, "telegram_username": item.telegram_username, "role": item.role} for item in employees],
        "warehouses": [{"id": item.id, "name": item.name, "address": item.address, "status": item.status} for item in warehouses],
        "rates": [{"id": item.id, "employee_id": item.employee_id, "object_id": item.object_id, "work_type": item.work_type, "amount": item.amount, "currency": item.currency} for item in rates],
        "ledger": [_row_dict(row) for row in rows],
    }
