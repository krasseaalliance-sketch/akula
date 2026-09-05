from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.customer_product import PricingPolicyV1, active_entitlement, onboard, confirm_model, create_payment, confirm_payment, expire_entitlements, set_payment_state
from app.models import Base, ProductCampaign, ProductOpportunity, User, Workspace, WorkspaceMember
from app.security import hash_password


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def workspace_user(db):
    user = User(email="stage4@example.local", name="Stage 4", password_hash=hash_password("secret"))
    db.add(user)
    db.flush()
    workspace = Workspace(name="Stage 4", slug="stage-4", owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    db.commit()
    return workspace, user


def onboarding_payload(name: str, demand: str = "Нужны новые клиенты на услуги"):
    from app.customer_product import OnboardingIn
    return OnboardingIn(name=name, description=f"Компания {name} оказывает услуги клиентам", country="Россия", region="Красноярск", demand=demand)


def test_pricing_policy_v1_is_explicit_and_no_free_forever():
    assert PricingPolicyV1.plan("PAID_TRIAL").amount == 25_000
    assert PricingPolicyV1.plan("PAID_TRIAL").days == 14
    assert [PricingPolicyV1.plan(code).amount for code in ("STANDARD_30", "STANDARD_90", "STANDARD_180", "STANDARD_365")] == [50_000, 135_000, 255_000, 480_000]
    assert PricingPolicyV1.additional_company_onboarding == 15_000
    with pytest.raises(ValueError):
        PricingPolicyV1.validate_free_days(31)


def test_payment_states_include_pending_and_failed(db, workspace_user):
    _workspace, user = workspace_user
    result = onboard(db, user, onboarding_payload("State Check"))
    confirm_model(db, user, result["id"])
    payment = create_payment(db, user, result["id"], "STANDARD_30")
    failed = set_payment_state(db, payment["payment_id"], "FAILED")
    assert failed.state == "FAILED"


def test_onboarding_payment_entitlement_and_expiration(db, workspace_user):
    _workspace, user = workspace_user
    result = onboard(db, user, onboarding_payload("Vitrina", "Нужны клиенты на создание сайтов"))
    confirm_model(db, user, result["id"])
    payment = create_payment(db, user, result["id"], "PAID_TRIAL")
    assert payment["state"] == "PENDING"
    confirmed = confirm_payment(db, user, payment["payment_id"])
    assert confirmed["state"] == "CONFIRMED"
    entitlement = active_entitlement(db, result["id"])
    assert entitlement is not None
    entitlement.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    assert expire_entitlements(db) == 1
    assert active_entitlement(db, result["id"]) is None
    renewal = create_payment(db, user, result["id"], "STANDARD_30")
    confirm_payment(db, user, renewal["payment_id"])
    assert active_entitlement(db, result["id"]) is not None


def test_one_company_one_coherent_task_and_second_company_isolated(db, workspace_user):
    _workspace, user = workspace_user
    first = onboard(db, user, onboarding_payload("Vitrina", "Создание сайтов для бизнеса"))
    second = onboard(db, user, onboarding_payload("North Industrial", "Поставка промышленного оборудования"))
    assert first["id"] != second["id"]
    assert first["company"] != second["company"]
    confirm_model(db, user, first["id"])
    first_payment = create_payment(db, user, first["id"], "STANDARD_30")
    confirm_payment(db, user, first_payment["payment_id"])
    campaign = db.get(ProductCampaign, first["id"])
    opportunity = ProductOpportunity(organization_id=campaign.organization_id, company_id=campaign.company_id, campaign_id=first["id"], dedupe_key="e2e-1", title="Нужен сайт", summary="Компания ищет подрядчика", need="Сайт для нового продукта", location="Красноярск", budget="от 100 000 ₽", appeared_at=datetime.utcnow(), why_matches="Подходит по услуге и географии")
    db.add(opportunity)
    db.commit()
    assert active_entitlement(db, second["id"]) is None
    assert opportunity.campaign_id == first["id"]


@pytest.mark.parametrize(
    "name,demand",
    [
        ("Vitrina", "Нужны клиенты на создание сайтов"),
        ("Bali Excursions", "Нужны туристы на экскурсии на Бали"),
        ("Bright Dental", "Нужны пациенты на стоматологические услуги"),
        ("Urban Estate", "Нужны собственники и покупатели недвижимости"),
        ("North Industrial", "Нужны корпоративные заказчики оборудования"),
    ],
)
def test_five_businesses_use_the_same_generic_customer_flow(db, workspace_user, name, demand):
    _workspace, user = workspace_user
    result = onboard(db, user, onboarding_payload(name, demand))
    confirm_model(db, user, result["id"])
    payment = create_payment(db, user, result["id"], "STANDARD_30")
    confirmed = confirm_payment(db, user, payment["payment_id"])
    assert confirmed["state"] == "CONFIRMED"
    assert active_entitlement(db, result["id"]) is not None
