from __future__ import annotations

from runpy import run_path

_QA = run_path("tools/qa_avito_opportunity_2026_08_11.py")
entity_key = _QA["entity_key"]
classify_taxonomy = _QA["classify_taxonomy"]
run_consistency_checks = _QA["run_consistency_checks"]
score = _QA["score"]


def test_business_entity_dedupe_collapses_similar_listing_name() -> None:
    first = {"seller": "ООО Стройсталь", "avito_ad": "https://avito.ru/one"}
    second = {"seller": "Ещё похожее у исполнителя ООО Стройсталь", "avito_ad": "https://avito.ru/two"}
    assert entity_key(first) == entity_key(second)


def test_taxonomy_does_not_map_logistics_to_furniture_offer() -> None:
    niche, offer, confidence, _ = classify_taxonomy({"seller": "Точная доставка", "title": "Грузоперевозки для бизнеса", "niche": "Грузоперевозки / B2B логистика"})
    assert "логистика" in niche
    assert "мебел" not in offer.casefold()
    assert confidence == "HIGH"


def test_taxonomy_ignores_stale_niche_when_listing_is_construction() -> None:
    niche, offer, confidence, _ = classify_taxonomy({
        "seller": "Строительная компания Тёплый стан",
        "title": "Строительство домов из газобетона",
        "niche": "Мебель / кухни / производство",
    })
    assert "строитель" in niche.casefold()
    assert "мебел" not in offer.casefold()
    assert confidence == "HIGH"


def test_score_caps_unverified_weak_candidate_below_100() -> None:
    value, _ = score({"final_lead_score": 100}, "SITE_UNVERIFIED", "MEDIUM", "HIGH")
    assert value < 100


def test_consistency_checks_reject_final_score_at_100() -> None:
    rows = [{
        "business_entity_key": "one",
        "niche": "B2B/услуги — требуется уточнение",
        "recommended_offer": "Корпоративный сайт",
        "site_status": "SITE_UNVERIFIED",
        "site_ownership_proven": False,
        "lead_score": 99,
        "final_lead_score": 100,
        "seller": "A",
    }]
    assert run_consistency_checks(rows)["passed"] is False


def test_consistency_checks_catch_duplicate_and_taxonomy_conflict() -> None:
    rows = [
        {"business_entity_key": "same", "niche": "Грузоперевозки / B2B логистика", "recommended_offer": "Сайт-каталог мебели", "site_status": "SITE_UNVERIFIED", "site_ownership_proven": False, "lead_score": 94, "seller": "A"},
        {"business_entity_key": "same", "niche": "Строительство домов", "recommended_offer": "Сайт-каталог мебели", "site_status": "SITE_CONFIRMED", "site_ownership_proven": True, "lead_score": 94, "seller": "B"},
    ]
    assert run_consistency_checks(rows)["passed"] is False
