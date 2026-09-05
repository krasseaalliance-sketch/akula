from __future__ import annotations

from datetime import UTC, datetime, timedelta
from runpy import run_path
from types import SimpleNamespace

import pytest
from app.hunter.intent import RulesIntentProvider
from app.hunter.models import QualificationResult, RawSignal
from app.hunter.normalization import normalize_signal
from app.hunter.profiles import VITRINA_SERVICES_V1
from app.hunter.scoring.money import score_money

_R4 = run_path("tools/run_lead_hunter_stage1r4.py")
FileInternalAlertAdapter = _R4["FileInternalAlertAdapter"]
InternalAlertSecurityError = _R4["InternalAlertSecurityError"]
should_alert = _R4["should_alert"]


def test_unknown_budget_is_capped_without_strong_corporate_or_tender_proof() -> None:
    now = datetime.now(UTC)
    raw = RawSignal(
        id="travel", source="test", source_url="https://example.test/travel", external_id="travel",
        author_identifier=None, published_at=now - timedelta(minutes=20), detected_at=now,
        title="Редизайн страницы travel-бренда",
        text="Сделать дизайн страницы по ТЗ, собрать на Tilda, адаптив, CRM, формы и аналитику",
        metadata={"actionable_now": "YES", "manual_verified": True}, lead_type_hint="HOT_DEMAND",
    )
    normalized = normalize_signal(raw)
    intent = RulesIntentProvider().analyze(normalized)
    qualification = QualificationResult("QUALIFIED", "HOT_DEMAND", ("DIRECT_PROJECT_REQUEST",), 0.95, intent.evidence)
    score = score_money(normalized, intent, qualification, VITRINA_SERVICES_V1, now, source_quality=80)
    assert score.commercial_fit_score <= 90
    assert score.commercial_value_confidence == "MEDIUM"


def test_alert_dedupe_allows_only_significant_change() -> None:
    lead = SimpleNamespace(
        actionable_now="YES", freshness={"within_72h": True, "age_hours": 2}, intent_score=90,
        commercial_fit_score=80, priority_score=75, result_class="GOOD_FIT", budget={"min": 100000, "max": 100000},
        deadline=None, original_signal_excerpt="new corporate website", source="test", source_url="https://example.test", id="1",
    )
    previous = {"first_alerted_at": "2026-08-11T00:00:00+00:00", "snapshot": {"budget": lead.budget, "deadline": None, "actionable_now": "YES", "priority_score": 75, "result_class": "GOOD_FIT", "excerpt_hash": "wrong"}}
    assert should_alert(previous, lead) is True
    previous["snapshot"]["excerpt_hash"] = __import__("hashlib").sha256(lead.original_signal_excerpt.encode()).hexdigest()[:16]
    assert should_alert(previous, lead) is False


def test_internal_recipient_cannot_be_overridden_by_arbitrary_value(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HUNTER_INTERNAL_NOTIFY_RECIPIENT", "attacker-chat")
    adapter = FileInternalAlertAdapter(tmp_path / "alerts.jsonl")
    with pytest.raises(InternalAlertSecurityError):
        adapter.dispatch({"event_type": "MONEY_NOW_ALERT"})
