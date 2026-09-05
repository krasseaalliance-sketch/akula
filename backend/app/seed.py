from datetime import datetime

from sqlalchemy import select

from .db import SessionLocal, engine
from .models import (
    Audience,
    Base,
    Brand,
    Campaign,
    Community,
    CommunityPermission,
    Company,
    DiscoveryProfile,
    IntegrationAccount,
    Lead,
    MessageDraft,
    Offer,
    SystemState,
    TelegramAccountProfile,
    User,
    Workspace,
    WorkspaceMember,
)
from .security import hash_password


def _one(db, model, **filters):
    return db.scalar(select(model).filter_by(**filters))


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = _one(db, User, email="demo@leadhunter.local")
        if user is None:
            user = User(
                email="demo@leadhunter.local",
                name="Alexey Demo",
                password_hash=hash_password("demo-password"),
            )
            db.add(user)
            db.flush()
        workspace = _one(db, Workspace, slug="krassea-alliance")
        if workspace is None:
            workspace = Workspace(
                name="KRASSEA Alliance", slug="krassea-alliance", owner_id=user.id
            )
            db.add(workspace)
            db.flush()
        workspace.name = "KRASSEA Alliance"
        member = _one(db, WorkspaceMember, workspace_id=workspace.id, user_id=user.id)
        if member is None:
            db.add(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="OWNER",
                    status="ACTIVE",
                    joined_at=datetime.utcnow(),
                )
            )
        else:
            member.role = "OWNER"
            member.status = "ACTIVE"

        travel = _one(db, Company, workspace_id=workspace.id, public_name="KRASSEA Travel")
        if travel is None:
            travel = Company(
                workspace_id=workspace.id,
                legal_name="KRASSEA Travel",
                public_name="KRASSEA Travel",
                description="Travel and experiences",
            )
            db.add(travel)
            db.flush()
        digital = _one(db, Company, workspace_id=workspace.id, public_name="KRASSEA Digital")
        if digital is None:
            digital = Company(
                workspace_id=workspace.id,
                legal_name="KRASSEA Digital",
                public_name="KRASSEA Digital",
                description="Digital products and automation",
            )
            db.add(digital)
            db.flush()

        alliance = _one(db, Brand, company_id=travel.id, name="KRASSEA Alliance")
        if alliance is None:
            alliance = Brand(
                company_id=travel.id,
                name="KRASSEA Alliance",
                positioning="Intentional travel and local experiences",
                tone_of_voice="Warm, precise, human",
            )
            db.add(alliance)
            db.flush()
        vitrina = _one(db, Brand, company_id=digital.id, name="Витрина")
        if vitrina is None:
            vitrina = Brand(
                company_id=digital.id,
                name="Витрина",
                positioning="Digital solutions for teams",
                tone_of_voice="Clear, practical, calm",
            )
            db.add(vitrina)
            db.flush()

        offer_specs = [
            (
                alliance,
                "Балийские поездки",
                "TRAVEL",
                "Bali",
                "Small-group trips and companion search",
            ),
            (
                alliance,
                "Яхты на Красноярском море",
                "YACHT_TRIP",
                "Красноярск",
                "Private yacht trips and local experiences",
            ),
            (
                vitrina,
                "Создание сайтов",
                "WEBSITE",
                "Remote",
                "Websites for small and growing teams",
            ),
            (
                vitrina,
                "Создание Telegram-ботов",
                "TELEGRAM_BOT",
                "Remote",
                "Automation bots for teams",
            ),
            (
                vitrina,
                "Создание приложений",
                "MOBILE_APP",
                "Remote",
                "Mobile products for companies",
            ),
        ]
        offers: list[Offer] = []
        for brand, name, offer_type, geography, description in offer_specs:
            offer = _one(db, Offer, brand_id=brand.id, name=name)
            if offer is None:
                offer = Offer(
                    brand_id=brand.id,
                    name=name,
                    type=offer_type,
                    geography=geography,
                    description=description,
                    facts={"source": "seed", "verified": True},
                )
                db.add(offer)
                db.flush()
            offers.append(offer)

        campaign_specs: list[tuple[Brand, Offer, str, str, str | None, str]] = [
            (
                alliance,
                offers[0],
                "Бали — поиск попутчиков",
                "Найти людей, которым важна компания в поездке",
                "Bali",
                "ACTIVE",
            ),
            (
                alliance,
                offers[1],
                "Красноярск — яхтенные прогулки",
                "Найти компании на прогулки",
                "Красноярск",
                "READY",
            ),
            (
                vitrina,
                offers[2],
                "Digital — клиенты на сайты",
                "Найти бизнесы, которым нужен сайт",
                None,
                "ACTIVE",
            ),
            (
                vitrina,
                offers[3],
                "Digital — Telegram-боты",
                "Найти команды для автоматизации",
                None,
                "DRAFT",
            ),
            (
                vitrina,
                offers[4],
                "Digital — приложения",
                "Найти продуктовые команды",
                None,
                "DRAFT",
            ),
        ]
        campaigns: list[Campaign] = []
        for brand, offer, name, objective, campaign_geography, campaign_status in campaign_specs:
            campaign = _one(db, Campaign, brand_id=brand.id, name=name)
            if campaign is None:
                campaign = Campaign(
                    brand_id=brand.id,
                    offer_id=offer.id,
                    name=name,
                    objective=objective,
                    geography=campaign_geography,
                    status=campaign_status,
                )
                db.add(campaign)
                db.flush()
            else:
                campaign.offer_id = offer.id
                campaign.objective = objective
                campaign.geography = campaign_geography
                campaign.status = campaign_status
            campaigns.append(campaign)

        community_specs = [
            (
                "mock-bali-travel",
                "Bali Travel Community",
                "bali_travel",
                "Bali",
                "travel",
                12400,
                0.84,
                0.93,
                "APPROVED",
            ),
            (
                "mock-krasnoyarsk",
                "Красноярск: отдых и море",
                "krasnoyarsk_rest",
                "Красноярск",
                "local",
                5800,
                0.72,
                0.88,
                "APPROVED",
            ),
        ]
        communities: list[Community] = []
        for (
            external_id,
            title,
            username,
            geography,
            category,
            member_count,
            activity,
            relevance,
            posting_status,
        ) in community_specs:
            community = _one(db, Community, workspace_id=workspace.id, external_id=external_id)
            if community is None:
                community = Community(
                    workspace_id=workspace.id,
                    platform="MOCK",
                    external_id=external_id,
                    title=title,
                    username=username,
                    geography=geography,
                    category=category,
                    member_count=member_count,
                    activity_score=activity,
                    relevance_score=relevance,
                    posting_status=posting_status,
                )
                db.add(community)
                db.flush()
            else:
                community.title = title
                community.posting_status = posting_status
            communities.append(community)
            permission = _one(
                db, CommunityPermission, community_id=community.id, workspace_id=workspace.id
            )
            if permission is None:
                db.add(
                    CommunityPermission(
                        workspace_id=workspace.id,
                        community_id=community.id,
                        permission_type="POST",
                        status="ACTIVE",
                        approved_by=user.id,
                    )
                )

        lead_specs = [
            (
                campaigns[0],
                communities[0],
                "Марина",
                "marina_trip",
                "Ищу попутчиков на Бали в октябре, одной ехать не хочется",
                "Попутчики на Бали",
                "QUALIFIED",
                0.94,
                0.91,
            ),
            (
                campaigns[2],
                communities[1],
                "Илья",
                "ilya_site",
                "Кто может сделать сайт для небольшой студии?",
                "Создание сайта",
                "NEW",
                0.81,
                0.87,
            ),
            (
                campaigns[0],
                communities[0],
                "Олег",
                "oleg_trip",
                "Посоветуйте спокойный маршрут по острову",
                "Маршрут по Бали",
                "REVIEW",
                0.68,
                0.75,
            ),
        ]
        leads: list[Lead] = []
        for (
            campaign,
            community,
            author_name,
            username,
            raw_text,
            need,
            status,
            score,
            confidence,
        ) in lead_specs:
            lead = _one(db, Lead, workspace_id=workspace.id, author_username=username)
            if lead is None:
                lead = Lead(
                    workspace_id=workspace.id,
                    campaign_id=campaign.id,
                    source_platform="MOCK",
                    source_community_id=community.id,
                    author_name=author_name,
                    author_username=username,
                    raw_text=raw_text,
                    normalized_text=raw_text,
                    detected_need=need,
                    score=score,
                    confidence=confidence,
                    status=status,
                )
                db.add(lead)
                db.flush()
            leads.append(lead)

        if _one(db, Audience, workspace_id=workspace.id, name="High intent leads") is None:
            db.add(
                Audience(
                    workspace_id=workspace.id,
                    name="High intent leads",
                    description="Leads with a clear service request",
                    criteria={"min_score": 0.7},
                )
            )
        if _one(db, MessageDraft, campaign_id=campaigns[0].id, lead_id=leads[0].id) is None:
            db.add(
                MessageDraft(
                    campaign_id=campaigns[0].id,
                    community_id=communities[0].id,
                    lead_id=leads[0].id,
                    content="Марина, добрый день! Видим, что вы ищете компанию на Бали в октябре. Можем познакомить с участниками поездки и рассказать о формате.",
                    created_by=user.id,
                    approval_status="APPROVED",
                    facts_snapshot={"offer": offers[0].name},
                    generation_context={"provider": "seed"},
                )
            )
        if _one(db, IntegrationAccount, workspace_id=workspace.id, platform="MOCK") is None:
            db.add(
                IntegrationAccount(
                    workspace_id=workspace.id,
                    platform="MOCK",
                    display_name="Mock platform",
                    status="CONNECTED",
                    health_status="HEALTHY",
                )
            )
        telegram_integration = _one(db, IntegrationAccount, workspace_id=workspace.id, platform="TELEGRAM")
        if telegram_integration is None:
            telegram_integration = IntegrationAccount(
                workspace_id=workspace.id,
                platform="TELEGRAM",
                display_name="Telegram mock workspace account",
                status="DISCONNECTED",
                health_status="UNKNOWN",
                account_type="USER",
                authorization_status="NOT_CONFIGURED",
                safety_status="DISCONNECTED",
                connection_status="DISCONNECTED",
            )
            db.add(telegram_integration)
            db.flush()
        if _one(db, TelegramAccountProfile, integration_account_id=telegram_integration.id) is None:
            db.add(TelegramAccountProfile(
                workspace_id=workspace.id,
                integration_account_id=telegram_integration.id,
                account_type="USER",
                authorization_status="NOT_CONFIGURED",
                safety_status="DISCONNECTED",
                connection_status="DISCONNECTED",
            ))
        profile_specs = [
            (campaigns[0], "Бали — поиск попутчиков", ["Бали", "Bali", "попутчик", "travel", "expats"]),
            (campaigns[1], "Красноярск — яхты", ["Красноярск", "яхты", "прогулка", "Дивногорск"]),
            (campaigns[2], "Digital — сайты", ["нужен сайт", "кто сделает сайт", "разработчик"]),
            (campaigns[3], "Digital — Telegram-боты", ["Telegram-бот", "нужен бот", "автоматизация"]),
            (campaigns[4], "Digital — приложения", ["мобильное приложение", "нужен разработчик"]),
        ]
        for campaign, name, keywords in profile_specs:
            if _one(db, DiscoveryProfile, campaign_id=campaign.id, name=name) is None:
                db.add(DiscoveryProfile(
                    campaign_id=campaign.id,
                    name=name,
                    platform="TELEGRAM",
                    languages=[campaign.language],
                    geography=[campaign.geography] if campaign.geography else [],
                    include_keywords=keywords,
                    exclude_keywords=["спам", "вакансия"],
                    community_categories=["travel", "yachts", "digital"],
                    intent_signals=["нужен", "ищу", "кто может", "подскажите"],
                    negative_signals=["спам", "вакансия"],
                    minimum_activity_score=0.1,
                    minimum_relevance_score=0.2,
                ))
        for key, enabled in (("EMERGENCY_STOP", False), ("SAFETY_LOCK", False)):
            state = db.get(SystemState, key)
            if state is None:
                db.add(SystemState(key=key, value="true" if enabled else "false", enabled=enabled))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
