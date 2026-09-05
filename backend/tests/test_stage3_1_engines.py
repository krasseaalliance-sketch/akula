import pytest
from app.community_classification import CommunityClassificationEngine
from app.human_writing.critic import critic_message
from app.human_writing.personas import ENDINGS, OPENINGS, PERSONAS
from app.models import (
    Base,
    Community,
    CommunityCollection,
    CommunityCollectionMembership,
    User,
    Workspace,
    WorkspaceMember,
)
from app.security import hash_password
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def workspace_user(db: Session):
    user = User(email="stage31@example.local", name="Stage 3.1", password_hash=hash_password("secret"))
    db.add(user)
    db.flush()
    workspace = Workspace(name="Stage 3.1", slug="stage-31", owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    db.commit()
    return workspace, user


def test_human_writing_library_has_requested_coverage():
    assert len(PERSONAS) == 50
    assert len(OPENINGS) >= 500
    assert len(ENDINGS) >= 500
    assert len(set(OPENINGS)) == len(OPENINGS)
    assert len(set(ENDINGS)) == len(ENDINGS)


def test_message_critic_accepts_contextual_draft_and_flags_bot_language():
    natural = critic_message("Привет! Я тоже сейчас на Бали. Могу подсказать по району Убуда — что именно ищете?")
    bot = critic_message("Уважаемый пользователь, рад предложить уникальную возможность. Оставьте заявку!")
    assert natural.naturalness_score >= 90
    assert "BOT_LIKE" in bot.flags
    assert bot.rewrite_required is True


def test_community_classification_is_bali_idempotent_and_multi_collection(db: Session, workspace_user):
    workspace, _user = workspace_user
    community = Community(workspace_id=workspace.id, external_id="bali-1", title="Bali community", description="Ищем попутчика для поездки и прогулок")
    db.add(community)
    db.flush()
    engine = CommunityClassificationEngine()
    first = engine.classify_community(db, community=community)
    db.flush()
    first_memberships = list(db.scalars(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)).all())
    second = engine.classify_community(db, community=community)
    db.flush()
    second_memberships = list(db.scalars(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)).all())
    slugs = {item.slug for item in db.scalars(select(CommunityCollection).where(CommunityCollection.id.in_([item.collection_id for item in second_memberships]))).all()}
    assert first.region == second.region == "Бали"
    assert "bali" in slugs and "bali/companions" in slugs and "travel" in slugs
    assert len(first_memberships) == len(second_memberships)
    assert len(second_memberships) > 1


def test_description_change_reclassifies_bali_subcategory(db: Session, workspace_user):
    workspace, _user = workspace_user
    community = Community(workspace_id=workspace.id, external_id="bali-2", title="Bali community", description="Ищем попутчика")
    db.add(community)
    db.flush()
    engine = CommunityClassificationEngine()
    engine.classify_community(db, community=community)
    community.description = "Йога и медитация утром в Убуде"
    engine.classify_community(db, community=community)
    collections = list(db.scalars(select(CommunityCollection).join(CommunityCollectionMembership, CommunityCollectionMembership.collection_id == CommunityCollection.id).where(CommunityCollectionMembership.community_id == community.id)).all())
    assert "bali/yoga" in {item.slug for item in collections}
    assert "bali/companions" not in {item.slug for item in collections}


def test_manual_classification_override_wins(db: Session, workspace_user):
    workspace, user = workspace_user
    community = Community(workspace_id=workspace.id, external_id="manual-1", title="Bali yoga", description="Йога")
    db.add(community)
    db.flush()
    engine = CommunityClassificationEngine()
    engine.classify_community(db, community=community, actor_id=user.id)
    before = {item.collection_id for item in db.scalars(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)).all()}
    community.manual_classification_override = True
    community.region = "Manual region"
    community.description = "Только Красноярск"
    engine.classify_community(db, community=community, actor_id=user.id)
    after = {item.collection_id for item in db.scalars(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)).all()}
    assert community.region == "Manual region"
    assert before == after
