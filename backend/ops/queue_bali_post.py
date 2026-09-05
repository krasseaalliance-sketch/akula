"""Queue one operator-approved Bali campaign post for a confirmed community."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Campaign,
    Community,
    CommunityPermission,
    MessageDraft,
    Publication,
    TelegramAccountProfile,
    Workspace,
)
from app.queue import enqueue_publication
from app.service_scheduler import actor_for
from app.telegram_engine.engine import TelegramEngineService


USERNAME = "bali_russia_choogl"
IDEMPOTENCY = "campaign-bali-companions-first-live-" + USERNAME
CONTENT = (
    "\u0420\u0435\u0431\u044f\u0442\u0430, \u0438\u0449\u0435\u043c \u043f\u043e\u043f\u0443\u0442\u0447\u0438\u043a\u043e\u0432 \u043d\u0430 \u0434\u0432\u0443\u0445\u0434\u043d\u0435\u0432\u043d\u0443\u044e \u043f\u043e\u0435\u0437\u0434\u043a\u0443 \u043f\u043e \u0441\u0435\u0432\u0435\u0440\u0443 \u0411\u0430\u043b\u0438 29\u201330 \u0438\u044e\u043b\u044f. "
    "\u041f\u043b\u0430\u043d\u0438\u0440\u0443\u0435\u043c \u0434\u0435\u043b\u044c\u0444\u0438\u043d\u043e\u0432, \u0411\u0430\u0442\u0443\u0440, Sekumpul, \u0445\u0440\u0430\u043c \u043d\u0430 \u043e\u0437\u0435\u0440\u0435, \u043a\u043b\u0443\u0431\u043d\u0438\u0447\u043d\u044b\u0435 \u043f\u043b\u0430\u043d\u0442\u0430\u0446\u0438\u0438 \u0438 \u0434\u0438\u043a\u0438\u0445 \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u0445. "
    "\u0415\u0434\u0435\u043c \u043d\u0430 \u043c\u0430\u0448\u0438\u043d\u0435, \u0435\u0441\u0442\u044c \u0447\u0435\u0442\u044b\u0440\u0435 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0445 \u043c\u0435\u0441\u0442\u0430. "
    "\u0415\u0441\u043b\u0438 \u043a\u0442\u043e\u2011\u0442\u043e \u0445\u043e\u0447\u0435\u0442 \u043f\u0440\u0438\u0441\u043e\u0435\u0434\u0438\u043d\u0438\u0442\u044c\u0441\u044f, \u043d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0432 \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u044f\u0445."
)


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        profile = db.scalar(select(TelegramAccountProfile).where(
            TelegramAccountProfile.workspace_id == workspace.id,
            TelegramAccountProfile.username == "Alexey_Mifanyuk",
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        ))
        actor = actor_for(workspace, db)
        engine = TelegramEngineService()
        dialogs = engine.sync_dialogs(db, profile=profile, actor=actor)
        dialog = next((item for item in dialogs if (item.username or "").casefold() == USERNAME.casefold()), None)
        if dialog is None or not dialog.is_joined:
            raise RuntimeError("TARGET_DIALOG_NOT_JOINED")
        community = db.scalar(select(Community).where(
            Community.workspace_id == workspace.id,
            Community.external_id == dialog.external_dialog_id,
        ))
        campaign = db.scalar(select(Campaign).where(
            Campaign.geography.ilike("%Bali%"), Campaign.status == "ACTIVE",
        ).order_by(Campaign.created_at))
        if community is None or campaign is None:
            raise RuntimeError("BALI_CAMPAIGN_OR_COMMUNITY_NOT_READY")

        permission = db.scalar(select(CommunityPermission).where(
            CommunityPermission.workspace_id == workspace.id,
            CommunityPermission.community_id == community.id,
        ))
        if permission is None:
            permission = CommunityPermission(
                workspace_id=workspace.id, community_id=community.id, permission_type="POST"
            )
            db.add(permission)
        permission.status = "ACTIVE"
        permission.approved_by = actor.id
        permission.reviewed_by = actor.id
        permission.reviewed_at = datetime.utcnow()
        permission.allowed_content_types = ["COMPANION_SEARCH"]
        permission.evidence = "Operator confirmed Telegram write permission in chat"
        community.posting_status = "APPROVED"

        draft = db.scalar(select(MessageDraft).where(
            MessageDraft.campaign_id == campaign.id,
            MessageDraft.community_id == community.id,
            MessageDraft.content == CONTENT,
        ))
        if draft is None:
            draft = MessageDraft(
                campaign_id=campaign.id,
                community_id=community.id,
                message_type="DIRECT_RESPONSE",
                publication_type="COMPANION_SEARCH",
                language="ru",
                content=CONTENT,
                facts_snapshot={"dates": "29-30 July", "route": "North Bali", "seats": 4, "verified": True},
                generation_context={"operator_confirmed": True, "unique_for_community": USERNAME},
                model_name="operator-approved-v1",
                prompt_version="operator-approved-v1",
                similarity_score=0,
                validation_status="VALID",
                approval_status="APPROVED",
                created_by=actor.id,
                approved_by=actor.id,
                naturalness_score=90,
                human_similarity_score=0,
                human_critic={"operator_confirmed": True},
            )
            db.add(draft)
            db.flush()

        publication = db.scalar(select(Publication).where(Publication.idempotency_key == IDEMPOTENCY))
        if publication is None:
            publication = Publication(
                message_draft_id=draft.id,
                campaign_id=campaign.id,
                community_id=community.id,
                idempotency_key=IDEMPOTENCY,
            )
            db.add(publication)
            db.flush()
            job = enqueue_publication(db, publication)
            db.commit()
            print(f"QUEUED {USERNAME} {publication.id} {job.id}", flush=True)
        else:
            print(f"EXISTING {publication.status} {publication.id} {publication.external_message_id}", flush=True)


if __name__ == "__main__":
    main()
