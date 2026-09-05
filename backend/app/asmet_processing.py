from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import (
    ConstructiveAsmetMessage,
    ConstructiveEmployee,
    ConstructiveLedgerRow,
    ConstructiveObject,
    ConstructiveOrganization,
    ConstructiveRate,
)
from .services import normalize_text


@dataclass(frozen=True)
class ParsedWorkRow:
    employee_id: str
    object_id: str
    work_type: str
    quantity: float
    rate: float
    raw_line: str


@dataclass(frozen=True)
class ParsedWorkReport:
    rows: list[ParsedWorkRow] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AsmetProcessingResult:
    message_id: str
    status: str
    rows_inserted: int
    acknowledgement_required: bool
    historical: bool
    rejections: list[dict[str, Any]]


def _same(value: str) -> str:
    return normalize_text(value).casefold()


def _number(value: str) -> float | None:
    cleaned = value.replace(" ", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def parse_work_report(
    text: str,
    employees: list[ConstructiveEmployee],
    objects: list[ConstructiveObject],
    rates: list[ConstructiveRate],
) -> ParsedWorkReport:
    employee_by_name = {_same(item.full_name): item for item in employees}
    object_by_name = {_same(item.name): item for item in objects}
    rate_by_key = {(
        item.employee_id,
        item.object_id,
        _same(item.work_type),
    ): item.amount for item in rates}
    fallback_rates = {(
        item.employee_id,
        _same(item.work_type),
    ): item.amount for item in rates if item.object_id is None}
    rows: list[ParsedWorkRow] = []
    rejections: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        parts = [part.strip() for part in re.split(r"\s*(?:\||/|;)\s*", raw_line) if part.strip()]
        if len(parts) < 4:
            rejections.append({"line": line_number, "raw": raw_line, "reason": "FORMAT_NOT_RECOGNIZED"})
            continue
        employee = employee_by_name.get(_same(parts[0]))
        if employee is None:
            rejections.append({"line": line_number, "raw": raw_line, "reason": "WORKER_NOT_FOUND"})
            continue
        obj = object_by_name.get(_same(parts[1]))
        if obj is None:
            rejections.append({"line": line_number, "raw": raw_line, "reason": "OBJECT_NOT_FOUND"})
            continue
        quantity = _number(parts[3])
        if quantity is None or quantity <= 0:
            rejections.append({"line": line_number, "raw": raw_line, "reason": "QUANTITY_NOT_RECOGNIZED"})
            continue
        work_type = normalize_text(parts[2])
        explicit_rate = _number(parts[4]) if len(parts) > 4 else None
        rate = explicit_rate
        if rate is None:
            rate = rate_by_key.get((employee.id, obj.id, _same(work_type)))
        if rate is None:
            rate = fallback_rates.get((employee.id, _same(work_type)))
        if rate is None:
            rejections.append({"line": line_number, "raw": raw_line, "reason": "RATE_NOT_FOUND"})
            continue
        rows.append(ParsedWorkRow(employee.id, obj.id, work_type, quantity, rate, raw_line))
    return ParsedWorkReport(rows, rejections)


def process_max_message(
    db: Session,
    *,
    organization_id: str,
    external_chat_id: str,
    external_message_id: str,
    text: str,
    sent_at: datetime | None = None,
    edited_at: datetime | None = None,
    historical: bool = False,
    profile: Any | None = None,
) -> AsmetProcessingResult:
    organization = db.get(ConstructiveOrganization, organization_id)
    if organization is None:
        raise LookupError("constructive organization not found")
    message = db.scalar(select(ConstructiveAsmetMessage).where(
        ConstructiveAsmetMessage.organization_id == organization_id,
        ConstructiveAsmetMessage.external_chat_id == external_chat_id,
        ConstructiveAsmetMessage.external_message_id == external_message_id,
    ))
    source_id = f"{external_chat_id}:{external_message_id}"
    if message is not None and message.text == text and message.edited_at == edited_at and (sent_at is None or message.sent_at == sent_at):
        retry_ack = profile is not None and not message.historical and not message.acknowledgement_sent
        if retry_ack:
            from .telegram_engine.engine import TelegramEngineService

            acknowledgement_id = TelegramEngineService().send_operator_notification(
                profile=profile,
                content="Принято",
                target=external_chat_id,
            )
            if acknowledgement_id:
                message.acknowledgement_sent = True
                db.commit()
        return AsmetProcessingResult(message.id, "DUPLICATE", 0, retry_ack, message.historical, message.rejections or [])
    was_seen = message is not None
    if message is None:
        message = ConstructiveAsmetMessage(
            organization_id=organization_id,
            external_chat_id=external_chat_id,
            external_message_id=external_message_id,
            text=text,
            sent_at=sent_at,
            edited_at=edited_at,
            historical=historical,
        )
        db.add(message)
        db.flush()
    else:
        message.text = text
        message.sent_at = sent_at or message.sent_at
        message.edited_at = edited_at
        message.historical = message.historical or historical

    db.execute(delete(ConstructiveLedgerRow).where(
        ConstructiveLedgerRow.organization_id == organization_id,
        ConstructiveLedgerRow.source_message_id == source_id,
    ))
    employees = list(db.scalars(select(ConstructiveEmployee).where(ConstructiveEmployee.organization_id == organization_id, ConstructiveEmployee.status == "ACTIVE")).all())
    objects = list(db.scalars(select(ConstructiveObject).where(ConstructiveObject.organization_id == organization_id, ConstructiveObject.status == "ACTIVE")).all())
    rates = list(db.scalars(select(ConstructiveRate).where(ConstructiveRate.organization_id == organization_id)).all())
    parsed = parse_work_report(text, employees, objects, rates)
    work_date = message.sent_at or edited_at or datetime.utcnow()
    for parsed_row in parsed.rows:
        db.add(ConstructiveLedgerRow(
            organization_id=organization_id,
            source_message_id=source_id,
            object_id=parsed_row.object_id,
            employee_id=parsed_row.employee_id,
            work_date=work_date,
            work_type=parsed_row.work_type,
            quantity=parsed_row.quantity,
            rate=parsed_row.rate,
            amount=parsed_row.quantity * parsed_row.rate,
            raw_line=parsed_row.raw_line,
        ))
    message.processed_at = datetime.utcnow()
    message.status = "PROCESSED" if parsed.rows else "REJECTED"
    message.rejections = parsed.rejections or None
    acknowledgement_required = not historical and not was_seen
    message.acknowledgement_sent = False
    db.commit()
    if profile is not None and acknowledgement_required:
        from .telegram_engine.engine import TelegramEngineService

        acknowledgement_id = TelegramEngineService().send_operator_notification(
            profile=profile,
            content="Принято",
            target=external_chat_id,
        )
        if acknowledgement_id:
            message.acknowledgement_sent = True
            db.commit()
    return AsmetProcessingResult(message.id, message.status, len(parsed.rows), acknowledgement_required, message.historical, parsed.rejections)
