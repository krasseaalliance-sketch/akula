from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.hunter.freshness import classify_freshness
from app.hunter.intent import RulesIntentProvider
from app.hunter.models import RawSignal
from app.hunter.normalization import normalize_signal
from app.hunter.profiles.vitrina_services import VITRINA_SERVICES_V1
from app.hunter.qualification import qualify_signal
from app.hunter.safety import hunter_runtime_capabilities
from app.hunter.scoring import score_lead


def _signal(text: str, published_at: datetime) -> RawSignal:
    return RawSignal(
        id="fresh-test", source="fixture", source_url="https://example.test/fresh",
        external_id="fresh-test", author_identifier=None, published_at=published_at,
        detected_at=published_at + timedelta(minutes=1), title=text[:60], text=text,
        metadata={"actionable_now": "YES"}, lead_type_hint="HOT_DEMAND",
    )


def test_freshness_classes_and_hard_caps():
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    assert classify_freshness(now - timedelta(hours=2), now).bucket == "ULTRA_FRESH"
    assert classify_freshness(now - timedelta(hours=12), now).bucket == "FRESH"
    assert classify_freshness(now - timedelta(hours=48), now).bucket == "RECENT"
    assert classify_freshness(now - timedelta(days=5), now).score_cap == 69
    assert classify_freshness(now - timedelta(days=10), now).score_cap == 49
    assert classify_freshness(now - timedelta(days=31), now).score_cap == 39

    normalized = normalize_signal(_signal("Нужен новый сайт для мебельной компании, бюджет 200000 рублей, срок 5 дней.", now - timedelta(days=31)))
    intent = RulesIntentProvider().analyze(normalized)
    qualification = qualify_signal(normalized, intent)
    score = score_lead(normalized, intent, qualification, VITRINA_SERVICES_V1, now)
    assert score.score <= 39


def test_missing_publication_is_low_confidence_and_not_very_hot():
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    info = classify_freshness(None, now)
    assert info.bucket == "UNKNOWN"
    assert info.confidence == "LOW"
    assert info.score_cap < 90


def test_hunter_readonly_contract_isolated_from_outbound_actions():
    capabilities = hunter_runtime_capabilities()

    assert capabilities["read_public_sources"] is True
    assert capabilities["write_hunter_reports"] is True
    assert all(not capabilities[name] for name in ("telegram_send", "publication", "direct_message", "webhook", "phone_or_email_outreach"))
