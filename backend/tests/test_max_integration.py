from __future__ import annotations

import httpx
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import AuditEvent, Base, ConstructiveCabinet, ConstructiveOrganization, User
from app.security import create_access_token, hash_password


def test_max_client_validates_bot_and_sends_idempotent_chat_message() -> None:
    from app.max_integration import MaxBotClient

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "max-token-for-test"
        if request.method == "GET" and request.url.path == "/me":
            return httpx.Response(
                200,
                json={
                    "user_id": 246517714839,
                    "name": "ASmeT",
                    "username": "id246517714839_bot",
                    "is_bot": True,
                    "last_activity_time": 1737500130100,
                },
            )
        if request.method == "POST" and request.url.path == "/messages":
            assert request.url.params["chat_id"] == "42727888"
            assert json.loads(request.content) == {"text": "Принято"}
            return httpx.Response(200, json={"message": {"message_id": "max-message-1"}})
        return httpx.Response(404)

    client = MaxBotClient(
        "max-token-for-test",
        base_url="https://platform-api2.max.ru",
        transport=httpx.MockTransport(handler),
    )

    assert client.get_me()["is_bot"] is True
    assert client.send_message("42727888", "Принято", idempotency_key="ack:message-1") == "max-message-1"
    assert client.send_message("42727888", "Принято", idempotency_key="ack:message-1") == "max-message-1"
    assert len([item for item in requests if item.url.path == "/messages"]) == 1


def test_max_client_registers_https_webhook_with_secret_and_message_events() -> None:
    from app.max_integration import MaxBotClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/subscriptions"
        assert json.loads(request.content) == {
            "url": "https://human-interface.ru/api/constructive/asmet/max/webhook",
            "update_types": ["message_created", "message_edited", "bot_started"],
            "secret": "max-webhook-secret",
        }
        return httpx.Response(200, json={"success": True})

    client = MaxBotClient(
        "max-token-for-test",
        base_url="https://platform-api2.max.ru",
        transport=httpx.MockTransport(handler),
    )

    assert client.subscribe_webhook(
        "https://human-interface.ru/api/constructive/asmet/max/webhook",
        "max-webhook-secret",
    ) == {"success": True}


def test_max_update_extracts_message_created_payload_without_guessing_sender_text() -> None:
    from app.max_integration import parse_max_message_update

    parsed = parse_max_message_update(
        {
            "update_type": "message_created",
            "timestamp": 1737500130100,
            "chat_id": 42727888,
            "user": {"user_id": 1001, "name": "Worker"},
            "message": {
                "body": {"mid": "m-77", "text": "Иван / Объект А / Монтаж / 2"},
                "timestamp": 1737500130000,
            },
        }
    )

    assert parsed is not None
    assert parsed.chat_id == "42727888"
    assert parsed.message_id == "m-77"
    assert parsed.text == "Иван / Объект А / Монтаж / 2"
    assert parsed.sender_id == "1001"


def test_signed_max_webhook_processes_a_message_once_and_sends_acknowledgement(monkeypatch) -> None:
    from app import constructive_api

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    creator = User(email="max-webhook@example.local", name="Creator", password_hash=hash_password("secret"))
    db.add(creator)
    db.flush()
    organization = ConstructiveOrganization(name="Constructive", workspace_id="workspace-max")
    db.add(organization)
    db.flush()
    db.add(ConstructiveCabinet(organization_id=organization.id, user_id=creator.id, role="CREATOR"))
    db.commit()

    settings = SimpleNamespace(
        max_asmet_access_token="max-token-for-test",
        max_asmet_organization_id=organization.id,
        max_webhook_secret="max-webhook-secret",
        max_asmet_chat_id="42727888",
        max_api_base_url="https://platform-api2.max.ru",
    )
    monkeypatch.setattr(constructive_api, "get_settings", lambda: settings)

    acknowledgements: list[tuple[str, str]] = []

    class FakeMaxClient:
        def __init__(self, access_token: str, *, base_url: str) -> None:
            assert access_token == "max-token-for-test"
            assert base_url == "https://platform-api2.max.ru"

        def send_message(self, chat_id: str, text: str, *, idempotency_key: str) -> str:
            acknowledgements.append((chat_id, text))
            return "ack-1"

    monkeypatch.setattr(constructive_api, "MaxBotClient", FakeMaxClient)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {
            "Authorization": f"Bearer {create_access_token(creator.id)}",
            "X-Max-Bot-Api-Secret": "max-webhook-secret",
        }
        payload = {
            "update_type": "message_created",
            "timestamp": 1737500130100,
            "chat_id": "42727888",
            "message": {"body": {"mid": "m-1", "text": "неформатированный отчёт"}},
        }
        first = client.post("/api/constructive/asmet/max/webhook", headers=headers, json=payload)
        second = client.post("/api/constructive/asmet/max/webhook", headers=headers, json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["status"] == "REJECTED"
        assert second.json()["status"] == "DUPLICATE"
        assert acknowledgements == [("42727888", "Принято")]
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "constructive.max.webhook.received")) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_creator_can_connect_max_webhook_without_persisting_access_token(monkeypatch) -> None:
    from app import constructive_api

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    creator = User(email="max-connect@example.local", name="Creator", password_hash=hash_password("secret"))
    db.add(creator)
    db.flush()
    organization = ConstructiveOrganization(name="Constructive", workspace_id="workspace-connect")
    db.add(organization)
    db.flush()
    db.add(ConstructiveCabinet(organization_id=organization.id, user_id=creator.id, role="CREATOR"))
    db.commit()

    settings = SimpleNamespace(
        max_asmet_access_token="max-token-for-test",
        max_asmet_organization_id=organization.id,
        max_webhook_secret="max-webhook-secret",
        max_webhook_url="https://human-interface.ru/api/constructive/asmet/max/webhook",
        max_api_base_url="https://platform-api2.max.ru",
    )
    monkeypatch.setattr(constructive_api, "get_settings", lambda: settings)
    calls: list[str] = []

    class FakeMaxClient:
        def __init__(self, access_token: str, *, base_url: str) -> None:
            assert access_token == "max-token-for-test"
            assert base_url == "https://platform-api2.max.ru"

        def get_me(self) -> dict[str, object]:
            calls.append("me")
            return {"user_id": 246517714839, "username": "id246517714839_bot", "is_bot": True}

        def subscribe_webhook(self, url: str, secret: str) -> dict[str, object]:
            calls.append(f"subscribe:{url}:{secret}")
            return {"success": True}

    monkeypatch.setattr(constructive_api, "MaxBotClient", FakeMaxClient)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/constructive/asmet/max/connect",
            headers={"Authorization": f"Bearer {create_access_token(creator.id)}"},
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True
        assert calls == [
            "me",
            "subscribe:https://human-interface.ru/api/constructive/asmet/max/webhook:max-webhook-secret",
        ]
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "constructive.max.connected"))
        assert audit is not None
        assert "max-token-for-test" not in str(audit.after_state)
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
