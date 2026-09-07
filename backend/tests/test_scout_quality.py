from __future__ import annotations

from datetime import UTC, datetime

from app.hunter.intent import RulesIntentProvider
from app.hunter.models import RawSignal
from app.hunter.normalization import normalize_signal
from app.hunter.qualification import qualify_signal


def _qualified(text: str):
    signal = RawSignal(
        id="telegram-fixture", source="telegram:@fixture", source_url="https://example.test/message/1",
        external_id="1", author_identifier="public_channel:fixture",
        published_at=datetime(2026, 8, 11, tzinfo=UTC), detected_at=datetime(2026, 8, 11, 0, 1, tzinfo=UTC),
        title="Public message", text=text, metadata={"source_scope": "PUBLIC_CHANNEL_PREVIEW"},
    )
    normalized = normalize_signal(signal)
    intent = RulesIntentProvider().analyze(normalized)
    return qualify_signal(normalized, intent)


def test_telegram_digest_is_not_a_lead_under_current_qualification_contract() -> None:
    digest = "digest: за последние сутки найдено 25 проектов на сумму 0 руб."

    assert _qualified(digest).decision == "REJECTED"


def test_concrete_telegram_request_is_kept_under_current_qualification_contract() -> None:
    request = "Нужен исполнитель: сделать лендинг для мебельной компании, бюджет обсуждается"

    assert _qualified(request).decision == "QUALIFIED"
