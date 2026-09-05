from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MoneyFilterConfig:
    """Configurable commercial-fit gates for VITRINA_SERVICES_V1."""

    budget_caps: tuple[tuple[int, int], ...] = (
        (5_000, 10), (15_000, 25), (30_000, 45), (75_000, 65),
        (150_000, 80), (300_000, 95),
    )
    unknown_budget_base: int = 58
    priority_weights: tuple[tuple[str, float], ...] = (
        ("intent", 0.70), ("freshness", 0.10), ("actionability", 0.10), ("source_quality", 0.10),
    )
    hot_money_fit_min: int = 75
    good_fit_min: int = 50
    money_now_priority_threshold: int = 70
    unknown_budget_default_cap: int = 85
    unknown_budget_strong_cap: int = 90
    unknown_budget_very_strong_cap: int = 95


@dataclass(frozen=True)
class HunterProfile:
    profile_id: str
    version: int
    primary_offers: tuple[str, ...]
    secondary_offers: tuple[str, ...]
    accepted_intents: tuple[str, ...]
    weights: dict[str, int]
    minimum_score: int = 60
    hot_score: int = 75
    max_freshness_days: int = 120
    money_filter: MoneyFilterConfig = MoneyFilterConfig()


VITRINA_SERVICES_V1 = HunterProfile(
    profile_id="VITRINA_SERVICES_V1",
    version=1,
    primary_offers=("BUILD_WEBSITE", "REDESIGN_WEBSITE"),
    secondary_offers=(
        "BUILD_ECOMMERCE", "BUILD_LANDING", "BUILD_CORPORATE_SITE",
        "BUILD_CATALOG_SITE", "BUILD_BOT", "BUILD_WEB_APP", "BUILD_MOBILE_APP",
        "BUILD_CALCULATOR", "BUILD_CONFIGURATOR", "AUTOMATE_BUSINESS_PROCESS",
        "CREATE_3D_RENDER", "CREATE_VISUALIZATION",
    ),
    accepted_intents=(
        "BUILD_WEBSITE", "REDESIGN_WEBSITE", "BUILD_ECOMMERCE", "BUILD_LANDING",
        "BUILD_CORPORATE_SITE", "BUILD_CATALOG_SITE", "BUILD_BOT", "BUILD_WEB_APP",
        "BUILD_MOBILE_APP", "BUILD_CALCULATOR", "BUILD_CONFIGURATOR",
        "AUTOMATE_BUSINESS_PROCESS", "CREATE_3D_RENDER", "CREATE_VISUALIZATION",
        "DIGITAL_CONTRACTOR_REQUEST",
    ),
    weights={
        "direct_order_intent": 20, "project_specificity": 15, "budget_signal": 12,
        "requirements_signal": 12, "deadline_signal": 10, "urgency_signal": 8,
        "contractor_signal": 8, "commercial_scale": 6, "freshness": 5,
        "vitrina_product_fit": 4,
    },
)
