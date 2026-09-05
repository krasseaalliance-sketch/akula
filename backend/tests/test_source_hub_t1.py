from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from app.hunter.source_hub.filters import TELEGRAM_RULESET_VITRINA_V1, FastIntentFilter
from app.hunter.source_hub.hub import SourceHub
from app.hunter.source_hub.models import SourceAccount, SourceEndpoint
from app.hunter.source_hub.security import OutboundOperationForbidden
from app.hunter.source_hub.shadow import TelegramShadowIngestor
from app.hunter.source_hub.t11 import effective_flags, inspect_session
from app.hunter.source_hub.telegram_auth import (
    TelegramAuthAdapter,
    TelegramAuthConfig,
    TelegramReadOnlyClient,
)


class FakeReadClient:
    async def health_check(self):
        return True

    async def get_dialogs(self):
        return []

    async def get_messages(self, dialog_external_id, limit, since=None):
        return []

    async def send_message(self, *args, **kwargs):
        return "should never be exposed"


def test_read_only_facade_blocks_write_and_audits() -> None:
    events = []
    client = TelegramReadOnlyClient(FakeReadClient(), audit_sink=events.append, account_id="a", endpoint_id="e")
    assert "send_message" not in dir(client)
    for action in ("send_message", "reply", "forward", "join", "invite", "reaction", "vote", "comment", "edit", "delete", "upload"):
        with pytest.raises(OutboundOperationForbidden):
            getattr(client, action)("e", "hello")
    assert events[0].result == "BLOCKED_OUTBOUND_OPERATION"


def test_source_hub_persists_cursor_account_endpoint_and_isolates_accounts(tmp_path) -> None:
    hub = SourceHub(tmp_path / "hub.json", tmp_path / "audit.jsonl")
    account_a = hub.add_account(SourceAccount(platform="TELEGRAM", account_alias="a", credential_ref="HUNTER_TELEGRAM_API_ID", session_ref="HUNTER_TELEGRAM_SESSION"))
    account_b = hub.add_account(SourceAccount(platform="VK", account_alias="b", credential_ref="VK_CREDENTIAL_REF"))
    endpoint_a = hub.add_endpoint(SourceEndpoint(source_account_id=account_a.id, external_id="100", username="known_channel"))
    endpoint_b = hub.add_endpoint(SourceEndpoint(source_account_id=account_b.id, platform="VK", external_id="vk-1", endpoint_type="PUBLIC_PAGE"))
    hub.test_read(endpoint_a.id)
    hub.enable_endpoint(endpoint_a.id)
    hub.record_metrics(endpoint_a.id, {"last_cursor": "100", "last_seen_message_id": "100", "new_messages": 2})
    hub.disable_endpoint(endpoint_b.id)
    restarted = SourceHub(tmp_path / "hub.json", tmp_path / "audit.jsonl")
    assert restarted.get_endpoint(endpoint_a.id).last_cursor == "100"
    assert restarted.get_endpoint(endpoint_a.id).enabled is True
    assert restarted.get_endpoint(endpoint_b.id).enabled is False
    assert restarted.mark_reauth_required(account_a.id).status == "AUTH_REQUIRED"
    assert restarted.mark_rate_limited(account_b.id).status == "RATE_LIMITED"
    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert all("HUNTER_TELEGRAM_API_ID" not in line or "credential_ref" not in line for line in audit_lines)


def test_auth_without_local_setup_returns_auth_setup_required(monkeypatch) -> None:
    for name in ("HUNTER_TELEGRAM_API_ID", "HUNTER_TELEGRAM_API_HASH", "HUNTER_TELEGRAM_SESSION"):
        monkeypatch.delenv(name, raising=False)
    adapter = TelegramAuthAdapter(TelegramAuthConfig())
    assert adapter.status()["status"] == "AUTH_SETUP_REQUIRED"
    assert asyncio.run(adapter.request_code("+70000000000"))["status"] == "AUTH_SETUP_REQUIRED"


def test_vitrina_fast_filter_is_explainable_and_extracts_fields() -> None:
    filter_ = FastIntentFilter(TELEGRAM_RULESET_VITRINA_V1)
    now = datetime.now(UTC)
    result = filter_.evaluate("Ищу исполнителя: нужен сайт-каталог для бизнеса до 50 000 ₽, Москва, до 20 августа", published_at=now - timedelta(hours=2), now=now)
    assert result.passed is True
    assert result.score > 40
    assert result.budget and result.budget["currency"] == "₽"
    assert "Москва" in result.geo
    assert result.deadline is not None
    seller = filter_.evaluate("Предлагаю услуги, сделаю сайт, портфолио", published_at=now, now=now)
    vacancy = filter_.evaluate("Вакансия разработчика в штат", published_at=now, now=now)
    assert seller.passed is False and seller.seller_language is True
    assert vacancy.passed is False and vacancy.vacancy_language is True


def test_shadow_dedupe_and_stage21_isolation() -> None:
    now = datetime.now(UTC)
    ingestor = TelegramShadowIngestor()
    result = ingestor.ingest("endpoint-1", [
        {"message_id": "1", "text": "Ищу разработчика сайта за 30 000 ₽", "published_at": now.isoformat(), "source_url": "https://t.me/x/1"},
        {"message_id": "2", "text": "Ищу разработчика сайта за 30 000 ₽", "published_at": now.isoformat(), "source_url": "https://t.me/x/2"},
        {"message_id": "3", "text": "Предлагаю услуги разработки", "published_at": now.isoformat()},
    ])
    assert result["candidate_count"] == 1
    assert result["write_operations"] == 0
    assert result["stage2_1_mutation"] is False
    assert result["production_alerts"] == 0


def test_t11_missing_source_hub_session_is_explicit(monkeypatch) -> None:
    for name in ("HUNTER_TELEGRAM_API_ID", "HUNTER_TELEGRAM_API_HASH", "HUNTER_TELEGRAM_SESSION"):
        monkeypatch.delenv(name, raising=False)
    inspection = inspect_session()
    assert inspection.status == "MISSING"
    assert inspection.reason == "SECRET_REFS_MISSING"
    assert all(value is False for value in inspection.refs_present.values())


def test_t11_safe_flags_default_true_and_can_fail_closed(monkeypatch) -> None:
    for name in ("HUNTER_TELEGRAM_READ_ONLY", "HUNTER_TELEGRAM_SEND_DISABLED", "HUNTER_SOURCE_HUB_SHADOW_MODE"):
        monkeypatch.delenv(name, raising=False)
    assert all(effective_flags().values())
    monkeypatch.setenv("HUNTER_TELEGRAM_READ_ONLY", "false")
    assert effective_flags()["HUNTER_TELEGRAM_READ_ONLY"] is False
