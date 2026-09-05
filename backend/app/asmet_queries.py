from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .constructive_access import constructive_role, visible_constructive_data
from .models import ConstructiveAsmetMessage, ConstructiveLedgerRow, User


@dataclass(frozen=True)
class AsmetAnswer:
    text: str
    role: str
    organization_id: str
    recognized: bool


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".00", "") + " ₽"


def _contains(question: str, *terms: str) -> bool:
    return any(term in question for term in terms)


def answer_asmet_question(
    db: Session,
    user: User,
    organization_id: str,
    question: str,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> AsmetAnswer:
    role = constructive_role(db, user.id, organization_id)
    if role is None:
        raise PermissionError("constructive.asmet.query")
    data = visible_constructive_data(db, user, organization_id, period_start, period_end)
    normalized = question.strip().casefold()
    rows = data["ledger"]
    if _contains(normalized, "сколько", "итого", "сумм", "начисл", "заработ"):
        quantity = sum(float(row["quantity"]) for row in rows)
        amount = sum(float(row["amount"]) for row in rows)
        return AsmetAnswer(
            f"За выбранный период: {len(rows)} строк, объём {quantity:g}, начислено {_money(amount)}.",
            role,
            organization_id,
            True,
        )
    if _contains(normalized, "ставк", "расцен", "тариф"):
        rates = data["rates"]
        if not rates:
            text = "В доступной области данных расценки не заведены."
        else:
            items = "; ".join(f"{rate['work_type']} — {_money(float(rate['amount']))}" for rate in rates)
            text = f"Доступные расценки: {items}."
        return AsmetAnswer(text, role, organization_id, True)
    if _contains(normalized, "объект", "адрес"):
        objects = data["objects"]
        if not objects:
            text = "В вашей области доступа объектов нет."
        else:
            items = "; ".join(f"{item['name']}" + (f" ({item['address']})" if item["address"] else "") for item in objects)
            text = f"Доступные объекты: {items}."
        return AsmetAnswer(text, role, organization_id, True)
    if _contains(normalized, "сотруд", "работник", "брига", "мастер"):
        employees = data["employees"]
        names = ", ".join(item["full_name"] for item in employees) or "нет данных"
        return AsmetAnswer(f"В вашей области доступа сотрудники: {names}.", role, organization_id, True)
    if _contains(normalized, "склад"):
        warehouses = data["warehouses"]
        names = ", ".join(item["name"] for item in warehouses) or "нет данных"
        return AsmetAnswer(f"Доступные склады: {names}.", role, organization_id, True)
    return AsmetAnswer(
        "Запрос не распознан. Уточните: объём и сумму, расценки, объекты, сотрудников или склады.",
        role,
        organization_id,
        False,
    )


def _message_dict(message: ConstructiveAsmetMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "external_chat_id": message.external_chat_id,
        "external_message_id": message.external_message_id,
        "text": message.text,
        "status": message.status,
        "historical": message.historical,
        "rejections": message.rejections or [],
        "created_at": message.created_at.isoformat(),
        "processed_at": message.processed_at.isoformat() if message.processed_at else None,
    }


def visible_asmet_messages(db: Session, user: User, organization_id: str) -> list[dict[str, Any]]:
    role = constructive_role(db, user.id, organization_id)
    if role is None:
        raise PermissionError("constructive.asmet.history")
    messages = list(db.scalars(select(ConstructiveAsmetMessage).where(
        ConstructiveAsmetMessage.organization_id == organization_id,
    ).order_by(ConstructiveAsmetMessage.created_at.asc())).all())
    if role == "CREATOR":
        return [_message_dict(message) for message in messages]
    data = visible_constructive_data(db, user, organization_id)
    visible_sources = {row["source_message_id"] for row in data["ledger"]}
    own_address = f"user:{user.email.lower()}"
    return [
        _message_dict(message)
        for message in messages
        if message.external_chat_id == own_address or f"{message.external_chat_id}:{message.external_message_id}" in visible_sources
    ]


def creator_history_report(
    db: Session,
    creator: User,
    organization_id: str,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, Any]:
    if constructive_role(db, creator.id, organization_id) != "CREATOR":
        raise PermissionError("constructive.asmet.history_report")
    messages = list(db.scalars(select(ConstructiveAsmetMessage).where(
        ConstructiveAsmetMessage.organization_id == organization_id,
        ConstructiveAsmetMessage.created_at >= period_start,
        ConstructiveAsmetMessage.created_at <= period_end,
        ConstructiveAsmetMessage.historical.is_(True),
    ).order_by(ConstructiveAsmetMessage.created_at.asc())).all())
    source_ids = {f"{message.external_chat_id}:{message.external_message_id}" for message in messages}
    rows = list(db.scalars(select(ConstructiveLedgerRow).where(
        ConstructiveLedgerRow.organization_id == organization_id,
        ConstructiveLedgerRow.source_message_id.in_(source_ids) if source_ids else False,
    )).all())
    rejection_counts: dict[str, int] = {}
    rejected_messages: list[dict[str, Any]] = []
    for message in messages:
        for rejection in message.rejections or []:
            reason = str(rejection.get("reason", "UNKNOWN"))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            rejected_messages.append({"message_id": message.external_message_id, **rejection})
    return {
        "period": {"from": period_start.isoformat(), "to": period_end.isoformat()},
        "messages_processed": len(messages),
        "recognized_rows": len(rows),
        "rejected_messages": len({message.id for message in messages if message.status == "REJECTED"}),
        "rejections_by_reason": rejection_counts,
        "rejections": rejected_messages,
    }


def persist_creator_history_report(
    db: Session,
    creator: User,
    organization_id: str,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, Any]:
    report = creator_history_report(db, creator, organization_id, period_start, period_end)
    message_key = f"history-report:{period_start.isoformat()}:{period_end.isoformat()}"
    existing = db.scalar(select(ConstructiveAsmetMessage).where(
        ConstructiveAsmetMessage.organization_id == organization_id,
        ConstructiveAsmetMessage.external_chat_id == f"user:{creator.email.lower()}",
        ConstructiveAsmetMessage.external_message_id == message_key,
    ))
    text = (
        f"Отчёт ASmeT за {period_start:%d.%m.%Y}–{period_end:%d.%m.%Y}: "
        f"обработано сообщений — {report['messages_processed']}; "
        f"распознано строк — {report['recognized_rows']}; "
        f"отклонено сообщений — {report['rejected_messages']}. "
        f"Причины: {report['rejections_by_reason'] or 'нет'}."
    )
    if existing is None:
        db.add(ConstructiveAsmetMessage(
            organization_id=organization_id,
            external_chat_id=f"user:{creator.email.lower()}",
            external_message_id=message_key,
            text=text,
            processed_at=datetime.utcnow(),
            historical=True,
            status="REPORT",
        ))
        db.commit()
    report["private_recipient"] = creator.email
    report["report_text"] = text
    return report
