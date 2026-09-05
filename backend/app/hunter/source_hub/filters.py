from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class PositivePattern:
    name: str
    pattern: str
    weight: int = 10


@dataclass(frozen=True)
class NegativePattern:
    name: str
    pattern: str
    penalty: int = 20


@dataclass(frozen=True)
class CommercialVerb:
    name: str
    pattern: str
    weight: int = 10


@dataclass(frozen=True)
class ProductTerm:
    name: str
    pattern: str
    weight: int = 8


@dataclass(frozen=True)
class ServiceTerm:
    name: str
    pattern: str
    weight: int = 8


@dataclass(frozen=True)
class GeoRule:
    name: str
    pattern: str


@dataclass(frozen=True)
class BudgetRule:
    name: str = "currency_amount"
    pattern: str = r"(?P<amount>\d[\d\s]*(?:[.,]\d+)?)\s*(?P<currency>₽|руб(?:\.ля|лей|ль)?|RUB|USD|\$|EUR|€|UAH|грн)"


@dataclass(frozen=True)
class TemporalRule:
    name: str
    pattern: str


@dataclass(frozen=True)
class ExclusionRule:
    name: str
    pattern: str
    penalty: int = 25


@dataclass(frozen=True)
class IntentRuleSet:
    name: str
    language: str
    positive_patterns: tuple[PositivePattern, ...] = ()
    negative_patterns: tuple[NegativePattern, ...] = ()
    commercial_verbs: tuple[CommercialVerb, ...] = ()
    product_terms: tuple[ProductTerm, ...] = ()
    service_terms: tuple[ServiceTerm, ...] = ()
    geo_rules: tuple[GeoRule, ...] = ()
    budget_rules: tuple[BudgetRule, ...] = (BudgetRule(),)
    temporal_rules: tuple[TemporalRule, ...] = ()
    exclusion_rules: tuple[ExclusionRule, ...] = ()


@dataclass
class FastIntentResult:
    score: int
    passed: bool
    freshness_class: str
    positive_evidence: list[str] = field(default_factory=list)
    negative_evidence: list[str] = field(default_factory=list)
    budget: dict[str, str | float] | None = None
    geo: list[str] = field(default_factory=list)
    deadline: str | None = None
    seller_language: bool = False
    vacancy_language: bool = False
    informational: bool = False
    reason: str = ""


def _matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE) is not None


