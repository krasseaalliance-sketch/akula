import pytest
from app.campaign_intelligence import CampaignIntelligenceEngine
from app.models import (
    Base,
    Brand,
    Campaign,
    CampaignCommunityScore,
    CampaignLearningSnapshot,
    Community,
    CommunityPermission,
    Company,
    Conversation,
    Lead,
    User,
    Workspace,
    WorkspaceMember,
)
from app.security import hash_password
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def workspace_user(db: Session):
    user = User(email="stage32@example.local", name="Stage 3.2", password_hash=hash_password("secret"))
    db.add(user)
    db.flush()
    workspace = Workspace(name="Stage 3.2", slug="stage-3-2", owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    company = Company(workspace_id=workspace.id, legal_name="Stage 3.2", public_name="Stage 3.2")
    db.add(company)
    db.flush()
    brand = Brand(company_id=company.id, name="Stage 3.2 Brand")
    db.add(brand)
    db.flush()
    campaign = Campaign(
        brand_id=brand.id,
        name="North Bali nature trip",
        objective="Получить заявки",
        geography="Bali",
        language="ru",
        status="READY",
        publication_policy="APPROVAL_REQUIRED",
    )
    db.add(campaign)
    db.commit()
    return workspace, user, campaign


def test_profile_infers_audience_segments():
    profile = CampaignIntelligenceEngine().build_profile(
        answers={
            "offer": "Поездка на север Бали",
            "audience": "путешественники, экспаты, любители природы, йога",
            "geographies": ["Bali"],
            "languages": ["ru"],
            "goal": "Получить заявки",
        },
        use_llm=False,
    )
    assert {"travelers", "expats", "nature_lovers", "yoga_wellness"}.issubset(profile.audience_segments)
    assert profile.provider == "RULES"


def test_analyze_ranks_semantically_matching_communities(db: Session, workspace_user):
    workspace, user, campaign = workspace_user
    matching = Community(
        workspace_id=workspace.id,
        platform="TELEGRAM",
        external_id="bali-nature",
        title="Русские путешественники на Бали",
        username="bali_travel_ru",
        description="Экспаты, туристы, природа и попутчики на Бали",
        language="ru",
        geography="Bali",
        category="travel",
        member_count=12000,
        activity_score=0.85,
        relevance_score=0.8,
        ai_tags=["bali", "travel", "nature", "companions"],
        posting_status="APPROVED",
    )
    irrelevant = Community(
        workspace_id=workspace.id,
        platform="TELEGRAM",
        external_id="accounting",
        title="Бухгалтерия Красноярск",
        description="Налоги и отчётность",
        language="ru",
        geography="Красноярск",
        category="business",
        member_count=300,
        activity_score=0.2,
        relevance_score=0.1,
        posting_status="NEEDS_REVIEW",
    )
    db.add_all([matching, irrelevant])
    db.flush()
    db.add(CommunityPermission(workspace_id=workspace.id, community_id=matching.id, status="ACTIVE"))
    engine = CampaignIntelligenceEngine()
    engine.create_profile(db, campaign=campaign, workspace_id=workspace.id, answers={"offer": "Поездка на север Бали", "audience": "путешественники экспаты природа", "geographies": ["Bali"], "languages": ["ru"], "goal": "Получить заявки"}, actor_id=user.id, use_llm=False)
    dashboard = engine.analyze(db, campaign=campaign, workspace_id=workspace.id, actor_id=user.id, use_llm=False)
    scores = db.scalars(select(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == campaign.id).order_by(CampaignCommunityScore.rank)).all()
    assert dashboard["communities_analyzed"] == 2
    assert scores[0].community_id == matching.id
    assert scores[0].community_score > scores[1].community_score
    assert 0 <= scores[0].lead_probability <= 100
    assert scores[0].recommendation in {"PUBLISH", "REVIEW"}


def test_analysis_is_idempotent_for_scores(db: Session, workspace_user):
    workspace, user, campaign = workspace_user
    db.add(Community(workspace_id=workspace.id, external_id="one", title="Bali travel", geography="Bali", category="travel", description="travelers", activity_score=0.5, relevance_score=0.5, posting_status="NEEDS_REVIEW"))
    db.commit()
    engine = CampaignIntelligenceEngine()
    answers = {"offer": "Bali trip", "audience": "travelers", "geographies": ["Bali"], "languages": ["ru"], "goal": "Получить заявки"}
    engine.create_profile(db, campaign=campaign, workspace_id=workspace.id, answers=answers, actor_id=user.id, use_llm=False)
    engine.analyze(db, campaign=campaign, workspace_id=workspace.id, actor_id=user.id, use_llm=False)
    engine.analyze(db, campaign=campaign, workspace_id=workspace.id, actor_id=user.id, use_llm=False)
    assert db.scalar(select(func.count()).select_from(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == campaign.id)) == 1


def test_learning_snapshot_uses_campaign_outcomes(db: Session, workspace_user):
    workspace, user, campaign = workspace_user
    lead = Lead(workspace_id=workspace.id, campaign_id=campaign.id, raw_text="Хочу поехать на Бали", status="CONVERTED", score=90)
    db.add(lead)
    db.flush()
    db.add(Conversation(workspace_id=workspace.id, campaign_id=campaign.id, lead_id=lead.id, external_chat_id="lead-1", status="CLOSED"))
    db.commit()
    snapshot = CampaignIntelligenceEngine().learn(db, campaign=campaign, workspace_id=workspace.id, actor_id=user.id)
    assert snapshot.converted_leads == 1
    assert db.scalar(select(func.count()).select_from(CampaignLearningSnapshot).where(CampaignLearningSnapshot.campaign_id == campaign.id)) == 1
