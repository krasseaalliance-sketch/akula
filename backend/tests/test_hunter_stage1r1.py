from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.hunter.freshness import classify_freshness
from app.hunter.intent import RulesIntentProvider
from app.hunter.models import RawSignal
from app.hunter.normalization import normalize_signal
from app.hunter.profiles.vitrina_services import VITRINA_SERVICES_V1
from app.hunter.qualification import qualify_signal
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


def test_hunter_readonly_compose_profile_isolated():
    compose = (Path(__file__).parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    block = compose.split("  hunter-readonly:", 1)[1].split("  frontend:", 1)[0]
    assert 'profiles: ["hunter-readonly"]' in block
    assert "HUNTER_OUTBOUND_DISABLED: \"true\"" in block
    assert 'TELEGRAM_REAL_SEND_ENABLED: \"false\"' in block
    assert "PUBLICATION_MODE: DRY_RUN" in block
    assert ":ro" in block
    assert "worker" not in block and "campaign-engine" not in block
    assert "run_lead_hunter_stage1r1.py" in block
