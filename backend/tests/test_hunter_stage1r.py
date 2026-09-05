from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.hunter.dedupe import canonical_url, classify_duplicate, content_fingerprint
from app.hunter.intent import FallbackIntentProvider, RulesIntentProvider
from app.hunter.models import IntentResult, RawSignal
from app.hunter.normalization import normalize_signal
from app.hunter.profiles.vitrina_services import VITRINA_SERVICES_V1
from app.hunter.qualification import qualify_signal
from app.hunter.safety import (
    HunterOutboundViolation,
    assert_hunter_outbound_disabled,
    hunter_runtime_capabilities,
)
from app.hunter.scoring import score_lead
from app.services import dedupe_key


def raw(text: str, identifier: str = "a") -> RawSignal:
    return RawSignal(
        id=identifier,
        source="fixture",
        source_url=f"https://example.test/{identifier}",
        external_id=identifier,
        author_identifier=None,
        published_at=datetime(2026, 8, 10, tzinfo=UTC),
        detected_at=datetime(2026, 8, 11, tzinfo=UTC),
        title=text[:50],
        text=text,
        metadata={"verification_status": "FIXTURE"},
    )


def test_outbound_guard_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HUNTER_OUTBOUND_DISABLED", "false")
    with pytest.raises(HunterOutboundViolation):
        assert_hunter_outbound_disabled()

    monkeypatch.setenv("HUNTER_OUTBOUND_DISABLED", "true")
    monkeypatch.setenv("TELEGRAM_REAL_SEND_ENABLED", "true")
    with pytest.raises(HunterOutboundViolation):
        assert_hunter_outbound_disabled()

    monkeypatch.setenv("TELEGRAM_REAL_SEND_ENABLED", "false")
    capabilities = hunter_runtime_capabilities()
    assert all(not capabilities[key] for key in ("telegram_send", "publication", "direct_message", "webhook", "phone_or_email_outreach"))


def test_positive_intent_and_qualification():
    signal = normalize_signal(raw("Нужен сайт для компании. Есть ТЗ, бюджет 350 000 руб. и срок 14 дней."))
    result = RulesIntentProvider().analyze(signal)
    qualification = qualify_signal(signal, result)
    assert result.intent == "BUILD_WEBSITE"
    assert result.budget_max == 350000
    assert qualification.decision == "QUALIFIED"


def test_supplier_and_vacancy_are_not_hot_demand():
    for text in ("Я делаю сайты под ключ, обращайтесь.", "Ищем веб-разработчика в штат, резюме отправляйте."):
        signal = normalize_signal(raw(text))
        result = RulesIntentProvider().analyze(signal)
        assert qualify_signal(signal, result).decision in {"REJECTED", "NEEDS_REVIEW"}


def test_null_extraction_and_score_explanation():
    signal = normalize_signal(raw("Нужен сайт для бизнеса, детали обсудим позже."))
    result = RulesIntentProvider().analyze(signal)
    assert result.budget_min is None and result.deadline is None
    qualification = qualify_signal(signal, result)
    score = score_lead(signal, result, qualification, VITRINA_SERVICES_V1, datetime(2026, 8, 11, tzinfo=UTC))
    assert set(score.components) == set(VITRINA_SERVICES_V1.weights)
    assert score.human_summary


def test_exact_and_likely_duplicate_classification():
    first = normalize_signal(raw("Нужен сайт для мебельной компании, бюджет 200 000 руб.", "a"))
    exact = normalize_signal(raw("Нужен сайт для мебельной компании, бюджет 200 000 руб.", "b"))
    likely = normalize_signal(raw("Нужен сайт мебельной компании, бюджет 200000 рублей.", "c"))
    assert classify_duplicate(exact, [first])[0] == "EXACT_DUPLICATE"
    assert classify_duplicate(likely, [first])[0] in {"LIKELY_DUPLICATE", "SAME_DEMAND_DIFFERENT_SOURCE", "UNRELATED"}


def test_dedupe_normalizes_tracking_urls_and_cyrillic_text():
    assert canonical_url("HTTPS://Example.test/task/42/?utm_source=feed&x=1#top") == "https://example.test/task/42?x=1"
    assert canonical_url("https://example.test/task/42?x=1&utm_medium=telegram") == "https://example.test/task/42?x=1"
    assert content_fingerprint("\u041d\u0443\u0436\u0435\u043d \u0441\u0430\u0439\u0442, \u0431\u044e\u0434\u0436\u0435\u0442 200 000") == content_fingerprint("\u041d\u0443\u0436\u0435\u043d \u0441\u0430\u0439\u0442 \u0431\u044e\u0434\u0436\u0435\u0442 200 000")


def test_same_demand_from_distinct_sources_is_marked_for_reviewable_dedupe():
    first = normalize_signal(raw("\u041d\u0443\u0436\u0435\u043d \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442 \u043c\u0430\u0433\u0430\u0437\u0438\u043d \u0434\u043b\u044f \u043c\u0435\u0431\u0435\u043b\u044c\u043d\u043e\u0439 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0438, \u0431\u044e\u0434\u0436\u0435\u0442 200000", "a"))
    second_raw = raw("\u041d\u0443\u0436\u0435\u043d \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442 \u043c\u0430\u0433\u0430\u0437\u0438\u043d \u0434\u043b\u044f \u043c\u0435\u0431\u0435\u043b\u044c\u043d\u043e\u0439 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0438, \u0431\u044e\u0434\u0436\u0435\u0442 200000", "b")
    second = normalize_signal(second_raw)
    assert classify_duplicate(second, [first])[0] == "EXACT_DUPLICATE"


def test_campaign_scope_keeps_parallel_campaigns_independent():
    common = {"author_username": "buyer", "normalized_text": "Нужен сайт", "source_platform": "TELEGRAM"}
    assert dedupe_key(**common, campaign_id="campaign-a") != dedupe_key(**common, campaign_id="campaign-b")
    assert dedupe_key(**common, campaign_id="campaign-a") == dedupe_key(**common, campaign_id="campaign-a")


class MalformedProvider:
    def analyze(self, signal):
        return {"intent": "BUILD_WEBSITE"}


class TimeoutProvider:
    def analyze(self, signal):
        raise TimeoutError("provider timeout")


def test_provider_malformed_and_timeout_fallback():
    signal = normalize_signal(raw("Нужен сайт для компании с ТЗ."))
    for primary in (MalformedProvider(), TimeoutProvider()):
        result = FallbackIntentProvider(primary).analyze(signal)
        assert isinstance(result, IntentResult)
        assert result.intent == "BUILD_WEBSITE"
