from datetime import datetime, timedelta

import pytest
from app.campaign_intelligence import CampaignIntelligenceEngine
from app.dialog_triage import DialogTriageService, TriageConflict
from app.models import (
    Base,
    Community,
    CommunityCollection,
    CommunityCollectionMembership,
    DialogTriageCollectionMembership,
    IntegrationAccount,
    TelegramAccountProfile,
    TelegramDialog,
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
def triage_context(db: Session):
    user = User(email="triage@example.local", name="Triage", password_hash=hash_password("secret"))
    db.add(user)
    db.flush()
    workspace = Workspace(name="Triage", slug="triage", owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    integration = IntegrationAccount(workspace_id=workspace.id, platform="TELEGRAM", display_name="Alexey_Mifanyuk", status="CONNECTED")
    db.add(integration)
    db.flush()
    account = TelegramAccountProfile(workspace_id=workspace.id, integration_account_id=integration.id, first_name="Alexey", username="Alexey_Mifanyuk", authorization_status="AUTHORIZED", connection_status="CONNECTED")
    db.add(account)
    db.flush()
    now = datetime.utcnow()
    dialogs = [
        TelegramDialog(workspace_id=workspace.id, integration_account_id=integration.id, external_dialog_id="group", title="Group", dialog_type="GROUP", last_synced_at=now - timedelta(days=1)),
        TelegramDialog(workspace_id=workspace.id, integration_account_id=integration.id, external_dialog_id="unknown", title="Unknown", dialog_type="UNKNOWN", last_synced_at=now),
        TelegramDialog(workspace_id=workspace.id, integration_account_id=integration.id, external_dialog_id="person", title="Person", dialog_type="USER", last_synced_at=now),
    ]
    db.add_all(dialogs)
    db.commit()
    return workspace, user, account, dialogs


def test_next_batch_is_stable_and_system_collections_are_internal(db: Session, triage_context):
    workspace, _user, account, _dialogs = triage_context
    service = DialogTriageService()
    first = service.next_batch(db, workspace_id=workspace.id, account_id=account.id, limit=30)
    second = service.next_batch(db, workspace_id=workspace.id, account_id=account.id, limit=30)
    assert [item["title"] for item in first["dialogs"]] == ["Group", "Unknown", "Person"]
    assert [item["id"] for item in first["dialogs"]] == [item["id"] for item in second["dialogs"]]
    assert first["progress"]["total"] == 3
    assert db.scalar(select(DialogTriageCollectionMembership.id)) is None


def test_save_excludes_dialog_and_optimistic_locking_protects_manual_decision(db: Session, triage_context):
    workspace, user, account, dialogs = triage_context
    service = DialogTriageService()
    service.next_batch(db, workspace_id=workspace.id, account_id=account.id, limit=30)
    decision = service.save_one(db, workspace_id=workspace.id, account_id=account.id, dialog=dialogs[0], actor_id=user.id, payload={"expected_version": None, "review_status": "REVIEWED", "manual_dialog_type": "GROUP", "manual_eligibility": "ELIGIBLE", "collection_slugs": ["bali"], "tag_slugs": ["travel"]})
    db.commit()
    assert decision.version == 1
    assert service.next_batch(db, workspace_id=workspace.id, account_id=account.id, limit=30)["progress"]["remaining"] == 2
    with pytest.raises(TriageConflict, match="TRIAGE_VERSION_CONFLICT"):
        service.save_one(db, workspace_id=workspace.id, account_id=account.id, dialog=dialogs[0], actor_id=user.id, payload={"expected_version": 0, "review_status": "REVIEWED", "manual_dialog_type": "GROUP", "manual_eligibility": "READ_ONLY", "collection_slugs": ["bali"], "tag_slugs": []}, allow_existing=True)


def test_bulk_personal_and_needs_context_update_progress(db: Session, triage_context):
    workspace, user, account, dialogs = triage_context
    service = DialogTriageService()
    service.next_batch(db, workspace_id=workspace.id, account_id=account.id, limit=30)
    service.bulk_action(db, workspace_id=workspace.id, account_id=account.id, dialogs=dialogs[:2], actor_id=user.id, action="MARK_PERSONAL", collection_slug=None, tag_slug=None, reason=None, confirm_overwrite=False)
    db.commit()
    assert service.progress(db, workspace_id=workspace.id, account_id=account.id)["reviewed"] == 2
    service.bulk_action(db, workspace_id=workspace.id, account_id=account.id, dialogs=[dialogs[2]], actor_id=user.id, action="NEEDS_CONTEXT", collection_slug=None, tag_slug=None, reason="Need to inspect metadata", confirm_overwrite=False)
    db.commit()
    progress = service.progress(db, workspace_id=workspace.id, account_id=account.id)
    assert progress["needs_context"] == 1
    assert progress["remaining"] == 0


def test_campaign_intelligence_gate_requires_reviewed_eligible_dialog(db: Session, triage_context):
    workspace, user, account, dialogs = triage_context
    community = Community(workspace_id=workspace.id, external_id="linked", title="Linked group", platform="TELEGRAM")
    db.add(community)
    db.flush()
    dialogs[0].community_id = community.id
    db.commit()
    intelligence = CampaignIntelligenceEngine()
    assert community.id not in intelligence._eligible_community_ids(db, workspace.id)
    DialogTriageService().save_one(db, workspace_id=workspace.id, account_id=account.id, dialog=dialogs[0], actor_id=user.id, payload={"review_status": "REVIEWED", "manual_dialog_type": "GROUP", "manual_eligibility": "ELIGIBLE", "collection_slugs": [], "tag_slugs": []})
    db.commit()
    assert community.id in intelligence._eligible_community_ids(db, workspace.id)


def test_interactive_refresh_updates_community_dataset_and_completion(db: Session, triage_context):
    workspace, user, account, dialogs = triage_context
    community = Community(workspace_id=workspace.id, external_id="interactive", title="Bali travel group", platform="TELEGRAM")
    db.add(community)
    db.flush()
    dialogs[0].community_id = community.id
    db.commit()

    service = DialogTriageService()
    service.ensure_system_collections(db, workspace.id)
    saved = service.save_one(db, workspace_id=workspace.id, account_id=account.id, dialog=dialogs[0], actor_id=user.id, payload={"review_status": "REVIEWED", "manual_dialog_type": "GROUP", "manual_eligibility": "ELIGIBLE", "collection_slugs": ["bali"], "tag_slugs": ["travel"]})
    downstream = service.refresh_downstream(db, workspace_id=workspace.id, account_id=account.id, decisions=[saved], actor_id=user.id)
    db.commit()

    refreshed = db.get(Community, community.id)
    assert refreshed is not None and refreshed.manual_classification_override is True
    assert db.scalar(select(CommunityCollection).where(CommunityCollection.workspace_id == workspace.id, CommunityCollection.slug == "bali")) is not None
    assert db.scalar(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)) is not None
    assert downstream == {"communities_updated": 1, "campaign_scores_refreshed": 0}

    for dialog, dialog_type in zip(dialogs[1:], ("PERSON", "BOT")):
        service.save_one(db, workspace_id=workspace.id, account_id=account.id, dialog=dialog, actor_id=user.id, payload={"review_status": "REVIEWED", "manual_dialog_type": dialog_type, "manual_eligibility": "NOT_ELIGIBLE", "collection_slugs": [], "tag_slugs": []})
    db.commit()
    final_batch = service.next_batch(db, workspace_id=workspace.id, account_id=account.id, limit=30)
    assert final_batch["dialogs"] == []
    assert final_batch["completion"]["complete"] is True
    assert final_batch["completion"]["processed_dialogs"] == 3
    assert final_batch["completion"]["community_dataset"] == 1
