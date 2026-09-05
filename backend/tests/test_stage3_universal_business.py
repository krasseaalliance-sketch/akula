from __future__ import annotations

import json

import pytest
from app.hunter.universal import BusinessInput, BusinessUnderstandingEngine, validate_feedback
from app.hunter.universal.audit import audit_model
from app.hunter.universal.contracts import CampaignScope, FeedbackEvent
from app.hunter.universal.evaluation import evaluate, evaluate_unseen
from app.hunter.universal.matching import match_signal
from app.hunter.universal.policy import evaluate_business_policy
from app.hunter.universal.source_contract import to_source_hub_contract
from app.hunter.universal.versioning import ModelVersionStore


def test_business_input_accepts_minimal_identifier_and_rejects_empty() -> None:
    assert BusinessInput(website="https://example.com").supplied_fields == ("website",)
    with pytest.raises(ValueError):
        BusinessInput()


def test_generic_engine_builds_evidence_backed_multi_offer_model() -> None:
    result = BusinessUnderstandingEngine().understand(BusinessInput(company_name="Demo", service_description="website development, redesign, bots", product_description="templates", customer_type="business", country="Russia"))
    assert result.business_model.model_version == "business-model-v1"
    assert len(result.offer_graph.nodes) == 4
    assert result.business_model.services.evidence
    assert result.demand_model.intent_classes
    assert result.negative_intent_map.exclusions
    assert result.source_strategy.preferred
    assert result.matching_profile.priority_score >= 0


def test_unknown_budget_is_not_low_value() -> None:
    result = BusinessUnderstandingEngine().understand(BusinessInput(service_description="architecture project bureau"))
    assert result.commercial_value_model.known_minimum_order is None
    assert result.commercial_value_model.confidence_class == "LOW"
    assert result.commercial_value_model.unknown_budget_penalty > 0
    assert result.business_model.minimum_commercial_value.value is None


def test_policy_allowed_prohibited_and_ambiguous() -> None:
    assert evaluate_business_policy(BusinessInput(service_description="cleaning service")).status == "NORMAL"
    assert evaluate_business_policy(BusinessInput(service_description="fraud services")).status == "PROHIBITED"
    assert evaluate_business_policy(BusinessInput(service_description="weapons consulting")).status == "POLICY_REVIEW_REQUIRED"


def test_source_hub_contract_is_read_only() -> None:
    result = BusinessUnderstandingEngine().understand(BusinessInput(service_description="website development"))
    contract = to_source_hub_contract(result.demand_model, result.source_strategy)
    assert contract.writes_allowed is False
    assert contract.activation == "READ_ONLY_CONTRACT_ONLY"


def test_campaign_boundary_feedback_and_matching() -> None:
    result = BusinessUnderstandingEngine().understand(BusinessInput(service_description="website development"))
    campaign = CampaignScope("campaign-1", result.business_model.business_id, tuple(node.offer_id for node in result.offer_graph.nodes), "find direct project demand")
    assert campaign.billing_boundary == "EXTERNAL_COMMERCIAL_POLICY"
    event = FeedbackEvent(result.business_model.business_id, result.demand_model.demand_model_id, "GOOD_LEAD", "operator")
    validate_feedback(event)
    matched = match_signal(result.matching_profile, {"text": "ищу работу программистом"})
    assert matched.blocking_reasons


def test_model_versioning_is_append_only_and_workspace_isolated(tmp_path) -> None:
    store = ModelVersionStore(tmp_path / "models.json")
    result = BusinessUnderstandingEngine().understand(BusinessInput(website="https://example.com"))
    event = audit_model("business_model.create", result.business_model.business_id, "operator", after_version=result.business_model.model_version)
    from app.hunter.universal.contracts import new_model_version
    version = new_model_version("BusinessModel", result.business_model.model_version, result.business_model.evidence)
    store.append(workspace_id="w1", business_id=result.business_model.business_id, model=result.business_model.to_dict(), version=version, audit_event=event)
    assert len(store.history(workspace_id="w1", business_id=result.business_model.business_id)) == 1
    assert store.history(workspace_id="w2", business_id=result.business_model.business_id) == []
    assert json.loads((tmp_path / "models.json").read_text(encoding="utf-8"))["audit"]


def test_stage3_reference_and_unseen_cases() -> None:
    reference = evaluate()
    unseen = evaluate_unseen()
    assert reference["count"] >= 20
    assert reference["passed"] == reference["count"]
    assert unseen["count"] == 5
    assert unseen["passed"] == 5


def test_no_outreach_contract() -> None:
    result = BusinessUnderstandingEngine().understand(BusinessInput(service_description="website development"))
    assert result.source_strategy.cadence_minutes > 0
    assert not hasattr(result, "outreach")
