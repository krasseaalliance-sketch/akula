from datetime import datetime

import pytest
from app.lead_intelligence.engine import LeadIntelligenceService, token_cosine
from app.models import Base, Community, CommunityPermission, User, Workspace, WorkspaceMember
from app.security import hash_password
from app.telegram_engine.engine import TelegramEngineService
from app.telegram_engine.vault import EncryptedLocalSessionVault, MockSessionVault
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
    user = User(email="stage2@example.local", name="Stage 2", password_hash=hash_password("secret"))
    db.add(user)
    db.flush()
    workspace = Workspace(name="Stage 2", slug="stage-2", owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    db.commit()
    return workspace, user


def test_encrypted_session_vault_never_writes_plain_session(tmp_path):
    from cryptography.fernet import Fernet

    vault = EncryptedLocalSessionVault(Fernet.generate_key(), tmp_path)
    reference = vault.store_session("account-1", b"secret-session-string")
    raw = b"".join(path.read_bytes() for path in tmp_path.iterdir())
    assert reference.startswith("local:")
    assert b"secret-session-string" not in raw
    assert vault.load_session(reference) == b"secret-session-string"
    vault.delete_session(reference)
    assert not list(tmp_path.iterdir())


def test_mock_authorization_dialog_sync_import_and_rules_are_human_gated(db: Session, workspace_user):
    workspace, user = workspace_user
    engine = TelegramEngineService(MockSessionVault())
    profile = engine.create_account(db, workspace_id=workspace.id, display_name="Mock Telegram", phone="+79991234567", api_credential_reference=None, actor=user)
    attempt = engine.start_authorization(db, profile=profile, phone="+79991234567", actor=user)
    profile = engine.complete_authorization(db, attempt=attempt, code="12345", actor=user)
    dialogs = engine.sync_dialogs(db, profile=profile, actor=user)
    target = next(item for item in dialogs if item.external_dialog_id == "balitravel_ru")
    imported = engine.import_community(db, workspace_id=workspace.id, actor=user, payload={
        "account_id": profile.integration_account_id, "title": target.title, "username": target.username,
        "external_id": target.external_dialog_id, "language": "ru", "idempotency_key": "test-import-1", "dry_run": False,
    })
    community = db.get(Community, imported["community_id"])
    assert community is not None
    assert community.posting_status == "NEEDS_REVIEW"
    assert db.scalar(select(CommunityPermission).where(CommunityPermission.community_id == community.id)) is None
    engine.sync_rules(db, profile=profile, community=community, actor=user)
    engine.analyze_rules(db, community=community, actor=user)
    assert db.scalar(select(CommunityPermission).where(CommunityPermission.community_id == community.id)) is None
    permission = engine.review_rules(db, community=community, actor=user, approved=True, allowed_content_types=["COMPANION_SEARCH"], allowed_days=[], min_interval_hours=24, expires_at=None)
    assert permission is not None
    assert permission.status == "ACTIVE"


def test_message_sync_is_idempotent_and_lead_does_not_enable_dm(db: Session, workspace_user):
    workspace, user = workspace_user
    engine = TelegramEngineService(MockSessionVault())
    profile = engine.create_account(db, workspace_id=workspace.id, display_name="Mock Telegram", phone=None, api_credential_reference=None, actor=user)
    attempt = engine.start_authorization(db, profile=profile, phone="+79991234567", actor=user)
    profile = engine.complete_authorization(db, attempt=attempt, code="12345", actor=user)
    dialog = next(item for item in engine.sync_dialogs(db, profile=profile, actor=user) if item.external_dialog_id == "digital_founders")
    first = engine.sync_messages(db, profile=profile, dialog=dialog, actor=user, max_messages=100)
    second = engine.sync_messages(db, profile=profile, dialog=dialog, actor=user, max_messages=100)
    assert len(first) == len(second) == 1
    leads = engine.discover_leads(db, profile=profile, actor=user, max_messages=100)
    assert leads
    assert all(item.direct_message_allowed is False for item in leads)


def test_flood_wait_requires_manual_unlock(db: Session, workspace_user):
    workspace, user = workspace_user
    engine = TelegramEngineService(MockSessionVault())
    profile = engine.create_account(db, workspace_id=workspace.id, display_name="Mock Telegram", phone=None, api_credential_reference=None, actor=user)
    attempt = engine.start_authorization(db, profile=profile, phone="+79991234567", actor=user)
    profile = engine.complete_authorization(db, attempt=attempt, code="12345", actor=user)
    incident = engine.create_incident(db, profile=profile, incident_type="FLOOD_WAIT", severity="HIGH", details={"retry_after": 60}, retry_after_seconds=60, actor=user)
    assert incident.status == "OPEN"
    assert profile.manual_unlock_required is True
    with pytest.raises(ValueError, match="FLOOD_WAIT_ACTIVE"):
        engine.unlock(db, profile=profile, actor=user)
    profile.flood_wait_until = datetime.utcnow()
    engine.unlock(db, profile=profile, actor=user)
    assert profile.manual_unlock_required is False


def test_lead_intelligence_classifies_intent_pain_need_and_recommendation():
    service = LeadIntelligenceService()
    result = service.analyze_text("Нужен сайт для бизнеса, кто может порекомендовать разработчика?", contact_initiated=False)
    assert result.intent == "DIGITAL_SERVICE"
    assert result.pain
    assert result.need
    assert result.score >= 70
    assert result.recommendation == "PUBLIC_REPLY"
    assert token_cosine("website developer", "Need a website developer") > 0.4
    assert token_cosine("website developer", "Bali yacht trip") == 0