def freshness_class(published_at: datetime | None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if published_at is None:
        return "STALE"
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age = max(0.0, (now - published_at).total_seconds() / 3600)
    if age <= 6:
        return "ULTRA_FRESH"
    if age <= 24:
        return "FRESH"
    if age <= 72:
        return "RECENT"
    if age <= 168:
        return "AGING"
    if age <= 720:
        return "STALE"
    return "DEAD"


def _extract_budget(text: str, rules: Iterable[BudgetRule]) -> dict[str, str | float] | None:
    for rule in rules:
        match = re.search(rule.pattern, text, flags=re.IGNORECASE | re.UNICODE)
        if match:
            amount = float(match.group("amount").replace(" ", "").replace(",", "."))
            return {"amount": amount, "currency": match.group("currency").upper()}
    return None


def _extract_deadline(text: str, rules: Iterable[TemporalRule]) -> str | None:
    for rule in rules:
        match = re.search(rule.pattern, text, flags=re.IGNORECASE | re.UNICODE)
        if match:
            return match.group(0)
    return None


class FastIntentFilter:
    def __init__(self, ruleset: IntentRuleSet):
        self.ruleset = ruleset

    def evaluate(self, text: str, *, published_at: datetime | None = None, now: datetime | None = None, metadata: dict[str, str] | None = None) -> FastIntentResult:
        normalized = " ".join(text.casefold().split())
        positive: list[str] = []
        negative: list[str] = []
        score = 0
        for rule in (*self.ruleset.positive_patterns, *self.ruleset.commercial_verbs, *self.ruleset.product_terms, *self.ruleset.service_terms):
            if _matches(rule.pattern, normalized):
                positive.append(rule.name)
                score += rule.weight
        for rule in (*self.ruleset.negative_patterns, *self.ruleset.exclusion_rules):
            if _matches(rule.pattern, normalized):
                negative.append(rule.name)
                score -= rule.penalty
        budget = _extract_budget(normalized, self.ruleset.budget_rules)
        if budget:
            positive.append("known_budget")
            score += 12
        geo = [rule.name for rule in self.ruleset.geo_rules if _matches(rule.pattern, normalized)]
        if geo:
            positive.append("geo")
            score += 5
        deadline = _extract_deadline(normalized, self.ruleset.temporal_rules)
        if deadline:
            positive.append("deadline")
            score += 8
        if metadata and metadata.get("username"):
            positive.append("public_username")
            score += 3
        freshness = freshness_class(published_at, now)
        freshness_bonus = {"ULTRA_FRESH": 10, "FRESH": 8, "RECENT": 5, "AGING": 0, "STALE": -8, "DEAD": -20}[freshness]
        score += freshness_bonus
        seller = _matches(r"\b(предлагаю услуги|сделаю сайт|ищу работу|резюме|портфолио)\b", normalized)
        vacancy = _matches(r"\b(ваканси[яи]|в штат|ищем сотрудника|зарплата)\b", normalized)
        informational = _matches(r"\b(курс|обучение|вебинар|статья|обсуждение)\b", normalized)
        if seller:
            negative.append("seller_language")
            score -= 35
        if vacancy:
            negative.append("vacancy_language")
            score -= 30
        if informational:
            negative.append("informational_content")
            score -= 20
        passed = score >= 40 and bool(positive) and not seller and not vacancy and freshness not in {"STALE", "DEAD"}
        reason = "; ".join([f"positive={','.join(positive) or 'none'}", f"negative={','.join(negative) or 'none'}", f"freshness={freshness}"])
        return FastIntentResult(max(0, min(100, score)), passed, freshness, positive, negative, budget, geo, deadline, seller, vacancy, informational, reason)


TELEGRAM_RULESET_VITRINA_V1 = IntentRuleSet(
    name="TELEGRAM_RULESET_VITRINA_V1",
    language="ru",
    positive_patterns=tuple(PositivePattern(name, pattern, weight) for name, pattern, weight in (
        ("direct_request", r"\b(ищу|нужен|нужна|нужно|требуется|посоветуйте|кто сделает|кто может сделать)\b", 18),
        ("contractor_request", r"\b(ищем подрядчика|ищем исполнителя|нужен разработчик)\b", 20),
    )),
    negative_patterns=tuple(NegativePattern(name, pattern, penalty) for name, pattern, penalty in (
        ("seller_offer", r"\b(предлагаю услуги|сделаю сайт|готов выполнить)\b", 30),
        ("job_seeker", r"\b(ищу работу|резюме|портфолио)\b", 30),
        ("education", r"\b(курс|обучение|вебинар)\b", 22),
        ("vacancy", r"\b(вакансия|в штат|зарплата)\b", 30),
    )),
    product_terms=tuple(ProductTerm(name, pattern, 10) for name, pattern in (
        ("website", r"\bсайт\b"), ("redesign", r"редизайн"), ("ecommerce", r"интернет[- ]магазин"),
        ("landing", r"лендинг"), ("bot", r"бот"), ("app", r"приложени[ея]"),
    )),
    service_terms=tuple(ServiceTerm(name, pattern, 10) for name, pattern in (
        ("automation", r"автоматизаци[яи]"), ("visualization", r"визуализаци[яи]"), ("3d", r"\b3d\b"), ("render", r"рендер"),
    )),
    geo_rules=tuple(GeoRule(name, rf"\b{pattern}\b") for name, pattern in (("Москва", "москва"), ("Санкт-Петербург", "санкт[- ]петербург"), ("Россия", "росси[яи]"), ("Казахстан", "казахстан"))),
    temporal_rules=(TemporalRule("deadline_phrase", r"\b(до|к|за)\s+\d{1,2}\s*(?:[а-я]+|дн(?:я|ей)?|час(?:а|ов)?)\b"), TemporalRule("urgent", r"\b(срочно|на этой неделе|в течение месяца)\b")),
)
