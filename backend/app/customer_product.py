"""Stage 4 customer-facing commercial boundary.

The module deliberately presents business language and keeps Hunter's internal
source, score, and model machinery behind a small product API.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, ClassVar, Protocol

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user
from .db import get_db
from .hunter.universal import BusinessInput, BusinessUnderstandingEngine
from .models import (
    ProductAuditEvent,
    ProductBillingAgreement,
    ProductCampaign,
    ProductCompany,
    ProductEntitlement,
    ProductFounderOverride,
    ProductNotification,
    ProductOpportunity,
    ProductOrganization,
    ProductPayment,
    ProductTeamInvitation,
    ProductTeamMember,
    User,
    Workspace,
    WorkspaceMember,
)
from .security import hash_password


@dataclass(frozen=True)
class PricingPlan:
    code: str
    label: str
    amount: int
    days: int
    commercial_class: str = "STANDARD"


class PricingPolicyV1:
    version: ClassVar[str] = "pricing-policy-v1"
    plans: ClassVar[dict[str, PricingPlan]] = {
        "PAID_TRIAL": PricingPlan("PAID_TRIAL", "Платный пробный период", 25_000, 14),
        "STANDARD_30": PricingPlan("STANDARD_30", "Стандарт · 30 дней", 50_000, 30),
        "STANDARD_90": PricingPlan("STANDARD_90", "Стандарт · 90 дней", 135_000, 90),
        "STANDARD_180": PricingPlan("STANDARD_180", "Стандарт · 180 дней", 255_000, 180),
        "STANDARD_365": PricingPlan("STANDARD_365", "Стандарт · 365 дней", 480_000, 365),
    }
    additional_company_onboarding: ClassVar[int] = 15_000

    @classmethod
    def plan(cls, code: str) -> PricingPlan:
        try:
            return cls.plans[code]
        except KeyError:
            raise ValueError(f"unknown plan: {code}") from None

    @classmethod
    def validate_free_days(cls, days: int) -> None:
        if days < 0 or days > 30:
            raise ValueError("promotional free access is limited to 30 days")


class PaymentProvider(Protocol):
    name: str

    def create_payment(self, amount: int, reference: str) -> str: ...


class ManualPaymentProvider:
    name = "MANUAL_PAYMENT"

    def create_payment(self, amount: int, reference: str) -> str:
        return f"manual:{reference}:{amount}"


PAYMENT_STATES = {"PENDING", "CONFIRMED", "FAILED", "REFUNDED", "CANCELED"}


class RegisterIn(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)


class OnboardingIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = None
    social_url: str | None = None
    description: str = Field(min_length=10, max_length=4000)
    country: str = Field(min_length=2, max_length=80)
    region: str | None = None
    demand: str = Field(min_length=5, max_length=2000)
    commercial_task: str | None = None
    minimum_value: float | None = Field(default=None, ge=0)


class PaymentIn(BaseModel):
    plan_code: str


class OpportunityIn(BaseModel):
    title: str
    summary: str
    need: str
    location: str | None = None
    budget: str | None = None
    appeared_at: datetime
    why_matches: str
    source_url: str | None = None
    dedupe_key: str


class FeedbackIn(BaseModel):
    action: str
    reason: str | None = None


class InviteIn(BaseModel):
    email: str
    role: str = "MEMBER"


class OverrideIn(BaseModel):
    reason: str = Field(min_length=3)
    custom_price: float | None = Field(default=None, ge=0)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    free_days: int = Field(default=0, ge=0, le=30)
    special_duration_days: int | None = Field(default=None, ge=1)
    commercial_class: str | None = None
    expires_at: datetime


def _now() -> datetime:
    return datetime.utcnow()


def _record(db: Session, org_id: str, actor_id: str | None, action: str, entity_type: str, entity_id: str, **details: Any) -> None:
    db.add(ProductAuditEvent(organization_id=org_id, actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id, details=details or None))


def _org(db: Session, user: User) -> ProductOrganization:
    organization = db.scalar(select(ProductOrganization).where(ProductOrganization.workspace_id.in_(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id))))
    if organization is None:
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id).order_by(Workspace.created_at))
        if workspace is None:
            workspace = Workspace(name=f"{user.name} workspace", slug=f"customer-{user.id[:8]}", owner_id=user.id)
            db.add(workspace)
            db.flush()
            db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", joined_at=_now()))
        organization = ProductOrganization(workspace_id=workspace.id, name=workspace.name)
        db.add(organization)
        db.flush()
        _record(db, organization.id, user.id, "organization.created", "Organization", organization.id)
    return organization


def _campaign(db: Session, user: User, campaign_id: str) -> tuple[ProductOrganization, ProductCampaign]:
    organization = _org(db, user)
    campaign = db.scalar(select(ProductCampaign).where(ProductCampaign.id == campaign_id, ProductCampaign.organization_id == organization.id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    member = db.scalar(select(ProductTeamMember).where(ProductTeamMember.campaign_id == campaign.id, ProductTeamMember.user_id == user.id, ProductTeamMember.status == "ACTIVE"))
    workspace_member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == organization.workspace_id, WorkspaceMember.user_id == user.id, WorkspaceMember.status == "ACTIVE"))
    if member is None and workspace_member is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return organization, campaign


def active_entitlement(db: Session, campaign_id: str) -> ProductEntitlement | None:
    now = _now()
    entitlement = db.scalar(select(ProductEntitlement).where(ProductEntitlement.campaign_id == campaign_id, ProductEntitlement.status == "ACTIVE", ProductEntitlement.starts_at <= now, ProductEntitlement.expires_at > now).order_by(ProductEntitlement.expires_at.desc()))
    if entitlement is None:
        campaign = db.get(ProductCampaign, campaign_id)
        if campaign and campaign.status == "ACTIVE":
            campaign.status = "EXPIRED"
    return entitlement


def onboard(db: Session, user: User, payload: OnboardingIn) -> dict[str, Any]:
    organization = _org(db, user)
    company = ProductCompany(organization_id=organization.id, name=payload.name, website=payload.website, social_url=payload.social_url, description=payload.description, country=payload.country, region=payload.region, customer_demand=payload.demand)
    db.add(company)
    db.flush()
    engine = BusinessUnderstandingEngine()
    result = engine.understand(BusinessInput(company_name=payload.name, website=payload.website, public_social_links=(payload.social_url,) if payload.social_url else (), business_description=payload.description, service_description=payload.demand, country=payload.country, region=payload.region, known_minimum_order=payload.minimum_value))
    summary = {
        "what_we_sell": list(result.business_model.services.value or result.business_model.products.value),
        "who_we_seek": list(result.buyer_models[0].buyer_types) if result.buyer_models else ["potential customers"],
        "where": list(result.business_model.geographies.value),
        "priorities": list(result.demand_model.commercial_events),
        "clarifications": [question.text for question in result.clarification_questions][:5],
    }
    company.business_model = {"summary": summary, "policy_status": result.policy_decision.status}
    campaign = ProductCampaign(organization_id=organization.id, company_id=company.id, name=f"{payload.name} · {payload.commercial_task or payload.demand[:60]}", commercial_task=payload.commercial_task or payload.demand, geography=payload.region or payload.country, minimum_value=payload.minimum_value, model_summary=summary, policy_status=result.policy_decision.status, status="DRAFT", feedback={"model_confirmed": False})
    db.add(campaign)
    db.flush()
    team = ProductTeamMember(organization_id=organization.id, company_id=company.id, campaign_id=campaign.id, user_id=user.id, role="ORGANIZATION_OWNER")
    db.add(team)
    _record(db, organization.id, user.id, "company.created", "Company", company.id)
    _record(db, organization.id, user.id, "campaign.created", "Campaign", campaign.id, policy_status=campaign.policy_status)
    db.commit()
    return campaign_view(company, campaign, None)


def campaign_view(company: ProductCompany, campaign: ProductCampaign, entitlement: ProductEntitlement | None) -> dict[str, Any]:
    return {"id": campaign.id, "company": company.name, "name": campaign.name, "task": campaign.commercial_task, "geography": campaign.geography, "understanding": campaign.model_summary, "model_confirmed": bool((campaign.feedback or {}).get("model_confirmed")), "status": campaign.status, "access_until": entitlement.expires_at.isoformat() if entitlement else None}


def confirm_model(db: Session, user: User, campaign_id: str) -> dict[str, Any]:
    organization, campaign = _campaign(db, user, campaign_id)
    if campaign.policy_status == "PROHIBITED":
        raise HTTPException(status_code=422, detail="This campaign cannot be activated")
    campaign.feedback = {**(campaign.feedback or {}), "model_confirmed": True, "confirmed_at": _now().isoformat()}
    _record(db, organization.id, user.id, "campaign.model_confirmed", "Campaign", campaign.id)
    db.commit()
    return campaign_view(db.get(ProductCompany, campaign.company_id), campaign, active_entitlement(db, campaign.id))


def create_payment(db: Session, user: User, campaign_id: str, plan_code: str) -> dict[str, Any]:
    organization, campaign = _campaign(db, user, campaign_id)
    plan = PricingPolicyV1.plan(plan_code)
    company = db.get(ProductCompany, campaign.company_id)
    if plan_code == "PAID_TRIAL" and company and company.trial_used_at is not None:
        raise HTTPException(status_code=409, detail="Paid trial already used for this company")
    if campaign.policy_status == "PROHIBITED":
        raise HTTPException(status_code=422, detail="This campaign cannot be activated")
    if not (campaign.feedback or {}).get("model_confirmed"):
        raise HTTPException(status_code=409, detail="Please confirm the business understanding first")
    has_other_company = db.scalar(select(ProductCompany.id).where(ProductCompany.organization_id == organization.id, ProductCompany.id != campaign.company_id)) is not None
    onboarding_fee = PricingPolicyV1.additional_company_onboarding if has_other_company else 0
    total = plan.amount + onboarding_fee
    payment = ProductPayment(organization_id=organization.id, campaign_id=campaign.id, amount=total, plan_code=plan.code, external_reference=ManualPaymentProvider().create_payment(total, campaign.id))
    db.add(payment)
    campaign.status = "AWAITING_PAYMENT"
    _record(db, organization.id, user.id, "pricing.selected", "Campaign", campaign.id, plan=plan.code, amount=plan.amount)
    db.commit()
    return {"payment_id": payment.id, "state": payment.state, "amount": payment.amount, "onboarding_fee": onboarding_fee, "currency": payment.currency, "plan": plan.label, "days": plan.days}


def confirm_payment(db: Session, user: User, payment_id: str) -> dict[str, Any]:
    organization = _org(db, user)
    payment = db.scalar(select(ProductPayment).where(ProductPayment.id == payment_id, ProductPayment.organization_id == organization.id))
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.state == "CONFIRMED":
        entitlement = db.scalar(select(ProductEntitlement).where(ProductEntitlement.billing_agreement_id == db.scalar(select(ProductBillingAgreement.id).where(ProductBillingAgreement.payment_id == payment.id))))
        return {"payment": payment.id, "state": payment.state, "entitlement": entitlement.id if entitlement else None}
    if payment.state != "PENDING":
        raise HTTPException(status_code=409, detail="Payment is not confirmable")
    plan = PricingPolicyV1.plan(payment.plan_code)
    now = _now()
    payment.state = "CONFIRMED"
    payment.confirmed_at = now
    agreement = ProductBillingAgreement(organization_id=organization.id, campaign_id=payment.campaign_id, payment_id=payment.id, commercial_class=plan.commercial_class)
    db.add(agreement)
    db.flush()
    entitlement = ProductEntitlement(organization_id=organization.id, company_id=db.get(ProductCampaign, payment.campaign_id).company_id, campaign_id=payment.campaign_id, billing_agreement_id=agreement.id, starts_at=now, expires_at=now + timedelta(days=plan.days), plan_code=plan.code, amount_paid=payment.amount)
    db.add(entitlement)
    campaign = db.get(ProductCampaign, payment.campaign_id)
    was_expired = campaign.status == "EXPIRED"
    campaign.status = "ACTIVE"
    company = db.get(ProductCompany, campaign.company_id)
    if payment.plan_code == "PAID_TRIAL":
        company.trial_used_at = now
        company.trial_campaign_id = campaign.id
    db.add(ProductNotification(organization_id=organization.id, campaign_id=campaign.id, user_id=user.id, title="Кампания активирована", body=f"Hunter будет присылать новые возможности до {entitlement.expires_at:%d.%m.%Y}."))
    _record(db, organization.id, user.id, "payment.confirmed", "Payment", payment.id)
    _record(db, organization.id, user.id, "entitlement.issued", "Entitlement", entitlement.id, expires_at=entitlement.expires_at.isoformat())
    if was_expired:
        _record(db, organization.id, user.id, "campaign.renewed", "Campaign", campaign.id)
    db.commit()
    return {"payment": payment.id, "state": payment.state, "entitlement": entitlement.id, "access_until": entitlement.expires_at.isoformat()}


def set_payment_state(db: Session, payment_id: str, state: str) -> ProductPayment:
    if state not in PAYMENT_STATES:
        raise ValueError(f"unsupported payment state: {state}")
    payment = db.get(ProductPayment, payment_id)
    if payment is None:
        raise ValueError("payment not found")
    if payment.state == "CONFIRMED" and state != "CONFIRMED":
        raise ValueError("confirmed payment cannot be changed without a refund workflow")
    payment.state = state
    db.commit()
    return payment


def expire_entitlements(db: Session) -> int:
    now = _now()
    rows = list(db.scalars(select(ProductEntitlement).where(ProductEntitlement.status == "ACTIVE", ProductEntitlement.expires_at <= now)).all())
    for entitlement in rows:
        entitlement.status = "EXPIRED"
        campaign = db.get(ProductCampaign, entitlement.campaign_id)
        if campaign:
            campaign.status = "EXPIRED"
            _record(db, entitlement.organization_id, None, "entitlement.expired", "Entitlement", entitlement.id)
    db.commit()
    return len(rows)


def opportunity_view(opportunity: ProductOpportunity) -> dict[str, Any]:
    return {"id": opportunity.id, "title": opportunity.title, "summary": opportunity.summary, "need": opportunity.need, "location": opportunity.location, "budget": opportunity.budget, "appeared_at": opportunity.appeared_at.isoformat(), "freshness": max(0, int((_now() - opportunity.appeared_at).total_seconds() / 3600)), "why_matches": opportunity.why_matches, "source_url": opportunity.source_url, "status": opportunity.status}


router = APIRouter(prefix="/api/customer", tags=["customer-product"])


@router.post("/onboarding")
def create_onboarding(payload: OnboardingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return onboard(db, user, payload)


@router.post("/campaigns/{campaign_id}/confirm")
def confirm_campaign_model(campaign_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return confirm_model(db, user, campaign_id)


@router.post("/account", status_code=201)
def create_account(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())) is not None:
        raise HTTPException(status_code=409, detail="Account already exists")
    user = User(email=payload.email.lower(), name=payload.name, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    workspace = Workspace(name=payload.organization_name, slug=f"customer-{user.id[:8]}", owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", joined_at=_now()))
    organization = ProductOrganization(workspace_id=workspace.id, name=payload.organization_name)
    db.add(organization)
    db.flush()
    db.add(ProductAuditEvent(organization_id=organization.id, actor_id=user.id, action="organization.created", entity_type="Organization", entity_id=organization.id))
    db.commit()
    return {"user_id": user.id, "organization_id": organization.id, "workspace_id": workspace.id}


@router.get("/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization = _org(db, user)
    expire_entitlements(db)
    campaigns = list(db.scalars(select(ProductCampaign).where(ProductCampaign.organization_id == organization.id).order_by(ProductCampaign.created_at.desc())).all())
    result = []
    for campaign in campaigns:
        company = db.get(ProductCompany, campaign.company_id)
        entitlement = active_entitlement(db, campaign.id)
        result.append(campaign_view(company, campaign, entitlement))
    new_count = len(list(db.scalars(select(ProductOpportunity).where(ProductOpportunity.organization_id == organization.id, ProductOpportunity.status == "NEW")).all()))
    return {"organization": organization.name, "campaigns": result, "new_opportunities": new_count, "in_work": len(list(db.scalars(select(ProductOpportunity).where(ProductOpportunity.organization_id == organization.id, ProductOpportunity.status == "TAKEN")).all())), "skipped": len(list(db.scalars(select(ProductOpportunity).where(ProductOpportunity.organization_id == organization.id, ProductOpportunity.status == "SKIPPED")).all()))}


@router.get("/campaigns/{campaign_id}/opportunities")
def feed(campaign_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _organization, campaign = _campaign(db, user, campaign_id)
    if active_entitlement(db, campaign.id) is None:
        db.commit()
        return {"campaign": campaign_view(db.get(ProductCompany, campaign.company_id), campaign, None), "opportunities": [], "service": "expired"}
    rows = db.scalars(select(ProductOpportunity).where(ProductOpportunity.campaign_id == campaign.id).order_by(ProductOpportunity.appeared_at.desc())).all()
    return {"campaign": campaign_view(db.get(ProductCompany, campaign.company_id), campaign, active_entitlement(db, campaign.id)), "opportunities": [opportunity_view(row) for row in rows]}


@router.post("/campaigns/{campaign_id}/payments")
def payment(campaign_id: str, payload: PaymentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return create_payment(db, user, campaign_id, payload.plan_code)


@router.post("/payments/{payment_id}/confirm")
def confirm(payment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return confirm_payment(db, user, payment_id)


@router.post("/opportunities/{opportunity_id}/feedback")
def feedback(opportunity_id: str, payload: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    opportunity = db.get(ProductOpportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    _, campaign = _campaign(db, user, opportunity.campaign_id)
    if active_entitlement(db, campaign.id) is None:
        raise HTTPException(status_code=403, detail="Campaign access has expired")
    if payload.action not in {"TAKE", "SKIP"}:
        raise HTTPException(status_code=422, detail="Action must be TAKE or SKIP")
    opportunity.status = "TAKEN" if payload.action == "TAKE" else "SKIPPED"
    opportunity.feedback_reason = payload.reason
    opportunity.acted_by = user.id
    opportunity.acted_at = _now()
    _record(db, opportunity.organization_id, user.id, f"opportunity.{payload.action.lower()}", "Opportunity", opportunity.id, reason=payload.reason)
    db.commit()
    return opportunity_view(opportunity)


@router.post("/campaigns/{campaign_id}/opportunities")
def add_opportunity(campaign_id: str, payload: OpportunityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization, campaign = _campaign(db, user, campaign_id)
    if active_entitlement(db, campaign.id) is None:
        raise HTTPException(status_code=403, detail="Campaign access has expired")
    opportunity = ProductOpportunity(organization_id=organization.id, company_id=campaign.company_id, campaign_id=campaign.id, **payload.model_dump())
    db.add(opportunity)
    db.add(ProductNotification(organization_id=organization.id, campaign_id=campaign.id, user_id=user.id, title="Новая возможность", body=payload.title))
    db.commit()
    return opportunity_view(opportunity)


@router.post("/campaigns/{campaign_id}/invite")
def invite(campaign_id: str, payload: InviteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization, campaign = _campaign(db, user, campaign_id)
    member = db.scalar(select(ProductTeamMember).where(ProductTeamMember.campaign_id == campaign.id, ProductTeamMember.user_id == user.id, ProductTeamMember.status == "ACTIVE"))
    if member and member.role not in {"ORGANIZATION_OWNER", "COMPANY_ADMIN", "CAMPAIGN_MANAGER"}:
        raise HTTPException(status_code=403, detail="Team invitation permission required")
    if payload.role not in {"COMPANY_ADMIN", "CAMPAIGN_MANAGER", "MEMBER", "VIEWER"}:
        raise HTTPException(status_code=422, detail="Unsupported team role")
    raw_token = secrets.token_urlsafe(24)
    invitation = ProductTeamInvitation(organization_id=organization.id, company_id=campaign.company_id, campaign_id=campaign.id, email=payload.email.lower(), role=payload.role, token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), expires_at=_now() + timedelta(days=7))
    db.add(invitation)
    _record(db, organization.id, user.id, "team.invitation", "Campaign", campaign.id, email=payload.email.lower(), role=payload.role)
    db.commit()
    return {"invitation_id": invitation.id, "email": invitation.email, "role": invitation.role, "expires_at": invitation.expires_at.isoformat()}


@router.post("/campaigns/{campaign_id}/founder-override")
def founder_override(campaign_id: str, payload: OverrideIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization, campaign = _campaign(db, user, campaign_id)
    workspace_member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == organization.workspace_id, WorkspaceMember.user_id == user.id, WorkspaceMember.status == "ACTIVE"))
    if workspace_member is None or workspace_member.role not in {"OWNER", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Founder override requires organization administration")
    if payload.free_days > 30:
        raise HTTPException(status_code=422, detail="Free period cannot exceed 30 days")
    override = ProductFounderOverride(organization_id=organization.id, campaign_id=campaign.id, granted_by=user.id, starts_at=_now(), **payload.model_dump())
    db.add(override)
    _record(db, organization.id, user.id, "founder.override", "Campaign", campaign.id, reason=payload.reason)
    db.commit()
    return {"override_id": override.id, "audited": True}
