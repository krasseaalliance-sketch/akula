import asyncio

import pytest
from app.integrations import (
    MockLeadSourceAdapter,
    MockMessageGenerationProvider,
    MockPlatformAdapter,
    PublishRequest,
    validate_message,
)
from app.policy import POLICIES, PolicyEngine
from app.services import ROLE_PERMISSIONS


@pytest.mark.parametrize(
    "role,permission,allowed",
    [
        ("OWNER", "workspace.manage", True),
        ("ADMIN", "workspace.manage", False),
        ("MANAGER", "campaign.create", True),
        ("OPERATOR", "campaign.create", False),
        ("ANALYST", "analytics.view", True),
        ("ANALYST", "message.approve", False),
        ("VIEWER", "audit.view", False),
    ],
)
def test_rbac_matrix(role: str, permission: str, allowed: bool):
    assert (permission in ROLE_PERMISSIONS[role]) is allowed


def test_policy_engine_reports_full_decision_shape_and_all_policies():
    assert len(POLICIES) >= 16
    decision = PolicyEngine().can_publish(
        safety_lock=False,
        campaign_status="ACTIVE",
        message_approved=True,
        community_status="APPROVED",
        sent_today=0,
        daily_limit=10,
    )
    assert decision.decision == "ALLOW"
    assert decision.policy_version
    assert decision.evaluated_at
    assert set(decision.checked_policies) == set(POLICIES)
    denied = PolicyEngine().can_publish(
        safety_lock=True,
        campaign_status="ACTIVE",
        message_approved=True,
        community_status="APPROVED",
        sent_today=0,
        daily_limit=10,
    )
    assert denied.decision == "DENY"
    assert "NO_EMERGENCY_STOP" in denied.denied_policies
    assert denied.reasons


def test_message_validation_blocks_safety_cases():
    assert validate_message("Нормальный текст").valid
    assert "PROHIBITED_WORD" in validate_message("Гарантированно заработаете").reasons
    assert "UNSUPPORTED_LANGUAGE" in validate_message("Text", language="de").reasons
    assert "CONTENT_TOO_LONG" in validate_message("x" * 20, max_length=10).reasons
    assert "TOO_SIMILAR" in validate_message("ok", similarity_score=0.99).reasons


def test_mock_providers_are_deterministic_and_idempotent():
    generated = MockMessageGenerationProvider().generate(
        campaign_name="Campaign", objective="Objective", facts={"verified": True}
    )
    assert generated.facts_snapshot["verified"] is True
    adapter = MockPlatformAdapter()
    request = PublishRequest(destination="mock", content="hello", idempotency_key="same-key")
    first = asyncio.run(adapter.publish_message(request))
    second = asyncio.run(adapter.publish_message(request))
    assert first.accepted and second.accepted
    assert len(adapter.published) == 1


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("website", "NEW"),
        ("spam", "REJECTED_SPAM"),
        ("do_not_contact", "DO_NOT_CONTACT"),
        ("irrelevant", "REJECTED_IRRELEVANT"),
    ],
)
def test_lead_source_scenarios(scenario: str, expected: str):
    lead = MockLeadSourceAdapter().discover(scenario)
    assert lead.scenario == scenario
    assert lead.raw_text
