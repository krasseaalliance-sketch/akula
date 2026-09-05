from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.hunter.intent import RulesIntentProvider
from app.hunter.models import QualificationResult, RawSignal
from app.hunter.normalization import normalize_signal
from app.hunter.profiles import VITRINA_SERVICES_V1
from app.hunter.scoring.money import score_money


def _money_score(text: str):
    now = datetime.now(UTC)
    raw = RawSignal(
        id="test-money", source="test", source_url="https://example.test/order", external_id="test-money",
        author_identifier=None, published_at=now - timedelta(minutes=20), detected_at=now,
        title="Нужен сайт", text=text,
        metadata={"actionable_now": "YES", "manual_verified": True, "source_scope": "TEST"},
        lead_type_hint="HOT_DEMAND",
    )
    normalized = normalize_signal(raw)
    intent = RulesIntentProvider().analyze(normalized)
    qualification = QualificationResult("QUALIFIED", "HOT_DEMAND", ("DIRECT_PROJECT_REQUEST",), 0.95, intent.evidence)
    return score_money(normalized, intent, qualification, VITRINA_SERVICES_V1, now, source_quality=80)


@pytest.mark.parametrize(
    ("budget", "maximum"),
    (("1 500 ₽", 10), ("10 000 ₽", 25), ("30 000 ₽", 45)),
)
def test_budget_caps_limit_commercial_fit_without_dropping_intent(budget: str, maximum: int) -> None:
    score = _money_score(f"Нужен интернет-магазин, ТЗ готово, бюджет {budget}, срочно")
    assert score.intent_score >= 60
    assert score.commercial_fit_score <= maximum
    assert score.result_class == "ACTIONABLE_LOW_VALUE"
    assert score.priority_score < 70


def test_unknown_budget_keeps_scope_based_fit_and_confidence() -> None:
    score = _money_score("Нужен корпоративный сайт, ТЗ готово, CRM, интеграция с 1С и дальнейшая поддержка")
    assert score.intent_score >= 60
    assert score.commercial_fit_score >= 50
    assert score.commercial_fit_confidence == "MEDIUM"
    assert score.result_class == "ACTIONABLE_UNKNOWN_VALUE"
