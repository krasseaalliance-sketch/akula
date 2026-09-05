from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .enum_values import CHECKS, sql_check


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Workspace(Timestamped, Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Krasnoyarsk")
    default_language: Mapped[str] = mapped_column(String(16), default="ru")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="VIEWER")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    invited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Company(Timestamped, Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    public_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Krasnoyarsk")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class Brand(Timestamped, Base):
    __tablename__ = "brands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    positioning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone_of_voice: Mapped[str | None] = mapped_column(String(120), nullable=True)
    visual_identity: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    default_language: Mapped[str] = mapped_column(String(16), default="ru")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class Offer(Timestamped, Base):
    __tablename__ = "offers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(48), default="OTHER")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(String(160), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class Campaign(Timestamped, Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    offer_id: Mapped[str | None] = mapped_column(ForeignKey("offers.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(String(500), default="Lead discovery")
    geography: Mapped[str | None] = mapped_column(String(160), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="ru")
    daily_limit: Mapped[int] = mapped_column(Integer, default=50)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    campaign_type: Mapped[str] = mapped_column(String(64), default="LEAD_DISCOVERY")
    publication_policy: Mapped[str] = mapped_column(String(32), default="APPROVAL_REQUIRED")
    communication_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


# Stage 4 customer-product entities intentionally live beside, but do not replace,
# the internal operations entities above.  This keeps the customer boundary explicit.
class ProductOrganization(Timestamped, Base):
    __tablename__ = "product_organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ProductCompany(Timestamped, Base):
    __tablename__ = "product_companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_demand: Mapped[str] = mapped_column(Text)
    business_model: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trial_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ProductCampaign(Timestamped, Base):
    __tablename__ = "product_campaigns"
    __table_args__ = (UniqueConstraint("company_id", "commercial_task"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("product_companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    commercial_task: Mapped[str] = mapped_column(Text)
    geography: Mapped[str] = mapped_column(String(200))
    minimum_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(120), default="stage3-v1")
    policy_status: Mapped[str] = mapped_column(String(40), default="ALLOWED")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ProductTeamMember(Timestamped, Base):
    __tablename__ = "product_team_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "campaign_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("product_companies.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="MEMBER")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ProductTeamInvitation(Timestamped, Base):
    __tablename__ = "product_team_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("product_companies.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(32), default="MEMBER")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductPayment(Timestamped, Base):
    __tablename__ = "product_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    plan_code: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40), default="MANUAL_PAYMENT")
    state: Mapped[str] = mapped_column(String(32), default="PENDING")
    external_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductBillingAgreement(Timestamped, Base):
    __tablename__ = "product_billing_agreements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("product_payments.id"), index=True)
    contract_type: Mapped[str] = mapped_column(String(40), default="FIXED")
    commercial_class: Mapped[str] = mapped_column(String(32), default="STANDARD")
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductEntitlement(Timestamped, Base):
    __tablename__ = "product_entitlements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("product_companies.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    billing_agreement_id: Mapped[str] = mapped_column(ForeignKey("product_billing_agreements.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    plan_code: Mapped[str] = mapped_column(String(40))
    amount_paid: Mapped[float] = mapped_column(Float)


class ProductPromotion(Timestamped, Base):
    __tablename__ = "product_promotions"
    __table_args__ = (CheckConstraint("free_days >= 0 AND free_days <= 30", name="ck_product_promotions_free_days"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float, default=0)
    free_days: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductFounderOverride(Timestamped, Base):
    __tablename__ = "product_founder_overrides"
    __table_args__ = (CheckConstraint("free_days >= 0 AND free_days <= 30", name="ck_product_founder_free_days"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    granted_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    custom_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_days: Mapped[int] = mapped_column(Integer, default=0)
    special_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commercial_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ProductOpportunity(Timestamped, Base):
    __tablename__ = "product_opportunities"
    __table_args__ = (UniqueConstraint("campaign_id", "dedupe_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("product_companies.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    need: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    budget: Mapped[str | None] = mapped_column(String(160), nullable=True)
    appeared_at: Mapped[datetime] = mapped_column(DateTime)
    source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    why_matches: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="NEW")
    feedback_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    acted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductNotification(Timestamped, Base):
    __tablename__ = "product_notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("product_campaigns.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="IN_APP")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SupportThread(Timestamped, Base):
    __tablename__ = "support_threads"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", "campaign_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("product_campaigns.id"), nullable=True, index=True)
    topic_title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telegram_thread_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SupportMessage(Timestamped, Base):
    __tablename__ = "support_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(ForeignKey("support_threads.id"), index=True)
    sender_type: Mapped[str] = mapped_column(String(32), default="CUSTOMER")
    sender_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    telegram_status: Mapped[str] = mapped_column(String(40), default="NOT_CONFIGURED")
    telegram_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telegram_error: Mapped[str | None] = mapped_column(String(240), nullable=True)


class ProductAuditEvent(Timestamped, Base):
    __tablename__ = "product_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("product_organizations.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Audience(Timestamped, Base):
    __tablename__ = "audiences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    criteria: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class CampaignAudienceProfile(Timestamped, Base):
    __tablename__ = "campaign_audience_profiles"
    __table_args__ = (UniqueConstraint("campaign_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    audience_id: Mapped[str | None] = mapped_column(ForeignKey("audiences.id"), nullable=True, index=True)
    offer_summary: Mapped[str] = mapped_column(Text)
    audience_summary: Mapped[str] = mapped_column(Text)
    audience_segments: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    intent_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    exclusions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    geographies: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    languages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    platforms: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    goal: Mapped[str] = mapped_column(String(120), default="Получить заявки")
    budget: Mapped[float] = mapped_column(Float, default=0)
    profile_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="campaign-audience-rules-v1")
    status: Mapped[str] = mapped_column(String(32), default="READY")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Community(Timestamped, Base):
    __tablename__ = "communities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="TELEGRAM")
    external_id: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="ru")
    geography: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    activity_score: Mapped[float] = mapped_column(Float, default=0)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    rules_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    posting_status: Mapped[str] = mapped_column(String(40), default="NEEDS_REVIEW")
    rules_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    allowed_content_types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allowed_days: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    min_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    community_score: Mapped[float] = mapped_column(Float, default=0)
    lead_quality_score: Mapped[float] = mapped_column(Float, default=0)
    conversion_rate: Mapped[float] = mapped_column(Float, default=0)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ai_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    classification_status: Mapped[str] = mapped_column(String(32), default="NEEDS_REVIEW")
    classification_source: Mapped[str] = mapped_column(String(32), default="PENDING_MANUAL_TRIAGE")
    manual_classification_override: Mapped[bool] = mapped_column(Boolean, default=False)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CommunityCollection(Timestamped, Base):
    __tablename__ = "community_collections"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("community_collections.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(32), default="SYSTEM")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)


class CommunityCollectionMembership(Timestamped, Base):
    __tablename__ = "community_collection_memberships"
    __table_args__ = (UniqueConstraint("collection_id", "community_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    collection_id: Mapped[str] = mapped_column(ForeignKey("community_collections.id"), index=True)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    assignment_source: Mapped[str] = mapped_column(String(32), default="AUTO")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class CommunityTag(Timestamped, Base):
    __tablename__ = "community_tags"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140))
    source: Mapped[str] = mapped_column(String(32), default="AI")


class CommunityTagMembership(Timestamped, Base):
    __tablename__ = "community_tag_memberships"
    __table_args__ = (UniqueConstraint("tag_id", "community_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tag_id: Mapped[str] = mapped_column(ForeignKey("community_tags.id"), index=True)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    assignment_source: Mapped[str] = mapped_column(String(32), default="AI")
    confidence: Mapped[float] = mapped_column(Float, default=0)


class CampaignIntelligenceRun(Timestamped, Base):
    __tablename__ = "campaign_intelligence_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    audience_profile_id: Mapped[str | None] = mapped_column(ForeignKey("campaign_audience_profiles.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="campaign-intelligence-rules-v1")
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    discovered_communities: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_communities: Mapped[int] = mapped_column(Integer, default=0)
    recommended_communities: Mapped[int] = mapped_column(Integer, default=0)
    average_score: Mapped[float] = mapped_column(Float, default=0)
    projected_reach: Mapped[int] = mapped_column(Integer, default=0)
    ai_cost: Mapped[float] = mapped_column(Float, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class CampaignCommunityScore(Timestamped, Base):
    __tablename__ = "campaign_community_scores"
    __table_args__ = (UniqueConstraint("campaign_id", "community_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("campaign_intelligence_runs.id"), nullable=True, index=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    audience_match_score: Mapped[float] = mapped_column(Float, default=0)
    activity_score: Mapped[float] = mapped_column(Float, default=0)
    posting_permission_score: Mapped[float] = mapped_column(Float, default=0)
    commercial_risk_score: Mapped[float] = mapped_column(Float, default=0)
    spam_risk_score: Mapped[float] = mapped_column(Float, default=0)
    expected_response_score: Mapped[float] = mapped_column(Float, default=0)
    community_score: Mapped[float] = mapped_column(Float, default=0)
    lead_probability: Mapped[float] = mapped_column(Float, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    recommendation: Mapped[str] = mapped_column(String(32), default="REVIEW")
    recommendation_reason: Mapped[str] = mapped_column(Text, default="Requires operator review")
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    collection_slugs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="campaign-scoring-rules-v1")
    status: Mapped[str] = mapped_column(String(32), default="ANALYZED")


class CampaignCostRecord(Timestamped, Base):
    __tablename__ = "campaign_cost_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("campaign_intelligence_runs.id"), nullable=True, index=True)
    cost_type: Mapped[str] = mapped_column(String(48))
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CampaignLearningSnapshot(Timestamped, Base):
    __tablename__ = "campaign_learning_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    analyzed_leads: Mapped[int] = mapped_column(Integer, default=0)
    responses: Mapped[int] = mapped_column(Integer, default=0)
    qualified_leads: Mapped[int] = mapped_column(Integer, default=0)
    converted_leads: Mapped[int] = mapped_column(Integer, default=0)
    publications: Mapped[int] = mapped_column(Integer, default=0)
    successful_publications: Mapped[int] = mapped_column(Integer, default=0)
    best_community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True)
    best_message_draft_id: Mapped[str | None] = mapped_column(ForeignKey("message_drafts.id"), nullable=True)
    learning_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class CommunityPermission(Timestamped, Base):
    __tablename__ = "community_permissions"
    __table_args__ = (UniqueConstraint("community_id", "workspace_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    permission_type: Mapped[str] = mapped_column(String(48), default="POST")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    allowed_content_types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allowed_days: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    min_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Lead(Timestamped, Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    source_platform: Mapped[str] = mapped_column(String(32), default="TELEGRAM")
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_dialog_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_message_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_community_id: Mapped[str | None] = mapped_column(
        ForeignKey("communities.id"), nullable=True
    )
    author_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    author_username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_need: Mapped[str | None] = mapped_column(String(300), nullable=True)
    lead_type: Mapped[str] = mapped_column(String(64), default="INBOUND")
    score: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="NEW")
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    matched_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    excluded_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    can_reply_publicly: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_initiated: Mapped[bool] = mapped_column(Boolean, default=False)
    direct_message_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pain: Mapped[str | None] = mapped_column(String(300), nullable=True)
    need: Mapped[str | None] = mapped_column(String(300), nullable=True)
    intent_confidence: Mapped[float] = mapped_column(Float, default=0)
    pain_confidence: Mapped[float] = mapped_column(Float, default=0)
    need_confidence: Mapped[float] = mapped_column(Float, default=0)
    offer_match_id: Mapped[str | None] = mapped_column(ForeignKey("offers.id"), nullable=True, index=True)
    offer_match_score: Mapped[float] = mapped_column(Float, default=0)
    first_contact_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MessageDraft(Timestamped, Base):
    __tablename__ = "message_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    audience_id: Mapped[str | None] = mapped_column(ForeignKey("audiences.id"), nullable=True)
    message_type: Mapped[str] = mapped_column(String(48), default="DIRECT_RESPONSE")
    publication_type: Mapped[str] = mapped_column(String(64), default="OTHER")
    language: Mapped[str] = mapped_column(String(16), default="ru")
    content: Mapped[str] = mapped_column(Text)
    facts_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    generation_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120), default="mock-template-v1")
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="VALID")
    approval_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    human_writing_run_id: Mapped[str | None] = mapped_column(ForeignKey("human_writing_runs.id"), nullable=True, index=True)
    human_variant_id: Mapped[str | None] = mapped_column(ForeignKey("human_writing_variants.id"), nullable=True, index=True)
    naturalness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_critic: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CommunityStyleProfile(Timestamped, Base):
    __tablename__ = "community_style_profiles"
    __table_args__ = (UniqueConstraint("community_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    average_message_length: Mapped[float] = mapped_column(Float, default=0)
    average_paragraphs: Mapped[float] = mapped_column(Float, default=1)
    emoji_rate: Mapped[float] = mapped_column(Float, default=0)
    greeting_rate: Mapped[float] = mapped_column(Float, default=0)
    question_rate: Mapped[float] = mapped_column(Float, default=0)
    abbreviation_rate: Mapped[float] = mapped_column(Float, default=0)
    english_rate: Mapped[float] = mapped_column(Float, default=0)
    slang_rate: Mapped[float] = mapped_column(Float, default=0)
    directness_score: Mapped[float] = mapped_column(Float, default=0.5)
    emotion_score: Mapped[float] = mapped_column(Float, default=0.5)
    dominant_language: Mapped[str] = mapped_column(String(16), default="ru")
    preferred_persona_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    style_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_message_count: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HumanWritingRun(Timestamped, Base):
    __tablename__ = "human_writing_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    persona_id: Mapped[str] = mapped_column(String(80))
    style_profile_id: Mapped[str | None] = mapped_column(ForeignKey("community_style_profiles.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="human-writing-rules-v1")
    status: Mapped[str] = mapped_column(String(32), default="SUCCEEDED")
    naturalness_score: Mapped[float] = mapped_column(Float, default=0)
    selected_variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    simulator_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    critic_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    structure_memory_key: Mapped[str | None] = mapped_column(String(160), nullable=True)


class HumanWritingVariant(Timestamped, Base):
    __tablename__ = "human_writing_variants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("human_writing_runs.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True, index=True)
    variant_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    opening: Mapped[str] = mapped_column(String(500))
    ending: Mapped[str] = mapped_column(String(500))
    structure: Mapped[list[str]] = mapped_column(JSON)
    structure_key: Mapped[str] = mapped_column(String(240), index=True)
    naturalness_score: Mapped[float] = mapped_column(Float, default=0)
    similarity_score: Mapped[float] = mapped_column(Float, default=0)
    similarity_method: Mapped[str] = mapped_column(String(40), default="TOKEN_COSINE")
    critic_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    critic_reasons: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="human-writing-rules-v1")


class StyleMemory(Timestamped, Base):
    __tablename__ = "human_writing_style_memory"
    __table_args__ = (UniqueConstraint("workspace_id", "community_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True, index=True)
    used_openings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    used_endings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    used_structures: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    rejected_patterns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    accepted_patterns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    operator_preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class StyleEvolutionEvent(Timestamped, Base):
    __tablename__ = "human_writing_style_evolution"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True, index=True)
    variant_id: Mapped[str | None] = mapped_column(ForeignKey("human_writing_variants.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    original_content: Mapped[str] = mapped_column(Text)
    edited_content: Mapped[str] = mapped_column(Text)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Publication(Timestamped, Base):
    __tablename__ = "publications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT")
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)


class PublicationJob(Timestamped, Base):
    __tablename__ = "publication_jobs"
    __table_args__ = (UniqueConstraint("publication_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    correlation_id: Mapped[str] = mapped_column(String(80), default=new_id, index=True)
    trace_id: Mapped[str] = mapped_column(String(80), default=new_id, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Conversation(Timestamped, Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    external_chat_id: Mapped[str] = mapped_column(String(200))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    sender: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IntegrationAccount(Timestamped, Base):
    __tablename__ = "integration_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    display_name: Mapped[str] = mapped_column(String(160))
    external_account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    credential_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DISCONNECTED")
    health_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    safety_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    authorization_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    safety_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    connection_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone_masked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    flood_wait_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36))
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SystemState(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceRuntime(Timestamped, Base):
    __tablename__ = "service_runtimes"
    __table_args__ = (UniqueConstraint("workspace_id", "service_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    service_key: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="STARTING")
    scheduler_name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[str] = mapped_column(String(5))
    window_end: Mapped[str] = mapped_column(String(5))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    today_publications: Mapped[int] = mapped_column(Integer, default=0)
    today_communities: Mapped[int] = mapped_column(Integer, default=0)
    today_leads: Mapped[int] = mapped_column(Integer, default=0)
    today_critical_leads: Mapped[int] = mapped_column(Integer, default=0)
    stats_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    settings_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ServiceLog(Base):
    __tablename__ = "service_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    service_key: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    event: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TelegramAccountProfile(Timestamped, Base):
    __tablename__ = "telegram_account_profiles"
    __table_args__ = (UniqueConstraint("integration_account_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    integration_account_id: Mapped[str] = mapped_column(
        ForeignKey("integration_accounts.id"), index=True
    )
    phone_masked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telegram_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    account_type: Mapped[str] = mapped_column(String(32), default="USER")
    authorization_status: Mapped[str] = mapped_column(String(40), default="NOT_CONFIGURED")
    safety_status: Mapped[str] = mapped_column(String(40), default="DISCONNECTED")
    connection_status: Mapped[str] = mapped_column(String(40), default="DISCONNECTED")
    session_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_credential_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proxy_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    flood_wait_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    restriction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    restriction_detected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    manual_unlock_required: Mapped[bool] = mapped_column(Boolean, default=False)


class TelegramAuthorizationAttempt(Timestamped, Base):
    __tablename__ = "telegram_authorization_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    telegram_account_profile_id: Mapped[str] = mapped_column(
        ForeignKey("telegram_account_profiles.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class TelegramDialog(Timestamped, Base):
    __tablename__ = "telegram_dialogs"
    __table_args__ = (
        UniqueConstraint("integration_account_id", "external_dialog_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    integration_account_id: Mapped[str] = mapped_column(
        ForeignKey("integration_accounts.id"), index=True
    )
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True, index=True)
    external_dialog_id: Mapped[str] = mapped_column(String(200), index=True)
    access_hash_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dialog_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    title: Mapped[str] = mapped_column(String(240))
    username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_joined: Mapped[bool] = mapped_column(Boolean, default=False)
    can_send_messages: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_history: Mapped[bool] = mapped_column(Boolean, default=False)
    has_slow_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    slow_mode_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_message_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_metadata_sanitized: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DialogTriageDecision(Timestamped, Base):
    __tablename__ = "dialog_triage_decisions"
    __table_args__ = (UniqueConstraint("workspace_id", "telegram_account_id", "telegram_dialog_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    telegram_account_id: Mapped[str] = mapped_column(ForeignKey("telegram_account_profiles.id"), index=True)
    telegram_dialog_id: Mapped[str] = mapped_column(ForeignKey("telegram_dialogs.id"), index=True)
    review_status: Mapped[str] = mapped_column(String(40), default="UNREVIEWED", index=True)
    manual_dialog_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    manual_eligibility: Mapped[str] = mapped_column(String(32), default="MANUAL_REVIEW")
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    needs_context_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class DialogTriageCollection(Timestamped, Base):
    __tablename__ = "dialog_triage_collection_definitions"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180))
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class DialogTriageCollectionMembership(Timestamped, Base):
    __tablename__ = "dialog_triage_collections"
    __table_args__ = (UniqueConstraint("decision_id", "collection_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    decision_id: Mapped[str] = mapped_column(ForeignKey("dialog_triage_decisions.id"), index=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("dialog_triage_collection_definitions.id"), index=True)
    assigned_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class DialogTriageTag(Timestamped, Base):
    __tablename__ = "dialog_triage_tag_definitions"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class DialogTriageTagMembership(Timestamped, Base):
    __tablename__ = "dialog_triage_tags"
    __table_args__ = (UniqueConstraint("decision_id", "tag_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    decision_id: Mapped[str] = mapped_column(ForeignKey("dialog_triage_decisions.id"), index=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("dialog_triage_tag_definitions.id"), index=True)
    assigned_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class TelegramCommunitySnapshot(Timestamped, Base):
    __tablename__ = "telegram_community_snapshots"
    __table_args__ = (UniqueConstraint("community_id", "integration_account_id", "metadata_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    integration_account_id: Mapped[str] = mapped_column(ForeignKey("integration_accounts.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rules_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinned_message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    slow_mode_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    can_send_messages: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_history: Mapped[bool] = mapped_column(Boolean, default=False)
    public_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    metadata_hash: Mapped[str] = mapped_column(String(128), index=True)


class TelegramMessageRecord(Timestamped, Base):
    __tablename__ = "telegram_message_records"
    __table_args__ = (UniqueConstraint("integration_account_id", "external_dialog_id", "external_message_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    integration_account_id: Mapped[str] = mapped_column(ForeignKey("integration_accounts.id"), index=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    external_dialog_id: Mapped[str] = mapped_column(String(200), index=True)
    external_message_id: Mapped[str] = mapped_column(String(200), index=True)
    sender_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sender_username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sender_display_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), default="INBOUND")
    message_type: Mapped[str] = mapped_column(String(48), default="TEXT")
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_to_external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    grouped_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entities_sanitized: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    attachments_metadata: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    source: Mapped[str] = mapped_column(String(40), default="MOCK")
    content_hash: Mapped[str] = mapped_column(String(128), index=True)


class TelegramSyncCursor(Timestamped, Base):
    __tablename__ = "telegram_sync_cursors"
    __table_args__ = (UniqueConstraint("integration_account_id", "dialog_id", "sync_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    integration_account_id: Mapped[str] = mapped_column(ForeignKey("integration_accounts.id"), index=True)
    dialog_id: Mapped[str | None] = mapped_column(ForeignKey("telegram_dialogs.id"), nullable=True, index=True)
    sync_type: Mapped[str] = mapped_column(String(32), default="MESSAGES")
    cursor_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TelegramAccountIncident(Timestamped, Base):
    __tablename__ = "telegram_account_incidents"
    __table_args__ = (UniqueConstraint("integration_account_id", "incident_type", "detected_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    integration_account_id: Mapped[str] = mapped_column(ForeignKey("integration_accounts.id"), index=True)
    incident_type: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16), default="WARNING")
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    source: Mapped[str] = mapped_column(String(80), default="MOCK")
    sanitized_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TelegramPublicationResult(Timestamped, Base):
    __tablename__ = "telegram_publication_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id"), index=True)
    integration_account_id: Mapped[str] = mapped_column(ForeignKey("integration_accounts.id"), index=True)
    external_dialog_id: Mapped[str] = mapped_column(String(200), index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result_status: Mapped[str] = mapped_column(String(32), default="DRY_RUN")
    telegram_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_metadata_sanitized: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DiscoveryProfile(Timestamped, Base):
    __tablename__ = "discovery_profiles"
    __table_args__ = (UniqueConstraint("campaign_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    platform: Mapped[str] = mapped_column(String(32), default="TELEGRAM")
    languages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    geography: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    include_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    exclude_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    community_categories: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    intent_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    negative_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    minimum_activity_score: Mapped[float] = mapped_column(Float, default=0)
    minimum_relevance_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class TelegramDiscoveryRun(Timestamped, Base):
    __tablename__ = "telegram_discovery_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    integration_account_id: Mapped[str] = mapped_column(ForeignKey("integration_accounts.id"), index=True)
    discovery_profile_id: Mapped[str | None] = mapped_column(ForeignKey("discovery_profiles.id"), nullable=True)
    search_query: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default="SUCCEEDED")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TelegramCommunityCandidate(Timestamped, Base):
    __tablename__ = "telegram_community_candidates"
    __table_args__ = (UniqueConstraint("workspace_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    discovery_run_id: Mapped[str | None] = mapped_column(ForeignKey("telegram_discovery_runs.id"), nullable=True)
    external_id: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(240))
    username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="MOCK")
    search_query: Mapped[str | None] = mapped_column(String(300), nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    activity_score: Mapped[float] = mapped_column(Float, default=0)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    rank_score: Mapped[float] = mapped_column(Float, default=0)
    rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    join_status: Mapped[str] = mapped_column(String(32), default="NOT_ATTEMPTED")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    join_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(String(160), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="NEW")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TelegramRuleAnalysis(Timestamped, Base):
    __tablename__ = "telegram_rule_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("telegram_community_snapshots.id"), nullable=True)
    advertising_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    companion_search_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    event_posts_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    external_links_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    images_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    hashtags_required: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_placement_required: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_days: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allowed_hours: Mapped[str | None] = mapped_column(String(120), nullable=True)
    minimum_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forbidden_topics: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    required_format: Mapped[str | None] = mapped_column(String(240), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    evidence_fragments: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="PENDING")


class TelegramImportRun(Timestamped, Base):
    __tablename__ = "telegram_import_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    integration_account_id: Mapped[str | None] = mapped_column(ForeignKey("integration_accounts.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(40), default="MANUAL")
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="PREVIEW")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)


class TelegramAttribution(Timestamped, Base):
    __tablename__ = "telegram_attributions"
    __table_args__ = (UniqueConstraint("source_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    community_id: Mapped[str | None] = mapped_column(ForeignKey("communities.id"), nullable=True, index=True)
    publication_id: Mapped[str | None] = mapped_column(ForeignKey("publications.id"), nullable=True, index=True)
    source_code: Mapped[str] = mapped_column(String(120), index=True)
    campaign_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    community_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    quiz_starts: Mapped[int] = mapped_column(Integer, default=0)
    participations: Mapped[int] = mapped_column(Integer, default=0)
    returns: Mapped[int] = mapped_column(Integer, default=0)
    referrals: Mapped[int] = mapped_column(Integer, default=0)


class AISearchProfile(Timestamped, Base):
    __tablename__ = "ai_search_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    natural_language_query: Mapped[str] = mapped_column(Text)
    criteria: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class LeadIntelligenceRun(Timestamped, Base):
    __tablename__ = "lead_intelligence_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(40), default="TELEGRAM")
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="lead-intelligence-rules-v1")
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    total_leads: Mapped[int] = mapped_column(Integer, default=0)
    processed_leads: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LeadIntelligenceAnalysis(Timestamped, Base):
    __tablename__ = "lead_intelligence_analyses"
    __table_args__ = (UniqueConstraint("lead_id", "run_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("lead_intelligence_runs.id"), index=True)
    intent: Mapped[str] = mapped_column(String(120))
    pain: Mapped[str] = mapped_column(String(300))
    need: Mapped[str] = mapped_column(String(300))
    confidence: Mapped[float] = mapped_column(Float, default=0)
    score: Mapped[float] = mapped_column(Float, default=0)
    matched_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    excluded_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="lead-intelligence-rules-v1")


class MessageRecommendation(Timestamped, Base):
    __tablename__ = "message_recommendations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    recommendation: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(40), default="PUBLIC_REPLY")
    reason: Mapped[str] = mapped_column(Text)
    suggested_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    facts_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), default="RULES")
    model: Mapped[str] = mapped_column(String(120), default="lead-intelligence-rules-v1")
    prompt_version: Mapped[str] = mapped_column(String(40), default="lead-intelligence-v1")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")


class MessageSimilarityRecord(Timestamped, Base):
    __tablename__ = "message_similarity_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    message_draft_id: Mapped[str | None] = mapped_column(ForeignKey("message_drafts.id"), nullable=True, index=True)
    publication_id: Mapped[str | None] = mapped_column(ForeignKey("publications.id"), nullable=True, index=True)
    compared_to_type: Mapped[str] = mapped_column(String(40))
    compared_to_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    similarity_score: Mapped[float] = mapped_column(Float, default=0)
    method: Mapped[str] = mapped_column(String(40), default="TOKEN_COSINE")
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class CommunityScoreSnapshot(Timestamped, Base):
    __tablename__ = "community_score_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id"), index=True)
    community_score: Mapped[float] = mapped_column(Float, default=0)
    activity_score: Mapped[float] = mapped_column(Float, default=0)
    size_score: Mapped[float] = mapped_column(Float, default=0)
    lead_score: Mapped[float] = mapped_column(Float, default=0)
    conversion_score: Mapped[float] = mapped_column(Float, default=0)
    rules_score: Mapped[float] = mapped_column(Float, default=0)
    geography_score: Mapped[float] = mapped_column(Float, default=0)
    topic_score: Mapped[float] = mapped_column(Float, default=0)
    rationale: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ConstructiveOrganization(Timestamped, Base):
    __tablename__ = "constructive_organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ConstructiveObject(Timestamped, Base):
    __tablename__ = "constructive_objects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ConstructiveObjectAssignment(Timestamped, Base):
    __tablename__ = "constructive_object_assignments"
    __table_args__ = (UniqueConstraint("object_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    object_id: Mapped[str] = mapped_column(ForeignKey("constructive_objects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="WORKER")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ConstructiveEmployee(Timestamped, Base):
    __tablename__ = "constructive_employees"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    telegram_username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="WORKER")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ConstructiveWarehouse(Timestamped, Base):
    __tablename__ = "constructive_warehouses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ConstructiveRate(Timestamped, Base):
    __tablename__ = "constructive_rates"
    __table_args__ = (UniqueConstraint("organization_id", "employee_id", "object_id", "work_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("constructive_employees.id"), index=True)
    object_id: Mapped[str | None] = mapped_column(ForeignKey("constructive_objects.id"), nullable=True, index=True)
    work_type: Mapped[str] = mapped_column(String(160))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConstructiveLedgerRow(Timestamped, Base):
    __tablename__ = "constructive_ledger_rows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    object_id: Mapped[str] = mapped_column(ForeignKey("constructive_objects.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("constructive_employees.id"), index=True)
    work_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    work_type: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[float] = mapped_column(Float)
    rate: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    raw_line: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ConstructiveCabinet(Timestamped, Base):
    __tablename__ = "constructive_cabinets"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ConstructiveCabinetInvite(Timestamped, Base):
    __tablename__ = "constructive_cabinet_invites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(32), default="MASTER")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class ConstructiveAsmetMessage(Timestamped, Base):
    __tablename__ = "constructive_asmet_messages"
    __table_args__ = (UniqueConstraint("organization_id", "external_chat_id", "external_message_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("constructive_organizations.id"), index=True)
    external_chat_id: Mapped[str] = mapped_column(String(200), index=True)
    external_message_id: Mapped[str] = mapped_column(String(200), index=True)
    text: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    historical: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledgement_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    rejections: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)


for table_name, column_name, constraint_name, allowed_values in CHECKS:
    Base.metadata.tables[table_name].append_constraint(
        CheckConstraint(sql_check(column_name, allowed_values), name=constraint_name)
    )


@event.listens_for(Session, "before_flush")
def validate_enum_values(session: Session, flush_context: Any, instances: Any) -> None:
    """Reject invalid controlled values before an ORM write reaches the database."""
    allowed_by_table = {
        table_name: {column_name: set(values)}
        for table_name, column_name, _name, values in CHECKS
    }
    for entity in (*session.new, *session.dirty):
        table_values = allowed_by_table.get(entity.__table__.name, {})
        for column_name, allowed_values in table_values.items():
            value = getattr(entity, column_name, None)
            if value is not None and value not in allowed_values:
                raise ValueError(
                    f"Invalid {entity.__table__.name}.{column_name}: {value!r}; "
                    f"allowed values are {sorted(allowed_values)}"
                )
