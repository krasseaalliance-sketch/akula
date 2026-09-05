from app.policy import PolicyEngine


def test_unapproved_message_is_denied():
    result = PolicyEngine().can_publish(
        safety_lock=False,
        campaign_status="ACTIVE",
        message_approved=False,
        community_status="APPROVED",
        sent_today=0,
        daily_limit=50,
    )
    assert result.allowed is False
    assert result.code == "MESSAGE_NOT_APPROVED"


def test_daily_limit_and_safety_lock_are_denied():
    engine = PolicyEngine()
    assert (
        engine.can_publish(
            safety_lock=False,
            campaign_status="ACTIVE",
            message_approved=True,
            community_status="APPROVED",
            sent_today=50,
            daily_limit=50,
        ).code
        == "DAILY_LIMIT_REACHED"
    )
    assert (
        engine.can_publish(
            safety_lock=True,
            campaign_status="ACTIVE",
            message_approved=True,
            community_status="APPROVED",
            sent_today=0,
            daily_limit=50,
        ).code
        == "SAFETY_LOCK"
    )
