from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.hunter.intent import RulesIntentProvider
from app.hunter.models import QualificationResult, RawSignal
from app.hunter.normalization import normalize_signal
from app.hunter.profiles import VITRINA_SERVICES_V1
from app.hunter.safety import (
    HunterOutboundViolation,
    assert_hunter_outbound_disabled,
    hunter_runtime_capabilities,
)
from app.hunter.scoring.money import score_money


def test_unknown_budget_is_capped_without_strong_corporate_or_tender_proof() -> None:
    now = datetime.now(UTC)
    raw = RawSignal(
        id="travel", source="test", source_url="https://example.test/travel", external_id="travel",
        author_identifier=None, published_at=now - timedelta(minutes=20), detected_at=now,
        title="Редизайн страницы travel-бренда",
        text="Сделать дизайн страницы по ТЗ, собрать на Tilda, адаптив, CRM, формы и аналитика",
        metadata={"actionable_now": "YES", "manual_verified": True}, lead_type_hint="HOT_DEMAND",
    )
    normalized = normalize_signal(raw)
    intent = RulesIntentProvider().analyze(normalized)
    qualification = QualificationResult("QUALIFIED", "HOT_DEMAND", ("DIRECT_PROJECT_REQUEST",), 0.95, intent.evidence)
    score = score_money(normalized, intent, qualification, VITRINA_SERVICES_V1, now, source_quality=80)

    assert score.commercial_fit_score <= 90
    assert score.commercial_value_confidence == "MEDIUM"


def test_hunter_outbound_guard_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_OUTBOUND_DISABLED", "false")

    with pytest.raises(HunterOutboundViolation):
        assert_hunter_outbound_disabled()


def test_current_hunter_capabilities_never_include_outbound_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_OUTBOUND_DISABLED", "true")
    monkeypatch.setenv("TELEGRAM_REAL_SEND_ENABLED", "false")

    capabilities = hunter_runtime_capabilities()

    assert all(not capabilities[name] for name in ("telegram_send", "publication", "direct_message", "webhook", "phone_or_email_outreach"))
