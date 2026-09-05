from __future__ import annotations

import re
from hashlib import sha256

from .models import (
    BusinessInput,
    BusinessLanguageModel,
    BusinessModel,
    BuyerModel,
    ClarificationQuestion,
    CommercialValueModel,
    DemandModel,
    GeoModel,
    Inference,
    IntentMap,
    MarketContext,
    MatchingProfile,
    NegativeIntentMap,
    OfferGraph,
    OfferNode,
    PolicyDecision,
    SourceStrategy,
    UnderstandingResult,
)

CANONICAL_INTENTS = (
    "DIRECT_PURCHASE_INTENT", "PROVIDER_SEARCH", "RECOMMENDATION_REQUEST", "QUOTE_REQUEST",
    "CONTRACTOR_SEARCH", "SUPPLIER_SEARCH", "TENDER_RFP", "REPLACEMENT_SEARCH",
    "URGENT_SERVICE_REQUEST", "INFORMATIONAL_ONLY", "SELLER_OFFER", "JOB_SEARCH",
    "EMPLOYEE_HIRING", "NOISE",
)

PROHIBITED = ("illegal drugs", "child sexual exploitation", "human trafficking", "sale of people", "stolen goods", "fraud services")
REGULATED = ("medical", "dentistry", "legal", "financial", "weapons", "alcohol")
WEB_TERMS = ("website", "сайт", "лендинг", "магазин", "crm", "бот", "приложен", "автоматизац", "рендер", "визуализ")
LOCAL_TERMS = ("салон", "стоматолог", "парикмах", "клини", "ресторан", "уборк", "ремонт", "цветоч")


def _text(value: str | None) -> str:
    return (value or "").strip()


def _evidence(input_data: BusinessInput) -> tuple[str, ...]:
    return tuple(f"input.{field}" for field in input_data.supplied_fields)


