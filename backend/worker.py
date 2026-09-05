"""Durable Stage 1 publication worker.

Jobs are persisted in PostgreSQL and optionally announced through Redis. The
worker re-checks all safety policies immediately before an adapter call.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

from app.config import get_settings
from app.db import SessionLocal
from app.integrations import MockPlatformAdapter, PublishRequest, TelegramPlatformAdapter
from app.models import (
    Brand,
    Campaign,
    Community,
    CommunityPermission,
    Company,
    IntegrationAccount,
    MessageDraft,
    Publication,
    TelegramAccountProfile,
    Workspace,
)
from app.policy import PolicyEngine
from app.queue import claim_next_job
from app.services import audit, system_flag, within_interval
from app.telegram_engine.live_client import TelethonUserClient
from app.telegram_engine.vault import EncryptedLocalSessionVault
from sqlalchemy import func, select

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lead-hunter-worker")


def _workspace_context(db, publication: Publication):
    draft = db.get(MessageDraft, publication.message_draft_id)
    campaign = db.get(Campaign, publication.campaign_id) if publication.campaign_id else None
    community = db.get(Community, publication.community_id) if publication.community_id else None
    if draft is None or campaign is None or community is None:
        return None
    brand = db.get(Brand, campaign.brand_id)
    company = db.get(Company, brand.company_id) if brand else None
    workspace = db.get(Workspace, company.workspace_id) if company else None
    permission = db.scalar(
        select(CommunityPermission).where(
            CommunityPermission.community_id == community.id, CommunityPermission.status == "ACTIVE"
        )
    )
    integrations = list(db.scalars(select(IntegrationAccount).where(
        IntegrationAccount.workspace_id == workspace.id,
        IntegrationAccount.platform == community.platform,
    )).all()) if workspace else []
    preferred_username = os.getenv("TELEGRAM_ACCOUNT_USERNAME", "Alexey_Mifanyuk")
    preferred_profile = db.scalar(select(TelegramAccountProfile).where(
        TelegramAccountProfile.integration_account_id.in_([item.id for item in integrations]),
        TelegramAccountProfile.username == preferred_username,
        TelegramAccountProfile.authorization_status == "AUTHORIZED",
    )) if integrations else None
    integration = db.get(IntegrationAccount, preferred_profile.integration_account_id) if preferred_profile else (
        next((item for item in integrations if item.status == "CONNECTED"), None) or (integrations[0] if integrations else None)
    )
    sent_today = (
        db.scalar(
            select(func.count(Publication.id)).where(
                Publication.campaign_id == campaign.id,
                Publication.status.in_(["SENT", "PUBLISHED_CONFIRMED"]),
            )
        )
        or 0
    )
    return draft, campaign, community, workspace, permission, integration, int(sent_today)


def process_one() -> bool:
    db = SessionLocal()
    try:
        job = claim_next_job(db)
        if job is None:
            return False
        publication = db.get(Publication, job.publication_id)
        context = _workspace_context(db, publication) if publication else None
        if publication is None or context is None:
            job.status = "DEAD"
            job.error_code = "INVALID_PUBLICATION"
            job.error_message = "Publication references missing domain entities"
            db.commit()
            return True
        draft, campaign, community, workspace, permission, integration, sent_today = context
        publication_interval_minutes = max(
            1, int(os.getenv("CAMPAIGN_PUBLICATION_INTERVAL_MINUTES", "20"))
        )
        last_sent_at = db.scalar(
            select(func.max(Publication.sent_at)).where(
                Publication.campaign_id == campaign.id,
                Publication.status.in_(["SENT", "PUBLISHED_CONFIRMED"]),
                Publication.sent_at.isnot(None),
            )
        )
        if last_sent_at is not None:
            next_allowed_at = last_sent_at + timedelta(minutes=publication_interval_minutes)
            if next_allowed_at > datetime.utcnow():
                job.status = "QUEUED"
                job.available_at = next_allowed_at
                job.error_code = "CAMPAIGN_INTERVAL_WAIT"
                job.error_message = f"Next publication is held until {next_allowed_at.isoformat()}"
                publication.status = "QUEUED"
                db.commit()
                return True
        if system_flag(db, "EMERGENCY_STOP") or system_flag(db, "SAFETY_LOCK"):
            job.status = "PAUSED"
            job.paused_at = datetime.utcnow()
            job.error_code = "SAFETY_LOCK"
            job.error_message = "Emergency Stop or safety lock is enabled"
            publication.status = "PAUSED_BY_SAFETY"
            db.commit()
            return True
        telegram_account_safe = True
        if community.platform == "TELEGRAM":
            profile = db.scalar(select(TelegramAccountProfile).where(
                TelegramAccountProfile.integration_account_id == integration.id
            )) if integration else None
            now = datetime.utcnow()
            telegram_account_safe = bool(
                integration
                and profile
                and integration.status == "CONNECTED"
                and integration.health_status == "HEALTHY"
                and not integration.safety_lock
                and profile.authorization_status == "AUTHORIZED"
                and profile.safety_status == "HEALTHY"
                and not profile.manual_unlock_required
                and (profile.flood_wait_until is None or profile.flood_wait_until <= now)
            )
        decision = PolicyEngine(publication_mode=get_settings().publication_mode).can_publish(
            safety_lock=False,
            campaign_status=campaign.status,
            message_approved=draft.approval_status == "APPROVED",
            community_status=community.posting_status,
            sent_today=sent_today,
            daily_limit=campaign.daily_limit,
            workspace_status=workspace.status,
            company_status="ACTIVE",
            brand_status="ACTIVE",
            offer_status="ACTIVE",
            permission_active=permission is not None,
            integration_healthy=(telegram_account_safe if community.platform == "TELEGRAM" else (
                integration is None or integration.health_status in {"HEALTHY", "UNKNOWN"}
            )),
            content_type_allowed=(
                draft.validation_status == "VALID"
                and (not permission or not permission.allowed_content_types
                     or draft.publication_type in permission.allowed_content_types)
            ),
            publication_date_allowed=True,
            community_interval_ok=within_interval(
                db, community.id, minutes=(permission.min_interval_hours * 60 if permission and permission.min_interval_hours else 30)
            ),
        )
        if not decision.allowed:
            publication.status = "BLOCKED_BY_POLICY"
            publication.error_code = decision.code
            publication.error_message = decision.reason
            job.status = "FAILED" if job.attempts < job.max_attempts else "DEAD"
            job.error_code = decision.code
            job.error_message = decision.reason
            audit(
                db,
                workspace_id=workspace.id,
                actor_id=workspace.owner_id,
                action="publication.policy_denied",
                entity_type="Publication",
                entity_id=publication.id,
                after={"decision": decision.__dict__},
            )
            db.commit()
            return True
        if get_settings().publication_mode == "DRY_RUN":
            publication.status = "DRY_RUN"
            publication.dry_run = True
            publication.sent_at = datetime.utcnow()
            job.status = "SUCCEEDED"
            job.error_code = None
            job.error_message = None
            audit(
                db,
                workspace_id=workspace.id,
                actor_id=workspace.owner_id,
                action="publication.dry_run",
                entity_type="Publication",
                entity_id=publication.id,
                after={
                    "status": "DRY_RUN",
                    "correlation_id": job.correlation_id,
                    "trace_id": job.trace_id,
                },
            )
            db.commit()
            return True
        live_client = None
        if community.platform == "TELEGRAM" and get_settings().telegram_real_send_enabled:
            profile = db.scalar(select(TelegramAccountProfile).where(
                TelegramAccountProfile.integration_account_id == integration.id
            )) if integration else None
            if profile and profile.session_reference:
                vault = EncryptedLocalSessionVault(
                    get_settings().telegram_session_encryption_key,
                    get_settings().telegram_session_root,
                )
                proxy_port = os.getenv("TELEGRAM_PROXY_PORT")
                live_client = TelethonUserClient(
                    api_id=get_settings().telegram_api_id,
                    api_hash=get_settings().telegram_api_hash,
                    session_data=vault.load_session(profile.session_reference),
                    proxy_host=os.getenv("TELEGRAM_PROXY_HOST"),
                    proxy_port=int(proxy_port) if proxy_port else None,
                )
        adapter = (
            MockPlatformAdapter()
            if community.platform == "MOCK"
            else TelegramPlatformAdapter(get_settings().telegram_real_send_enabled, live_client)
        )
        result = asyncio.run(
            adapter.publish_message(
                PublishRequest(
                    # Public Telegram channels/supergroups are reliably resolved
                    # by username; the raw numeric entity id lacks the -100 peer
                    # prefix required by Telethon's entity cache.
                    destination=community.username or community.external_id,
                    content=draft.content,
                    idempotency_key=job.idempotency_key,
                )
            )
        )
        if result.accepted:
            verified = False
            verification_error = None
            if (
                community.platform == "TELEGRAM"
                and live_client is not None
                and result.external_message_id
            ):
                try:
                    verified = asyncio.run(
                        live_client.verify_message(
                            community.username or community.external_id,
                            result.external_message_id,
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - verification is a separate terminal check
                    verification_error = type(exc).__name__
            elif community.platform != "TELEGRAM":
                verification_error = "EXTERNAL_PLATFORM_VERIFICATION_NOT_IMPLEMENTED"
            else:
                verification_error = "TELEGRAM_MESSAGE_ID_MISSING"

            publication.external_message_id = result.external_message_id
            if verified:
                publication.status = "PUBLISHED_CONFIRMED"
                publication.sent_at = datetime.utcnow()
                publication.error_code = None
                publication.error_message = None
                job.status = "SUCCEEDED"
            else:
                publication.status = "NOT_CONFIRMED"
                publication.error_code = "PUBLICATION_NOT_CONFIRMED"
                publication.error_message = verification_error or "Telegram message existence check returned false"
                job.status = "PAUSED"
                job.paused_at = datetime.utcnow()
                job.error_code = "PUBLICATION_NOT_CONFIRMED"
                job.error_message = publication.error_message
        else:
            publication.status = "FAILED"
            publication.error_code = "ADAPTER_ERROR"
            publication.error_message = result.error
            job.status = "QUEUED" if job.attempts < job.max_attempts else "DEAD"
            job.available_at = datetime.utcnow() + timedelta(seconds=min(60, 2**job.attempts))
            job.error_code = "ADAPTER_ERROR"
            job.error_message = result.error
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.exception("publication job failed")
        return True
    finally:
        db.close()


def main() -> None:
    try:
        from redis import Redis

        Redis.from_url(get_settings().redis_url, decode_responses=True).ping()
        logger.info("lead-hunter-worker ready; PostgreSQL-backed queue connected to Redis")
    except Exception:
        logger.exception("Redis notification channel unavailable; DB polling remains active")
    while True:
        processed = process_one()
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
