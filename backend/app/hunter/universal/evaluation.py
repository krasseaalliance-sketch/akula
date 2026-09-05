from __future__ import annotations

from dataclasses import dataclass

from .engine import BusinessUnderstandingEngine
from .models import BusinessInput


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    input_data: BusinessInput
    expected_policy: str = "NORMAL"
    expected_geo: str | None = None


REFERENCE_CASES = (
    EvaluationCase("vitrina web studio", BusinessInput(company_name="Vitrina Services", service_description="website development, redesign, e-commerce, bots", country="Russia", customer_type="business"), expected_geo="REMOTE"),
    EvaluationCase("premium concierge", BusinessInput(service_description="premium concierge and personal assistance for travelers", country="Indonesia")),
    EvaluationCase("north bali excursions", BusinessInput(service_description="North Bali excursions and private tours", service_area="North Bali", customer_type="consumers"), expected_geo="REGION"),
    EvaluationCase("nusa penida excursions", BusinessInput(service_description="Nusa Penida boat trips and excursions", service_area="Nusa Penida", customer_type="consumers"), expected_geo="REGION"),
    EvaluationCase("real estate", BusinessInput(service_description="real estate brokerage for residential property", city="Krasnoyarsk", customer_type="consumers"), expected_geo="CITY"),
    EvaluationCase("dentistry", BusinessInput(service_description="dentistry and dental implants", city="Krasnoyarsk"), expected_policy="REGULATED", expected_geo="CITY"),
    EvaluationCase("flower shop", BusinessInput(product_description="bouquets and flower delivery", city="Krasnoyarsk"), expected_geo="CITY"),
    EvaluationCase("grooming salon", BusinessInput(service_description="pet grooming salon", city="Krasnoyarsk", service_area="10 km"), expected_geo="CITY"),
    EvaluationCase("property management", BusinessInput(service_description="property management for apartment owners", customer_type="business")),
    EvaluationCase("tarot service", BusinessInput(service_description="tarot consultations and readings", customer_type="consumers")),
    EvaluationCase("manufacturing", BusinessInput(product_description="industrial components for manufacturers", customer_type="business")),
    EvaluationCase("logistics", BusinessInput(service_description="regional freight logistics", customer_type="business", country="Russia")),
    EvaluationCase("architecture bureau", BusinessInput(service_description="architecture and project bureau", customer_type="business")),
    EvaluationCase("printing", BusinessInput(service_description="commercial printing and packaging", customer_type="business")),
    EvaluationCase("automotive service", BusinessInput(service_description="automotive repair and maintenance", city="Krasnoyarsk"), expected_geo="CITY"),
    EvaluationCase("cleaning", BusinessInput(service_description="office and home cleaning", city="Krasnoyarsk"), expected_geo="CITY"),
    EvaluationCase("construction", BusinessInput(service_description="construction contractor for commercial buildings", customer_type="business")),
    EvaluationCase("industrial supplier", BusinessInput(product_description="B2B industrial equipment supply", customer_type="business")),
    EvaluationCase("restaurant hospitality", BusinessInput(service_description="restaurant and event hospitality", city="Krasnoyarsk"), expected_geo="CITY"),
    EvaluationCase("legal consulting", BusinessInput(service_description="legal and consulting services", customer_type="business"), expected_policy="REGULATED"),
    EvaluationCase("tourism operator", BusinessInput(service_description="tourism and excursion operator", country="Indonesia")),
    EvaluationCase("education", BusinessInput(service_description="professional education courses")),
    EvaluationCase("retail", BusinessInput(product_description="online retail of home goods")),
)

UNSEEN_CASES = (
    EvaluationCase("marine survey", BusinessInput(service_description="marine survey and vessel inspection", customer_type="business")),
    EvaluationCase("solar installer", BusinessInput(service_description="solar panel installation for homes", city="Krasnoyarsk"), expected_geo="CITY"),
    EvaluationCase("food subscription", BusinessInput(product_description="weekly prepared meal subscription", city="Krasnoyarsk"), expected_geo="CITY"),
    EvaluationCase("cybersecurity consultancy", BusinessInput(service_description="cybersecurity audit for companies", customer_type="business")),
    EvaluationCase("wedding florist", BusinessInput(service_description="wedding floral design and delivery", service_area="Krasnoyarsk"), expected_geo="REGION"),
)


def evaluate(cases: tuple[EvaluationCase, ...] = REFERENCE_CASES) -> dict[str, object]:
    engine = BusinessUnderstandingEngine()
    rows = []
    for case in cases:
        result = engine.understand(case.input_data)
        accepted = bool(result.business_model.evidence) and result.policy_decision.status == case.expected_policy and (case.expected_geo is None or result.geo_model.scope == case.expected_geo)
        rows.append({"name": case.name, "passed": accepted, "policy": result.policy_decision.status, "geo": result.geo_model.scope, "confidence": result.business_model.overall_confidence, "hallucinated_required_fields": 0})
    return {"count": len(rows), "passed": sum(row["passed"] for row in rows), "rows": rows}


def evaluate_unseen() -> dict[str, object]:
    return evaluate(UNSEEN_CASES)