def _contains(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    lowered = text.casefold()
    return tuple(term for term in terms if term.casefold() in lowered)


def _business_text(input_data: BusinessInput) -> str:
    return " ".join(_text(value) for value in (input_data.company_name, input_data.business_description, input_data.product_description, input_data.service_description, input_data.operator_notes) if value)


class BusinessUnderstandingEngine:
    """Generic rules-first understanding; no industry-specific Python branches."""

    model_version = "business-model-v1"

    def understand(self, input_data: BusinessInput) -> UnderstandingResult:
        text = _business_text(input_data)
        evidence = _evidence(input_data)
        web_hits = _contains(text, WEB_TERMS)
        local_hits = _contains(text, LOCAL_TERMS)
        regulated_hits = _contains(text, REGULATED)
        prohibited_hits = _contains(text, PROHIBITED)
        name = input_data.company_name
        if web_hits:
            business_type, industry = "DIGITAL_SERVICE_PROVIDER", "digital services"
        elif local_hits:
            business_type, industry = "LOCAL_SERVICE_BUSINESS", "local services"
        elif input_data.customer_type and "business" in input_data.customer_type.casefold():
            business_type, industry = "B2B_BUSINESS", "commercial services"
        elif text:
            business_type, industry = "COMMERCIAL_BUSINESS", "commercial activity"
        else:
            business_type, industry = "UNKNOWN", None
        confidence = min(0.95, 0.42 + 0.08 * len(input_data.supplied_fields) + (0.12 if web_hits or local_hits else 0))
        if len(text) < 20:
            confidence = min(confidence, 0.35)
        services = tuple(dict.fromkeys(_extract_items(input_data.service_description or "", (",", ";", " и "))))
        products = tuple(dict.fromkeys(_extract_items(input_data.product_description or "", (",", ";", " и "))))
        if not services and web_hits:
            services = ("website development and digital implementation",)
        summary = text[:500] if text else None
        geo = self._geo(input_data, text, evidence)
        language = self._language(input_data, text, evidence)
        market = MarketContext(input_data.country, "RUB" if (input_data.country or "").casefold() in {"ru", "russia", "россия"} else None, None, language.market_languages, None, None, None, evidence)
        model = BusinessModel(
            business_id=self._id(input_data), model_version=self.model_version,
            business_name=Inference(name, 0.95 if name else 0.0, ("input.company_name",) if name else ()),
            business_type=Inference(business_type, confidence, evidence),
            business_summary=Inference(summary, confidence if summary else 0.0, evidence),
            industry_primary=Inference(industry, confidence if industry else 0.0, evidence),
            industry_secondary=Inference((), 0.2 if text else 0.0, evidence),
            business_model_type=Inference("SERVICE" if services and not products else "PRODUCT_OR_SERVICE", confidence, evidence),
            b2b_b2c_class=Inference(self._b2b_b2c(input_data, text), min(0.85, confidence), evidence),
            products=Inference(products, 0.8 if products else 0.0, ("input.product_description",) if products else ()),
            services=Inference(services, 0.8 if services else 0.0, ("input.service_description",) if services else ()),
            bundles=Inference((), 0.0, ()), customer_segments=Inference(self._segments(input_data), 0.55 if input_data.customer_type else 0.0, evidence),
            geographies=Inference(tuple(filter(None, (input_data.country, input_data.region, input_data.city, input_data.service_area))), 0.9 if any((input_data.country, input_data.region, input_data.city, input_data.service_area)) else 0.0, evidence),
            languages=Inference(language.business_languages, language.confidence, language.evidence),
            price_positioning=Inference(None, 0.0, ()), minimum_commercial_value=Inference(input_data.known_minimum_order, 0.95 if input_data.known_minimum_order is not None else 0.0, ("input.known_minimum_order",) if input_data.known_minimum_order is not None else ()),
            seasonality=Inference(None, 0.0, ()), urgency_patterns=Inference(("deadline or immediate need",), 0.35, ()),
            repeat_purchase_pattern=Inference("RECURRING_POSSIBLE" if local_hits else None, 0.35 if local_hits else 0.0, ()), sales_cycle_class=Inference("SHORT" if local_hits else "UNKNOWN", 0.35 if local_hits else 0.0, ()),
            regulatory_flags=Inference(tuple(regulated_hits), 0.8 if regulated_hits else 0.0, evidence), overall_confidence=confidence, evidence=evidence,
        )
        graph = self._offer_graph(model, input_data)
        buyers = tuple(self._buyer_model(node, model, input_data) for node in graph.nodes)
        value = self._commercial_value(input_data, model, graph)
        intent = self._intent_map(model, graph)
        negative = self._negative_map(text)
        demand = DemandModel(self._id(input_data) + ":demand:v1", model.business_id, tuple(n.offer_id for n in graph.nodes), intent.canonical_families, tuple(b.offer_id for b in buyers), intent.positive_patterns, negative.patterns, ("new project", "replacement", "urgent need"), ("direct request",), ("budget", "deadline", "geography"), {"known_budget": input_data.known_minimum_order, "unknown_reduces_confidence": True}, geo, language, {"priority_hours": 72, "dead_after_days": 30}, value, {"exclude": negative.exclusions}, min(model.overall_confidence, 0.85), evidence)
        strategy = self._source_strategy(model, demand, language)
        matching = MatchingProfile(model.business_id, round((model.overall_confidence + value.unknown_budget_penalty + (0.2 if graph.nodes else 0)) * 100, 2), round(model.overall_confidence * 100, 2), round(max(0, 100 - value.unknown_budget_penalty * 100), 2), round(model.overall_confidence * 70 + (30 if input_data.known_minimum_order else 10), 2), ("business model has evidence", "offer graph is available"), negative.exclusions, model.overall_confidence)
        policy = self._policy(text, regulated_hits, prohibited_hits, evidence)
        questions = self._clarifications(model, input_data)
        return UnderstandingResult(model, graph, buyers, demand, intent, negative, value, geo, language, market, strategy, matching, policy, questions)

    @staticmethod
    def _id(input_data: BusinessInput) -> str:
        return "biz_" + sha256((input_data.website or input_data.company_name or _business_text(input_data)).encode()).hexdigest()[:16]

    def _offer_graph(self, model: BusinessModel, input_data: BusinessInput) -> OfferGraph:
        names = list(model.services.value) + list(model.products.value)
        if not names and model.business_summary.value:
            names = ["primary commercial offer"]
        nodes = tuple(OfferNode(f"{model.business_id}:offer:{index}", name, "SERVICE" if name in model.services.value else "PRODUCT", "OWN_OFFER", ("input.service_description" if name in model.services.value else "input.product_description",), 0.8) for index, name in enumerate(dict.fromkeys(names), 1))
        return OfferGraph(model.business_id, nodes, ())

    def _buyer_model(self, node: OfferNode, model: BusinessModel, input_data: BusinessInput) -> BuyerModel:
        b2b = model.b2b_b2c_class.value in {"B2B", "B2B_B2C"}
        return BuyerModel(node.offer_id, ("business buyer",) if b2b else ("consumer", "household"), ("owner", "procurement", "decision maker") if b2b else ("end customer",), ("SMB", "corporate") if b2b else (), ("local consumer",) if not b2b else (), ("new need", "replacement", "growth"), ("new project", "deadline", "life event"), ("quote request", "service inquiry"), ("scope", "price", "availability"), ("stated budget", "request for quote"), ("deadline", "urgent", "soon"), ("asks price", "asks availability", "provides scope"), ("discussion only", "seller offer", "job seeker"), model.overall_confidence, model.evidence)

    def _intent_map(self, model: BusinessModel, graph: OfferGraph) -> IntentMap:
        families = ("DIRECT_PURCHASE_INTENT", "PROVIDER_SEARCH", "QUOTE_REQUEST", "URGENT_SERVICE_REQUEST", "INFORMATIONAL_ONLY", "SELLER_OFFER", "JOB_SEARCH", "NOISE")
        specific = tuple("BUY_" + re.sub(r"[^A-Z0-9]+", "_", node.name.upper()).strip("_") for node in graph.nodes)
        return IntentMap(families, specific, ("looking for", "need", "order", "book", "hire", "quote", "price", "deadline"), model.evidence)

    def _negative_map(self, text: str) -> NegativeIntentMap:
        return NegativeIntentMap(("seller instead of buyer", "job seeker", "discussion", "news", "spam", "old or closed demand", "competitor offer"), ("looking for work", "vacancy", "selling", "news", "discussion", "just curious", "closed", "no longer needed"), ("generic negative-intent contract",))

    def _commercial_value(self, input_data: BusinessInput, model: BusinessModel, graph: OfferGraph) -> CommercialValueModel:
        known = input_data.known_minimum_order
        return CommercialValueModel(known, ("scope", "buyer class", "service fit", "urgency", "repeat potential"), "HIGH" if known is not None else "LOW", 0.0 if known is not None else 0.25, "RECURRING_POSSIBLE" if model.business_type.value == "LOCAL_SERVICE_BUSINESS" else "UNKNOWN", "POSSIBLE" if len(graph.nodes) > 1 else "UNKNOWN", "SHORT" if model.business_type.value == "LOCAL_SERVICE_BUSINESS" else "UNKNOWN", model.evidence)

    def _source_strategy(self, model: BusinessModel, demand: DemandModel, language: BusinessLanguageModel) -> SourceStrategy:
        if model.business_type.value == "DIGITAL_SERVICE_PROVIDER":
            preferred = ("freelance marketplaces", "public project channels", "business communities")
        elif model.business_type.value == "LOCAL_SERVICE_BUSINESS":
            preferred = ("local public communities", "recommendation requests", "local business pages")
        else:
            preferred = ("public project requests", "business communities", "tender/RFP sources")
        return SourceStrategy(preferred, ("web-indexed requests",), ("candidate sources requiring review",), ("private data", "sources requiring bypass"), ("unconfigured or blocked endpoints",), "<=72h for actionable demand", 15, model.evidence)

    def _geo(self, input_data: BusinessInput, text: str, evidence: tuple[str, ...]) -> GeoModel:
        if input_data.service_area or input_data.city or _contains(text, LOCAL_TERMS):
            scope = "CITY" if input_data.city else "REGION"
            return GeoModel(scope, input_data.service_area, input_data.service_area, None, False, (), evidence, 0.7)
        return GeoModel("REMOTE" if _contains(text, WEB_TERMS) else "COUNTRY", None, None, None, True if _contains(text, WEB_TERMS) else None, (), evidence, 0.55)

    def _language(self, input_data: BusinessInput, text: str, evidence: tuple[str, ...]) -> BusinessLanguageModel:
        language = "ru" if re.search(r"[А-Яа-яЁё]", text) else "en" if text else None
        return BusinessLanguageModel(language, (language,) if language else (), (language,) if language else (), ("ru", "en"), ("ru", "en"), 0.8 if language else 0.0, evidence)

    @staticmethod
    def _b2b_b2c(input_data: BusinessInput, text: str) -> str:
        value = (input_data.customer_type or "").casefold()
        if "business" in value or "b2b" in value or "corporate" in text.casefold():
            return "B2B"
        if "consumer" in value or "клиент" in text.casefold():
            return "B2C"
        return "UNKNOWN"

    @staticmethod
    def _segments(input_data: BusinessInput) -> tuple[str, ...]:
        return (input_data.customer_type,) if input_data.customer_type else ()

    @staticmethod
    def _policy(text: str, regulated: tuple[str, ...], prohibited: tuple[str, ...], evidence: tuple[str, ...]) -> PolicyDecision:
        lowered = text.casefold()
        if prohibited:
            return PolicyDecision("PROHIBITED", prohibited[0], ("explicit prohibited commercial category",), evidence)
        if any(term in lowered for term in ("weapon", "наркот", "людьми")) and not prohibited:
            return PolicyDecision("POLICY_REVIEW_REQUIRED", None, ("ambiguous sensitive wording",), evidence)
        return PolicyDecision("REGULATED" if regulated else "NORMAL", regulated[0] if regulated else None, (), evidence)

    @staticmethod
    def _clarifications(model: BusinessModel, input_data: BusinessInput) -> tuple[ClarificationQuestion, ...]:
        questions: list[ClarificationQuestion] = []
        if not input_data.service_description and not input_data.product_description:
            questions.append(ClarificationQuestion("offers", "Какие услуги или товары сейчас для вас приоритетны?", "offer graph is inferred with low confidence", 1))
        if not input_data.customer_type:
            questions.append(ClarificationQuestion("customers", "Кто ваш основной клиент: частные лица, компании или оба варианта?", "buyer model is uncertain", 2))
        if len(questions) > 5:
            questions = questions[:5]
        return tuple(questions)


def _extract_items(value: str, separators: tuple[str, ...]) -> list[str]:
    result = [value]
    for separator in separators:
        result = [item for chunk in result for item in chunk.split(separator)]
    return [item.strip() for item in result if item.strip()]
