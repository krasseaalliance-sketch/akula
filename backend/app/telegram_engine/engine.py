from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Campaign,
    Community,
    CommunityPermission,
    Conversation,
    ConversationMessage,
    IntegrationAccount,
    Lead,
    Publication,
    TelegramAccountIncident,
    TelegramAccountProfile,
    TelegramAuthorizationAttempt,
    TelegramCommunityCandidate,
    TelegramCommunitySnapshot,
    TelegramDialog,
    TelegramDiscoveryRun,
    TelegramImportRun,
    TelegramMessageRecord,
    TelegramRuleAnalysis,
    TelegramSyncCursor,
    User,
)
from ..services import audit, dedupe_key, normalize_text
from .live_client import TelethonUserClient
from .mock_client import MockTelegramClient
from .vault import MockSessionVault, SessionVault

_CLIENTS: dict[str, MockTelegramClient] = {}
_MOCK_VAULT = MockSessionVault()
_PENDING_PHONES: dict[str, str] = {}
_PENDING_CODE_HASHES: dict[str, str] = {}


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return "***"
    return f"+{'*' * max(0, len(digits) - 4)}{digits[-4:]}"


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


class TelegramEngineService:
    """Mock-first Telegram domain service.

    The service owns the Telegram-specific workflow. Joining is available only
    through an explicit operator-selected public username; it never bypasses a
    restriction, sends an unsolicited DM, or approves permissions from
    imported/discovered/rule-analysis data.
    """

    def __init__(self, vault: SessionVault | None = None) -> None:
        settings = get_settings()
        if vault is not None:
            self.vault = vault
        elif settings.telegram_real_connect_enabled or settings.telegram_real_send_enabled:
            from .vault import EncryptedLocalSessionVault
            self.vault = EncryptedLocalSessionVault(settings.telegram_session_encryption_key, settings.telegram_session_root)
        else:
            self.vault = _MOCK_VAULT

    @staticmethod
    def client(integration_account_id: str) -> MockTelegramClient:
        return _CLIENTS.setdefault(integration_account_id, MockTelegramClient())

    def _client_for_profile(self, profile: TelegramAccountProfile) -> Any:
        settings = get_settings()
        if settings.telegram_real_connect_enabled or settings.telegram_real_send_enabled:
            session_data = self.vault.load_session(profile.session_reference) if profile.session_reference else None
            return TelethonUserClient(
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
                session_data=session_data,
                proxy_host=settings.telegram_proxy_host,
                proxy_port=settings.telegram_proxy_port,
            )
        return self.client(profile.integration_account_id)

    @staticmethod
    def profile(db: Session, account_id: str) -> TelegramAccountProfile:
        profile = db.get(TelegramAccountProfile, account_id)
        if profile is None:
            raise ValueError("Telegram account not found")
        return profile

    @staticmethod
    def profile_for_integration(db: Session, integration_id: str) -> TelegramAccountProfile:
        profile = db.scalar(
            select(TelegramAccountProfile).where(
                TelegramAccountProfile.integration_account_id == integration_id
            )
        )
        if profile is None:
            raise ValueError("Telegram account profile not found")
        return profile

    def create_account(self, db: Session, *, workspace_id: str, display_name: str, phone: str | None,
                       api_credential_reference: str | None, actor: User) -> TelegramAccountProfile:
        integration = IntegrationAccount(
            workspace_id=workspace_id,
            platform="TELEGRAM",
            display_name=display_name,
            status="DISCONNECTED",
            health_status="UNKNOWN",
            account_type="USER",
            authorization_status="NOT_CONFIGURED",
            safety_status="DISCONNECTED",
            connection_status="DISCONNECTED",
            phone_masked=mask_phone(phone),
            credential_reference=api_credential_reference,
        )
        db.add(integration)
        db.flush()
        profile = TelegramAccountProfile(
            workspace_id=workspace_id,
            integration_account_id=integration.id,
            phone_masked=mask_phone(phone),
            api_credential_reference=api_credential_reference,
        )
        db.add(profile)
        db.flush()
        audit(db, workspace_id=workspace_id, actor_id=actor.id, action="telegram.account.created",
              entity_type="TelegramAccountProfile", entity_id=profile.id,
              after={"authorization_status": profile.authorization_status, "real_connect": False})
        db.commit()
        db.refresh(profile)
        return profile

    def start_authorization(self, db: Session, *, profile: TelegramAccountProfile, phone: str,
                            actor: User) -> TelegramAuthorizationAttempt:
        integration = db.get(IntegrationAccount, profile.integration_account_id)
        if integration is None:
            raise ValueError("Integration account not found")
        profile.phone_masked = mask_phone(phone)
        integration.phone_masked = profile.phone_masked
        profile.authorization_status = "CODE_REQUIRED"
        profile.connection_status = "CONNECTING"
        integration.authorization_status = "CODE_REQUIRED"
        integration.connection_status = "CONNECTING"
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        attempt = TelegramAuthorizationAttempt(
            telegram_account_profile_id=profile.id,
            status="CODE_SENT",
            expires_at=expires_at,
            created_by=actor.id,
        )
        db.add(attempt)
        db.flush()
        _PENDING_PHONES[attempt.id] = phone
        client = self._client_for_profile(profile)
        _run(client.request_code(phone))
        code_hash = getattr(client, "_phone_code_hash", None)
        if code_hash:
            _PENDING_CODE_HASHES[attempt.id] = str(code_hash)
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.authorization.code_requested",
              entity_type="TelegramAuthorizationAttempt", entity_id=attempt.id, after={"expires_at": expires_at.isoformat()})
        db.commit()
        db.refresh(attempt)
        return attempt

    def complete_authorization(self, db: Session, *, attempt: TelegramAuthorizationAttempt,
                               code: str, actor: User) -> TelegramAccountProfile:
        if attempt.expires_at < datetime.utcnow():
            attempt.status = "EXPIRED"
            db.commit()
            raise ValueError("AUTHORIZATION_ATTEMPT_EXPIRED")
        profile = self.profile(db, attempt.telegram_account_profile_id)
        try:
            phone = _PENDING_PHONES.get(attempt.id, "mock")
            client = self._client_for_profile(profile)
            code_hash = _PENDING_CODE_HASHES.get(attempt.id)
            if code_hash and hasattr(client, "_phone_code_hash"):
                client._phone_code_hash = code_hash
            session_data, identity = _run(client.sign_in(phone, code))
        except RuntimeError as exc:
            if "SessionPasswordNeeded" in str(exc) or "PASSWORD_REQUIRED" in str(exc):
                attempt.status = "PASSWORD_REQUIRED"
                profile.authorization_status = "PASSWORD_REQUIRED"
                db.commit()
                raise ValueError("PASSWORD_REQUIRED") from exc
            attempt.status = "FAILED"
            attempt.error_code = "AUTHORIZATION_FAILED"
            profile.authorization_status = "FAILED"
            profile.connection_status = "ERROR"
            db.commit()
            raise
        except ValueError as exc:
            attempt.status = "FAILED"
            attempt.error_code = str(exc)
            profile.authorization_status = "FAILED"
            profile.connection_status = "ERROR"
            db.commit()
            raise
        return self._authorize_success(db, profile, attempt, session_data, identity, actor)

    def complete_password_authorization(self, db: Session, *, attempt: TelegramAuthorizationAttempt,
                                        password: str, actor: User) -> TelegramAccountProfile:
        profile = self.profile(db, attempt.telegram_account_profile_id)
        phone = _PENDING_PHONES.get(attempt.id, "mock")
        session_data, identity = _run(self._client_for_profile(profile).sign_in_password(phone, password))
        return self._authorize_success(db, profile, attempt, session_data, identity, actor)

    def _authorize_success(self, db: Session, profile: TelegramAccountProfile,
                           attempt: TelegramAuthorizationAttempt, session_data: bytes,
                           identity: dict[str, str], actor: User) -> TelegramAccountProfile:
        reference = self.vault.store_session(profile.id, session_data)
        now = datetime.utcnow()
        profile.session_reference = reference
        profile.telegram_user_id = identity.get("id")
        profile.username = identity.get("username")
        profile.first_name = identity.get("first_name")
        profile.last_name = identity.get("last_name")
        profile.authorization_status = "AUTHORIZED"
        profile.connection_status = "CONNECTED"
        profile.safety_status = "HEALTHY"
        profile.last_connected_at = now
        profile.last_health_check_at = now
        attempt.status = "COMPLETED"
        attempt.completed_at = now
        integration = db.get(IntegrationAccount, profile.integration_account_id)
        if integration:
            integration.external_account_id = profile.telegram_user_id
            integration.authorization_status = "AUTHORIZED"
            integration.connection_status = "CONNECTED"
            integration.status = "CONNECTED"
            integration.health_status = "HEALTHY"
            integration.safety_status = "HEALTHY"
            integration.last_health_check_at = now
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.authorization.completed",
              entity_type="TelegramAccountProfile", entity_id=profile.id,
              after={"authorization_status": "AUTHORIZED", "session_stored": True})
        db.commit()
        db.refresh(profile)
        return profile

    def disconnect(self, db: Session, *, profile: TelegramAccountProfile, actor: User) -> None:
        if profile.session_reference:
            self.vault.delete_session(profile.session_reference)
        profile.session_reference = None
        profile.authorization_status = "REVOKED"
        profile.connection_status = "DISCONNECTED"
        profile.safety_status = "REVOKED"
        profile.manual_unlock_required = False
        integration = db.get(IntegrationAccount, profile.integration_account_id)
        if integration:
            integration.status = "DISCONNECTED"
            integration.authorization_status = "REVOKED"
            integration.connection_status = "DISCONNECTED"
            integration.health_status = "UNKNOWN"
            integration.safety_status = "REVOKED"
            integration.safety_lock = True
        if not (get_settings().telegram_real_connect_enabled or get_settings().telegram_real_send_enabled):
            self.client(profile.integration_account_id).revoked = True
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.authorization.revoked",
              entity_type="TelegramAccountProfile", entity_id=profile.id, after={"session_destroyed": True})
        db.commit()

    def health_check(self, db: Session, *, profile: TelegramAccountProfile, actor: User | None = None) -> bool:
        ok = bool(profile.authorization_status == "AUTHORIZED" and _run(self._client_for_profile(profile).health_check()))
        now = datetime.utcnow()
        profile.last_health_check_at = now
        integration = db.get(IntegrationAccount, profile.integration_account_id)
        if ok and not profile.manual_unlock_required:
            profile.connection_status = "CONNECTED"
            if profile.safety_status not in {"FLOOD_WAIT", "SAFETY_LOCK", "SPAM_WARNING", "RESTRICTED"}:
                profile.safety_status = "HEALTHY"
            if integration:
                integration.health_status = "HEALTHY"
                integration.connection_status = "CONNECTED"
        elif integration:
            integration.health_status = "UNHEALTHY"
            profile.connection_status = "ERROR"
        if actor:
            audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.account.health_check",
                  entity_type="TelegramAccountProfile", entity_id=profile.id, after={"healthy": ok})
        db.commit()
        return ok

    def sync_dialogs(self, db: Session, *, profile: TelegramAccountProfile, actor: User) -> list[TelegramDialog]:
        self._require_authorized(profile)
        rows = _run(self._client_for_profile(profile).get_dialogs())
        result: list[TelegramDialog] = []
        now = datetime.utcnow()
        for item in rows:
            dialog = db.scalar(select(TelegramDialog).where(
                TelegramDialog.integration_account_id == profile.integration_account_id,
                TelegramDialog.external_dialog_id == item.external_id,
            ))
            values = {
                "workspace_id": profile.workspace_id,
                "integration_account_id": profile.integration_account_id,
                "external_dialog_id": item.external_id,
                "dialog_type": item.dialog_type,
                "title": item.title,
                "username": item.username,
                "is_public": item.is_public,
                "is_joined": item.is_joined,
                "can_send_messages": item.can_send_messages,
                "can_view_history": item.can_view_history,
                "has_slow_mode": item.slow_mode_seconds is not None,
                "slow_mode_seconds": item.slow_mode_seconds,
                "member_count": item.member_count,
                "last_synced_at": now,
                "raw_metadata_sanitized": {"description": item.description, "category": item.category},
            }
            if dialog is None:
                dialog = TelegramDialog(**values)
                db.add(dialog)
            else:
                for key, value in values.items():
                    setattr(dialog, key, value)
            result.append(dialog)
            community = db.scalar(select(Community).where(
                Community.workspace_id == profile.workspace_id,
                Community.external_id == item.external_id,
            ))
            community_values = {
                "workspace_id": profile.workspace_id,
                "platform": "TELEGRAM",
                "external_id": item.external_id,
                "title": item.title or item.external_id,
                "username": item.username,
                "url": f"https://t.me/{item.username}" if item.username else None,
                "description": item.description,
                "language": item.language or "ru",
                "geography": item.geography,
                "category": item.category,
                "member_count": item.member_count or 0,
                "rules_text": item.rules_text,
            }
            if community is None:
                community = Community(**community_values, classification_status="NEEDS_REVIEW", classification_source="PENDING_MANUAL_TRIAGE", classification_confidence=0, classification_reason="Awaiting manual dialog triage")
                db.add(community)
                db.flush()
            elif not community.manual_classification_override:
                for key, value in community_values.items():
                    if key != "workspace_id":
                        setattr(community, key, value)
            dialog.community_id = community.id
        profile.last_successful_sync_at = now
        integration = db.get(IntegrationAccount, profile.integration_account_id)
        if integration:
            integration.last_sync_at = now
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.dialogs.synced",
              entity_type="TelegramAccountProfile", entity_id=profile.id, after={"count": len(result)})
        db.commit()
        return result

    def import_community(self, db: Session, *, workspace_id: str, actor: User,
                         payload: dict[str, Any]) -> dict[str, Any]:
        existing_run = db.scalar(select(TelegramImportRun).where(
            TelegramImportRun.idempotency_key == payload["idempotency_key"]))
        if existing_run:
            return {"run_id": existing_run.id, "status": existing_run.status, "imported": existing_run.imported_rows, "duplicate": True}
        run = TelegramImportRun(workspace_id=workspace_id, integration_account_id=payload.get("account_id"),
                                source=payload.get("source", "MANUAL"), idempotency_key=payload["idempotency_key"],
                                status="DRY_RUN" if payload.get("dry_run") else "IMPORTED", total_rows=1)
        db.add(run)
        db.flush()
        community = db.scalar(select(Community).where(Community.workspace_id == workspace_id,
                                                      Community.external_id == payload["external_id"]))
        if payload.get("dry_run"):
            run.status = "DRY_RUN"
        else:
            if community is None:
                community = Community(workspace_id=workspace_id, platform="TELEGRAM", classification_status="NEEDS_REVIEW", classification_source="PENDING_MANUAL_TRIAGE", classification_confidence=0, classification_reason="Awaiting manual dialog triage", **{
                    key: payload.get(key) for key in ("external_id", "title", "username", "url", "description", "language", "geography", "category", "rules_text", "rules_url", "allowed_content_types", "allowed_days", "min_interval_hours", "valid_from", "valid_until", "evidence", "evidence_url", "notes")
                })
                db.add(community)
            else:
                for key in ("title", "username", "url", "description", "rules_text", "rules_url", "allowed_content_types", "allowed_days", "min_interval_hours", "valid_from", "valid_until", "evidence", "evidence_url", "notes"):
                    if payload.get(key) is not None:
                        setattr(community, key, payload[key])
            run.imported_rows = 1
        audit(db, workspace_id=workspace_id, actor_id=actor.id, action="telegram.community.imported",
              entity_type="TelegramImportRun", entity_id=run.id,
              after={"status": run.status, "permission_created": False})
        db.commit()
        return {"run_id": run.id, "status": run.status, "imported": run.imported_rows, "community_id": getattr(community, "id", None), "permission_created": False}

    def import_rows(self, db: Session, *, workspace_id: str, actor: User,
                    rows: list[dict[str, Any]], idempotency_key: str, account_id: str | None,
                    dry_run: bool) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        imported = 0
        for index, row in enumerate(rows):
            if not row.get("title") or not row.get("external_id"):
                errors.append({"row": index + 1, "error": "title and external_id are required"})
                continue
            if not dry_run:
                self.import_community(db, workspace_id=workspace_id, actor=actor, payload={**row, "account_id": account_id, "idempotency_key": f"{idempotency_key}:{index}", "dry_run": False})
            imported += 1
        return {"status": "DRY_RUN" if dry_run else "IMPORTED", "total_rows": len(rows), "imported_rows": imported, "error_rows": len(errors), "errors": errors}

    def discover(self, db: Session, *, profile: TelegramAccountProfile, actor: User,
                 query: str, discovery_profile_id: str | None = None) -> list[TelegramCommunityCandidate]:
        self._require_authorized(profile)
        query_terms = [term.lower() for term in re.findall(r"[\wА-Яа-я-]+", query) if len(term) > 2]
        dialogs = _run(self._client_for_profile(profile).search_communities(query))
        run = TelegramDiscoveryRun(workspace_id=profile.workspace_id, integration_account_id=profile.integration_account_id,
                                   discovery_profile_id=discovery_profile_id, search_query=query, status="SUCCEEDED")
        db.add(run)
        db.flush()
        candidates: list[TelegramCommunityCandidate] = []
        for item in dialogs:
            haystack = " ".join(filter(None, [item.title, item.username, item.description, item.geography, item.category])).lower()
            score = min(1.0, sum(term in haystack for term in query_terms) / max(1, len(query_terms)))
            if score <= 0:
                continue
            candidate = db.scalar(select(TelegramCommunityCandidate).where(
                TelegramCommunityCandidate.workspace_id == profile.workspace_id,
                TelegramCommunityCandidate.external_id == item.external_id,
            ))
            values = {"workspace_id": profile.workspace_id, "discovery_run_id": run.id, "external_id": item.external_id,
                      "title": item.title, "username": item.username, "url": f"https://t.me/{item.username}" if item.username else None,
                      "source": "MOCK", "search_query": query, "relevance_score": score, "activity_score": min(1.0, (item.member_count or 0) / 10000),
                      "geography": item.geography, "language": item.language, "category": item.category,
                      "reason": f"Matched query terms: {', '.join(query_terms)}", "review_status": "NEW"}
            if candidate is None:
                candidate = TelegramCommunityCandidate(**values)
                db.add(candidate)
            else:
                for key, value in values.items():
                    setattr(candidate, key, value)
            candidates.append(candidate)
        run.result_count = len(candidates)
        run.completed_at = datetime.utcnow()
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.discovery.completed",
              entity_type="TelegramDiscoveryRun", entity_id=run.id, after={"count": len(candidates), "joined_any": False})
        db.commit()
        return candidates

    def search_global_messages(self, *, profile: TelegramAccountProfile, query: str, limit: int = 100):
        self._require_authorized(profile)
        return _run(self._client_for_profile(profile).search_global_messages(query, limit))

    def read_public_community_messages(self, *, profile: TelegramAccountProfile, usernames: list[str], limit: int = 20):
        self._require_authorized(profile)
        return _run(self._client_for_profile(profile).read_public_community_messages(usernames, limit))

    def search_communities(self, *, profile: TelegramAccountProfile, query: str):
        self._require_authorized(profile)
        return _run(self._client_for_profile(profile).search_communities(query))

    def search_global_communities(self, *, profile: TelegramAccountProfile, query: str, limit: int = 100):
        self._require_authorized(profile)
        return _run(self._client_for_profile(profile).search_global_communities(query, limit))

    def search_global_communities_batch(self, *, profile: TelegramAccountProfile, queries: list[str], limit: int = 100):
        self._require_authorized(profile)
        return _run(self._client_for_profile(profile).search_global_communities_batch(queries, limit))

    def update_dialog_folder(self, *, profile: TelegramAccountProfile, title: str, usernames: list[str]) -> int:
        self._require_authorized(profile)
        return _run(self._client_for_profile(profile).update_dialog_folder(title, usernames))

    def enrich_community_metadata(self, *, profile: TelegramAccountProfile, usernames: list[str]):
        self._require_authorized(profile)
        return _run(self._client_for_profile(profile).enrich_community_metadata(usernames))

    def join_public_community(self, db: Session, *, profile: TelegramAccountProfile,
                              username: str, actor: User) -> TelegramDialog:
        self._require_authorized(profile)
        item = _run(self._client_for_profile(profile).join_public_community(username))
        now = datetime.utcnow()
        dialog = db.scalar(select(TelegramDialog).where(
            TelegramDialog.integration_account_id == profile.integration_account_id,
            TelegramDialog.external_dialog_id == item.external_id,
        ))
        values = {
            "workspace_id": profile.workspace_id,
            "integration_account_id": profile.integration_account_id,
            "external_dialog_id": item.external_id,
            "dialog_type": item.dialog_type,
            "title": item.title,
            "username": item.username,
            "is_public": True,
            "is_joined": True,
            "can_send_messages": item.can_send_messages,
            "can_view_history": item.can_view_history,
            "has_slow_mode": item.slow_mode_seconds is not None,
            "slow_mode_seconds": item.slow_mode_seconds,
            "member_count": item.member_count,
            "last_synced_at": now,
            "raw_metadata_sanitized": {"description": item.description, "category": item.category},
        }
        if dialog is None:
            dialog = TelegramDialog(**values)
            db.add(dialog)
            db.flush()
        else:
            for key, value in values.items():
                setattr(dialog, key, value)
        community = db.scalar(select(Community).where(
            Community.workspace_id == profile.workspace_id,
            Community.external_id == item.external_id,
        ))
        community_values = {
            "workspace_id": profile.workspace_id,
            "platform": "TELEGRAM",
            "external_id": item.external_id,
            "title": item.title or item.external_id,
            "username": item.username,
            "url": f"https://t.me/{item.username}" if item.username else None,
            "description": item.description,
            "language": item.language or "ru",
            "member_count": item.member_count or 0,
        }
        if community is None:
            community = Community(**community_values, classification_status="NEEDS_REVIEW",
                                   classification_source="JOINED_PUBLIC_COMMUNITY",
                                   classification_confidence=0,
                                   classification_reason="Joined for operator review")
            db.add(community)
            db.flush()
        elif not community.manual_classification_override:
            for key, value in community_values.items():
                if key != "workspace_id" and value is not None:
                    setattr(community, key, value)
        dialog.community_id = community.id
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id,
              action="telegram.community.joined",
              entity_type="TelegramDialog", entity_id=dialog.id,
              after={"username": item.username, "member_count": item.member_count,
                     "can_send_messages": item.can_send_messages})
        db.commit()
        db.refresh(dialog)
        return dialog

    def decide_candidate(self, db: Session, *, candidate: TelegramCommunityCandidate, status: str, actor: User) -> TelegramCommunityCandidate:
        candidate.review_status = status
        audit(db, workspace_id=candidate.workspace_id, actor_id=actor.id, action=f"telegram.discovery.candidate_{status.lower()}",
              entity_type="TelegramCommunityCandidate", entity_id=candidate.id, after={"review_status": status})
        db.commit()
        return candidate

    def sync_rules(self, db: Session, *, profile: TelegramAccountProfile, community: Community, actor: User) -> TelegramCommunitySnapshot:
        self._require_authorized(profile)
        dialogs = _run(self._client_for_profile(profile).get_dialogs())
        dialog = next((item for item in dialogs if item.external_id == community.external_id or item.username == community.username), None)
        if dialog is None:
            raise ValueError("COMMUNITY_NOT_AVAILABLE_TO_ACCOUNT")
        metadata_hash = hashlib.sha256(("|".join(map(str, [dialog.title, dialog.rules_text, dialog.pinned_message_text, dialog.slow_mode_seconds, dialog.can_send_messages, dialog.can_view_history]))).encode()).hexdigest()
        latest = db.scalar(select(TelegramCommunitySnapshot).where(
            TelegramCommunitySnapshot.community_id == community.id,
            TelegramCommunitySnapshot.integration_account_id == profile.integration_account_id,
        ).order_by(TelegramCommunitySnapshot.observed_at.desc()))
        snapshot = db.scalar(select(TelegramCommunitySnapshot).where(
            TelegramCommunitySnapshot.community_id == community.id,
            TelegramCommunitySnapshot.integration_account_id == profile.integration_account_id,
            TelegramCommunitySnapshot.metadata_hash == metadata_hash,
        ))
        changed = latest is not None and latest.metadata_hash != metadata_hash
        if snapshot is None:
            snapshot = TelegramCommunitySnapshot(community_id=community.id, integration_account_id=profile.integration_account_id,
                title=dialog.title, username=dialog.username, description=dialog.description, member_count=dialog.member_count,
                rules_text=dialog.rules_text, pinned_message_text=dialog.pinned_message_text, slow_mode_seconds=dialog.slow_mode_seconds,
                can_send_messages=dialog.can_send_messages, can_view_history=dialog.can_view_history,
                public_link=f"https://t.me/{dialog.username}" if dialog.username else None, metadata_hash=metadata_hash)
            db.add(snapshot)
            db.flush()
        community.rules_text = dialog.rules_text
        community.member_count = dialog.member_count or 0
        if changed:
            community.posting_status = "NEEDS_REVIEW"
            for permission in db.scalars(select(CommunityPermission).where(CommunityPermission.community_id == community.id, CommunityPermission.status == "ACTIVE")):
                permission.status = "REVIEW_REQUIRED"
            for publication in db.scalars(select(Publication).where(Publication.community_id == community.id, Publication.status.in_(["DRAFT", "QUEUED"]))):
                publication.status = "BLOCKED_BY_POLICY"
            audit(db, workspace_id=community.workspace_id, actor_id=actor.id, action="telegram.rules.changed",
                  entity_type="Community", entity_id=community.id, after={"permission_review_required": True})
        audit(db, workspace_id=community.workspace_id, actor_id=actor.id, action="telegram.rules.synced",
              entity_type="TelegramCommunitySnapshot", entity_id=snapshot.id, after={"changed": changed})
        db.commit()
        db.refresh(snapshot)
        return snapshot

    def analyze_rules(self, db: Session, *, community: Community, actor: User) -> TelegramRuleAnalysis:
        text = normalize_text(community.rules_text or "")
        analysis = TelegramRuleAnalysis(
            community_id=community.id,
            advertising_allowed=not any(term in text for term in ("реклама запрещена", "no advertising", "любая реклама запрещена")),
            companion_search_allowed=any(term in text for term in ("попутчик", "companion", "travel posts welcome")),
            event_posts_allowed=any(term in text for term in ("анонс", "мероприяти", "event")),
            external_links_allowed="ссылки" in text or "links" in text,
            images_allowed="изображ" in text or "image" in text,
            admin_approval_required=any(term in text for term in ("согласован", "approval", "администратор")),
            paid_placement_required="рекламный день" in text,
            allowed_days=["FRIDAY"] if "пятниц" in text or "friday" in text else None,
            minimum_interval=60 if "slow mode 60" in text else None,
            maximum_length=None,
            forbidden_topics=["unsolicited advertising"] if "запрещ" in text or "no unsolicited" in text else [],
            required_format=None,
            confidence=0.85 if text else 0.1,
            evidence_fragments=[community.rules_text] if community.rules_text else [],
            review_status="PENDING",
        )
        db.add(analysis)
        db.flush()
        audit(db, workspace_id=community.workspace_id, actor_id=actor.id, action="telegram.rules.analysis_created",
              entity_type="TelegramRuleAnalysis", entity_id=analysis.id, after={"approved": False})
        db.commit()
        return analysis

    def review_rules(self, db: Session, *, community: Community, actor: User, approved: bool,
                     allowed_content_types: list[str], allowed_days: list[str], min_interval_hours: int,
                     expires_at: datetime | None) -> CommunityPermission | None:
        analysis = db.scalar(select(TelegramRuleAnalysis).where(TelegramRuleAnalysis.community_id == community.id).order_by(TelegramRuleAnalysis.created_at.desc()))
        if analysis:
            analysis.review_status = "APPROVED" if approved else "REJECTED"
        if not approved:
            community.posting_status = "REJECTED"
            db.commit()
            return None
        permission = db.scalar(select(CommunityPermission).where(CommunityPermission.community_id == community.id))
        if permission is None:
            permission = CommunityPermission(workspace_id=community.workspace_id, community_id=community.id, permission_type="POST")
            db.add(permission)
            db.flush()
        permission.status = "ACTIVE"
        permission.approved_by = actor.id
        permission.reviewed_by = actor.id
        permission.reviewed_at = datetime.utcnow()
        permission.expires_at = expires_at
        permission.allowed_content_types = allowed_content_types
        permission.allowed_days = allowed_days
        permission.min_interval_hours = min_interval_hours
        community.posting_status = "APPROVED"
        audit(db, workspace_id=community.workspace_id, actor_id=actor.id, action="telegram.rules.permission_approved",
              entity_type="CommunityPermission", entity_id=permission.id, after={"approved": True, "human_review": True})
        db.commit()
        return permission

    def sync_messages(self, db: Session, *, profile: TelegramAccountProfile, dialog: TelegramDialog,
                      actor: User, max_messages: int, since: datetime | None = None) -> list[TelegramMessageRecord]:
        self._require_authorized(profile)
        rows = _run(self._client_for_profile(profile).get_messages(dialog.external_dialog_id, max_messages, since))
        result: list[TelegramMessageRecord] = []
        for item in rows:
            content = item.text or ""
            content_hash = hashlib.sha256(normalize_text(content).encode()).hexdigest()
            record = db.scalar(select(TelegramMessageRecord).where(
                TelegramMessageRecord.integration_account_id == profile.integration_account_id,
                TelegramMessageRecord.external_dialog_id == item.dialog_external_id,
                TelegramMessageRecord.external_message_id == item.external_id,
            ))
            values = {"workspace_id": profile.workspace_id, "integration_account_id": profile.integration_account_id,
                      "community_id": dialog.community_id, "external_dialog_id": item.dialog_external_id,
                      "external_message_id": item.external_id, "sender_external_id": item.sender_external_id,
                      "sender_username": item.sender_username, "sender_display_name": item.sender_display_name,
                      "direction": item.direction, "message_type": "TEXT", "text": item.text,
                      "normalized_text": normalize_text(content), "reply_to_external_message_id": item.reply_to_external_id,
                      "sent_at": item.sent_at, "edited_at": item.edited_at, "deleted_at": item.deleted_at,
                      "source": "MOCK", "content_hash": content_hash}
            if record is None:
                record = TelegramMessageRecord(**values)
                db.add(record)
            else:
                for key, value in values.items():
                    setattr(record, key, value)
            result.append(record)
        cursor = db.scalar(select(TelegramSyncCursor).where(TelegramSyncCursor.integration_account_id == profile.integration_account_id,
                                                            TelegramSyncCursor.dialog_id == dialog.id, TelegramSyncCursor.sync_type == "MESSAGES"))
        if cursor is None:
            cursor = TelegramSyncCursor(integration_account_id=profile.integration_account_id, dialog_id=dialog.id, sync_type="MESSAGES")
            db.add(cursor)
        cursor.cursor_value = str(len(rows))
        cursor.last_external_message_id = rows[-1].external_id if rows else cursor.last_external_message_id
        cursor.last_synced_at = datetime.utcnow()
        cursor.status = "SUCCEEDED"
        cursor.last_error = None
        dialog.last_message_external_id = cursor.last_external_message_id
        dialog.last_synced_at = datetime.utcnow()
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.messages.synced",
              entity_type="TelegramDialog", entity_id=dialog.id, after={"count": len(result), "attachments_downloaded": False})
        db.commit()
        return result

    def ingest_global_messages(self, db: Session, *, profile: TelegramAccountProfile,
                               actor: User, rows: list[Any]) -> set[str]:
        """Persist messages returned by global public search without joining chats."""
        dialog_ids: set[str] = set()
        for item in rows:
            dialog_ids.add(item.dialog_external_id)
            dialog = db.scalar(select(TelegramDialog).where(
                TelegramDialog.integration_account_id == profile.integration_account_id,
                TelegramDialog.external_dialog_id == item.dialog_external_id,
            ))
            if dialog is None:
                dialog = TelegramDialog(
                    workspace_id=profile.workspace_id,
                    integration_account_id=profile.integration_account_id,
                    external_dialog_id=item.dialog_external_id,
                    dialog_type=item.dialog_type,
                    title=item.dialog_title or item.dialog_external_id,
                    username=item.dialog_username,
                    is_public=item.dialog_is_public,
                    is_joined=False,
                    can_send_messages=False,
                    can_view_history=False,
                )
                db.add(dialog)
                db.flush()
            community = db.scalar(select(Community).where(
                Community.workspace_id == profile.workspace_id,
                Community.external_id == item.dialog_external_id,
            ))
            if community is None:
                community = Community(
                    workspace_id=profile.workspace_id,
                    platform="TELEGRAM",
                    external_id=item.dialog_external_id,
                    title=item.dialog_title or item.dialog_external_id,
                    username=item.dialog_username,
                    url=f"https://t.me/{item.dialog_username}" if item.dialog_username else None,
                    language="ru",
                    classification_status="NEEDS_REVIEW",
                    classification_source="GLOBAL_MESSAGE_SEARCH",
                )
                db.add(community)
                db.flush()
            dialog.community_id = community.id
            record = db.scalar(select(TelegramMessageRecord).where(
                TelegramMessageRecord.integration_account_id == profile.integration_account_id,
                TelegramMessageRecord.external_dialog_id == item.dialog_external_id,
                TelegramMessageRecord.external_message_id == item.external_id,
            ))
            content = item.text or ""
            values = {
                "workspace_id": profile.workspace_id,
                "integration_account_id": profile.integration_account_id,
                "community_id": community.id,
                "external_dialog_id": item.dialog_external_id,
                "external_message_id": item.external_id,
                "sender_external_id": item.sender_external_id,
                "sender_username": item.sender_username,
                "sender_display_name": item.sender_display_name,
                "direction": item.direction,
                "message_type": "TEXT",
                "text": item.text,
                "normalized_text": normalize_text(content),
                "sent_at": item.sent_at,
                "source": "LIVE_GLOBAL_SEARCH",
                "content_hash": hashlib.sha256(normalize_text(content).encode()).hexdigest(),
            }
            if record is None:
                db.add(TelegramMessageRecord(**values))
            else:
                for key, value in values.items():
                    setattr(record, key, value)
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id,
              action="telegram.global_messages.ingested",
              entity_type="TelegramAccountProfile", entity_id=profile.id,
              after={"messages": len(rows), "dialogs": len(dialog_ids), "joined_any": False})
        db.commit()
        return dialog_ids

    def discover_leads(self, db: Session, *, profile: TelegramAccountProfile, actor: User,
                       campaign_id: str | None = None, dialog_id: str | None = None,
                       dialog_external_ids: set[str] | None = None,
                       message_external_ids: set[str] | None = None,
                       max_messages: int = 100) -> list[Lead]:
        query = select(TelegramMessageRecord).where(TelegramMessageRecord.workspace_id == profile.workspace_id)
        if dialog_id:
            dialog = db.get(TelegramDialog, dialog_id)
            if dialog:
                query = query.where(TelegramMessageRecord.external_dialog_id == dialog.external_dialog_id)
        if dialog_external_ids is not None:
            if not dialog_external_ids:
                return []
            query = query.where(TelegramMessageRecord.external_dialog_id.in_(dialog_external_ids))
        if message_external_ids is not None:
            if not message_external_ids:
                return []
            query = query.where(TelegramMessageRecord.external_message_id.in_(message_external_ids))
        messages = list(db.scalars(query.order_by(TelegramMessageRecord.sent_at.desc()).limit(max_messages)).all())
        leads: list[Lead] = []
        campaign = db.get(Campaign, campaign_id) if campaign_id else None
        for message in messages:
            text = normalize_text(message.text or "")
            promotional_terms = ("\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f", "\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c", "\u0432\u043e\u0440\u043a\u0448\u043e\u043f", "\u043c\u0438\u0442\u0430\u043f", "\u043a\u0443\u0440\u0441", "\u0437\u0430\u043d\u044f\u0442\u0438\u0435", "\u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430", "\u043a\u0442\u043e \u0432\u0435\u0434\u0435\u0442", "\u0434\u043b\u044f \u043a\u043e\u0433\u043e", "\u043e\u043f\u043b\u0430\u0442\u0430 \u043d\u0430 \u043c\u0435\u0441\u0442\u0435", "\u043c\u0435\u0441\u0442 \u043c\u0430\u043b\u043e")
            if any(term in text.casefold() for term in promotional_terms):
                continue
            if any(term in text.casefold() for term in ("\u0435\u0441\u0442\u044c \u043c\u0435\u0441\u0442\u0430", "\u043c\u0435\u0441\u0442\u0430 \u0435\u0441\u0442\u044c")) and not any(term in text.casefold() for term in ("\u043d\u0443\u0436\u0435\u043d", "\u043d\u0443\u0436\u043d\u0430", "\u043d\u0443\u0436\u043d\u043e", "\u0438\u0449\u0443", "\u043f\u043e\u0441\u043e\u0432\u0435\u0442\u0443\u0439\u0442\u0435")):
                continue
            if not text or any(term in text for term in ("реклама запрещена", "спам", "вакансия")):
                continue
            signals: list[str] = []
            breakdown: dict[str, int] = {}
            if message.source == "LIVE_GLOBAL_SEARCH":
                signals.append("DIRECT_REQUEST")
                breakdown["direct_request"] = 35
            elif any(term in text.casefold() for term in ("нужен", "нужна", "нужно", "ищу", "кто может", "порекомендуйте")):
                signals.append("DIRECT_REQUEST")
                breakdown["direct_request"] = 35
            if any(term in text.casefold() for term in ("\u0441\u0440\u043e\u0447\u043d\u043e", "\u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0439 \u043d\u0435\u0434\u0435\u043b\u0435", "\u0432 \u044d\u0442\u0438 \u0432\u044b\u0445\u043e\u0434\u043d\u044b\u0435")):
                signals.append("URGENCY")
                breakdown["urgency"] = 15
                community = db.get(Community, message.community_id)
                if community and community.geography and any(term in text for term in normalize_text(community.geography).split()):
                    signals.append("GEOGRAPHY_MATCH")
                    breakdown["geography"] = 25
            if not signals:
                continue
            score = sum(breakdown.values())
            existing_key = dedupe_key(
                author_username=message.sender_username,
                normalized_text=text,
                source_platform="TELEGRAM",
                campaign_id=campaign_id,
            )
            existing_query = select(Lead).where(
                Lead.workspace_id == profile.workspace_id,
                Lead.dedupe_key == existing_key,
            )
            if campaign_id:
                existing_query = existing_query.where(Lead.campaign_id == campaign_id)
            else:
                existing_query = existing_query.where(Lead.campaign_id.is_(None))
            existing = db.scalar(existing_query)
            if existing:
                if existing.source_message_id is None:
                    existing.source_message_id = message.external_message_id
                    existing.source_dialog_external_id = message.external_dialog_id
                    existing.source_message_url = self._message_url(
                        db.get(Community, message.community_id) if message.community_id else None,
                        message.external_dialog_id,
                        message.external_message_id,
                    )
                leads.append(existing)
                continue
            community = db.get(Community, message.community_id) if message.community_id else None
            source_message_url = self._message_url(community, message.external_dialog_id, message.external_message_id)
            lead = Lead(workspace_id=profile.workspace_id, campaign_id=campaign.id if campaign else None,
                source_platform="TELEGRAM", source_url=community.url if community else None,
                source_message_id=message.external_message_id,
                source_dialog_external_id=message.external_dialog_id,
                source_message_url=source_message_url,
                source_community_id=message.community_id, author_name=message.sender_display_name,
                author_username=message.sender_username, raw_text=message.text or "", normalized_text=text,
                detected_need="; ".join(signals), lead_type="INBOUND", score=min(100, score), confidence=min(1, score / 100),
                status="NEW", dedupe_key=existing_key, score_breakdown=breakdown, matched_signals=signals,
                excluded_signals=[], explanation=f"Matched signals: {', '.join(signals)}",
                recommended_action="Review publicly; do not send unsolicited DM", can_reply_publicly=True,
                contact_initiated=False, direct_message_allowed=False, model_version="telegram-rules-v1", evaluated_at=datetime.utcnow())
            db.add(lead)
            leads.append(lead)
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.leads.discovered",
              entity_type="TelegramAccountProfile", entity_id=profile.id, after={"count": len(leads), "automatic_dm": False})
        db.commit()
        return leads

    @staticmethod
    def _message_url(community: Community | None, dialog_external_id: str | None,
                     message_external_id: str | None) -> str | None:
        """Build a real Telegram message URL only when Telegram identifiers support it."""
        if not message_external_id:
            return None
        message_id = str(message_external_id)
        if not message_id.isdigit():
            return None
        if community and community.username:
            return f"https://t.me/{community.username.lstrip('@')}/{message_id}"
        if dialog_external_id and str(dialog_external_id).lstrip('-').isdigit():
            dialog_id = str(dialog_external_id).lstrip('-')
            if dialog_id.startswith("100"):
                dialog_id = dialog_id[3:]
            return f"https://t.me/c/{dialog_id}/{message_id}"
        return None

    def sync_incoming(self, db: Session, *, profile: TelegramAccountProfile, actor: User,
                      dialog_id: str | None = None, max_messages: int = 100) -> list[Conversation]:
        query = select(TelegramMessageRecord).where(TelegramMessageRecord.workspace_id == profile.workspace_id,
                                                    TelegramMessageRecord.direction == "INBOUND")
        if dialog_id:
            dialog = db.get(TelegramDialog, dialog_id)
            if dialog:
                query = query.where(TelegramMessageRecord.external_dialog_id == dialog.external_dialog_id)
        conversations: list[Conversation] = []
        for record in db.scalars(query.order_by(TelegramMessageRecord.sent_at.desc()).limit(max_messages)):
            external_chat = f"telegram:{record.external_dialog_id}:{record.sender_external_id or 'unknown'}"
            conversation = db.scalar(select(Conversation).where(Conversation.workspace_id == profile.workspace_id,
                                                                   Conversation.external_chat_id == external_chat))
            if conversation is None:
                conversation = Conversation(workspace_id=profile.workspace_id, external_chat_id=external_chat, status="OPEN",
                                            last_message_at=record.sent_at)
                db.add(conversation)
                db.flush()
            record.conversation_id = conversation.id
            duplicate = db.scalar(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id,
                                                                     ConversationMessage.external_message_id == record.external_message_id))
            if duplicate is None:
                db.add(ConversationMessage(conversation_id=conversation.id, direction="INBOUND",
                                           sender=record.sender_display_name or record.sender_username or "Telegram user",
                                           content=record.text or "", external_message_id=record.external_message_id,
                                           sent_at=record.sent_at))
            conversation.last_message_at = record.sent_at
            conversations.append(conversation)
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.incoming.synced",
              entity_type="TelegramAccountProfile", entity_id=profile.id, after={"count": len(conversations), "auto_reply": False})
        db.commit()
        return conversations

    def create_incident(self, db: Session, *, profile: TelegramAccountProfile, incident_type: str,
                        severity: str, details: dict[str, Any], actor: User | None = None,
                        retry_after_seconds: int | None = None) -> TelegramAccountIncident:
        now = datetime.utcnow()
        incident = TelegramAccountIncident(integration_account_id=profile.integration_account_id,
            incident_type=incident_type, severity=severity, source="MOCK", sanitized_details=details, detected_at=now)
        db.add(incident)
        db.flush()
        profile.manual_unlock_required = True
        profile.safety_status = "FLOOD_WAIT" if incident_type == "FLOOD_WAIT" else "SAFETY_LOCK"
        if incident_type == "FLOOD_WAIT" and retry_after_seconds:
            profile.flood_wait_until = now + timedelta(seconds=retry_after_seconds)
        integration = db.get(IntegrationAccount, profile.integration_account_id)
        if integration:
            integration.safety_lock = True
            integration.safety_status = profile.safety_status
            integration.health_status = "UNHEALTHY"
            integration.flood_wait_until = profile.flood_wait_until
        if actor:
            audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.incident.created",
                  entity_type="TelegramAccountIncident", entity_id=incident.id,
                  after={"incident_type": incident_type, "safety_lock": True})
        db.commit()
        return incident

    def resolve_incident(self, db: Session, *, incident: TelegramAccountIncident, actor: User,
                         resolution_notes: str) -> TelegramAccountIncident:
        incident.status = "RESOLVED"
        incident.resolved_at = datetime.utcnow()
        incident.resolved_by = actor.id
        incident.resolution_notes = resolution_notes
        audit(db, workspace_id=self.profile_for_integration(db, incident.integration_account_id).workspace_id,
              actor_id=actor.id, action="telegram.incident.resolved", entity_type="TelegramAccountIncident",
              entity_id=incident.id, after={"manual_resolution": True})
        db.commit()
        return incident

    def unlock(self, db: Session, *, profile: TelegramAccountProfile, actor: User) -> bool:
        if profile.flood_wait_until and profile.flood_wait_until > datetime.utcnow():
            raise ValueError("FLOOD_WAIT_ACTIVE")
        profile.manual_unlock_required = False
        profile.safety_status = "HEALTHY"
        profile.connection_status = "CONNECTED" if profile.authorization_status == "AUTHORIZED" else "DISCONNECTED"
        integration = db.get(IntegrationAccount, profile.integration_account_id)
        if integration:
            integration.safety_lock = False
            integration.safety_status = "HEALTHY"
            integration.health_status = "HEALTHY"
        audit(db, workspace_id=profile.workspace_id, actor_id=actor.id, action="telegram.account.manual_unlock",
              entity_type="TelegramAccountProfile", entity_id=profile.id, after={"manual_unlock": True})
        db.commit()
        return True

    @staticmethod
    def _require_authorized(profile: TelegramAccountProfile) -> None:
        if profile.authorization_status != "AUTHORIZED":
            raise ValueError("TELEGRAM_ACCOUNT_NOT_AUTHORIZED")
        if profile.manual_unlock_required or profile.safety_status in {"FLOOD_WAIT", "SAFETY_LOCK", "SPAM_WARNING", "RESTRICTED", "REVOKED"}:
            raise ValueError("TELEGRAM_ACCOUNT_SAFETY_LOCKED")

    def create_forum_topic(self, *, profile: TelegramAccountProfile, target: str, title: str) -> str:
        self._require_authorized(profile)
        client = self._client_for_profile(profile)
        if not hasattr(client, "create_forum_topic"):
            raise RuntimeError("TELEGRAM_FORUM_TOPICS_UNAVAILABLE")
        return _run(client.create_forum_topic(target, title))

    def send_operator_notification(self, *, profile: TelegramAccountProfile, content: str, target: str | None = None, thread_id: str | None = None) -> str | None:
        settings = get_settings()
        if not settings.telegram_operator_notifications_enabled:
            return None
        self._require_authorized(profile)
        client = self._client_for_profile(profile)
        if target:
            return _run(client.send_message(target, content, f"operator:{profile.id}:{hashlib.sha256(content.encode()).hexdigest()}", thread_id=thread_id))
        if not hasattr(client, "send_self_message"):
            return None
        return _run(client.send_self_message(content))
