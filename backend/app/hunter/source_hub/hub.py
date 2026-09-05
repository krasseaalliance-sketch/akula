from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import SourceAccount, SourceEndpoint
from .security import AuditEvent, block_outbound


class SourceHub:
    """Platform-neutral internal source registry with JSON persistence.

    The persisted file contains only credential/session references, never their
    values or session bodies. A production deployment can replace this store
    with a database without changing the account/endpoint service contract.
    """

    def __init__(self, path: str | Path | None = None, audit_path: str | Path | None = None):
        self.path = Path(path or ".source_hub/source_hub.json")
        self.audit_path = Path(audit_path or ".source_hub/audit.jsonl")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"version": 1, "accounts": {}, "endpoints": {}, "metrics": {}}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _audit(self, event: AuditEvent) -> None:
        self.audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def _admin_event(self, actor: str, action: str, account_id: str | None, endpoint_id: str | None, result: str, metadata: dict[str, Any] | None = None) -> None:
        self._audit(AuditEvent(actor, action, account_id, endpoint_id, datetime.now(UTC).isoformat(), result, metadata or {}))

    def add_account(self, account: SourceAccount, *, actor: str = "operator") -> SourceAccount:
        if not account.read_only or account.access_mode != "READ_ONLY":
            raise ValueError("Source Hub accounts must be READ_ONLY")
        self._state["accounts"][account.id] = account.to_dict()
        self._save()
        self._admin_event(actor, "ADD_ACCOUNT", account.id, None, "OK", {"platform": account.platform})
        return account

    def list_accounts(self) -> list[SourceAccount]:
        return [SourceAccount(**item) for item in self._state["accounts"].values()]

    def add_endpoint(self, endpoint: SourceEndpoint, *, actor: str = "operator") -> SourceEndpoint:
        if endpoint.source_account_id not in self._state["accounts"]:
            raise KeyError("source account not found")
        endpoint.discovery_state = "ACCESS_REVIEW"
        endpoint.enabled = False
        endpoint.scheduling_state = "PAUSED"
        self._state["endpoints"][endpoint.id] = endpoint.to_dict()
        self._save()
        self._admin_event(actor, "ADD_ENDPOINT", endpoint.source_account_id, endpoint.id, "ACCESS_REVIEW", {"platform": endpoint.platform})
        return endpoint

    def list_endpoints(self, *, platform: str | None = None) -> list[SourceEndpoint]:
        rows = [SourceEndpoint(**item) for item in self._state["endpoints"].values()]
        return [item for item in rows if platform is None or item.platform == platform]

    def get_endpoint(self, endpoint_id: str) -> SourceEndpoint:
        item = self._state["endpoints"].get(endpoint_id)
        if item is None:
            raise KeyError("source endpoint not found")
        return SourceEndpoint(**item)

    def test_read(self, endpoint_id: str, reader: Callable[[SourceEndpoint], dict[str, Any]] | None = None, *, actor: str = "operator") -> SourceEndpoint:
        endpoint = self.get_endpoint(endpoint_id)
        try:
            result = reader(endpoint) if reader else {"ok": True, "messages_scanned": 0}
            if not result.get("ok", True):
                raise RuntimeError(str(result.get("error") or "read test failed"))
            endpoint.discovery_state = "ACTIVE"
            endpoint.discovery_reason = None
            endpoint.operational_health = "HEALTHY"
            endpoint.last_success_at = datetime.now(UTC).isoformat()
            endpoint.last_scan_at = endpoint.last_success_at
            self._admin_event(actor, "TEST_READ", endpoint.source_account_id, endpoint.id, "PASS", {"messages_scanned": result.get("messages_scanned", 0)})
        except (OSError, RuntimeError, ValueError) as exc:
            endpoint.operational_health = "DEGRADED"
            endpoint.discovery_reason = "TEST_READ_FAILED"
            self._admin_event(actor, "TEST_READ", endpoint.source_account_id, endpoint.id, "FAIL", {"error_type": type(exc).__name__})
        self._state["endpoints"][endpoint.id] = endpoint.to_dict()
        self._save()
        return endpoint

    def enable_endpoint(self, endpoint_id: str, *, actor: str = "operator") -> SourceEndpoint:
        endpoint = self.get_endpoint(endpoint_id)
        if endpoint.discovery_state != "ACTIVE":
            raise ValueError("endpoint must pass TEST_READ before enable")
        endpoint.enabled = True
        endpoint.scheduling_state = "NORMAL"
        self._state["endpoints"][endpoint.id] = endpoint.to_dict()
        self._save()
        self._admin_event(actor, "ENABLE_ENDPOINT", endpoint.source_account_id, endpoint.id, "OK")
        return endpoint

    def disable_endpoint(self, endpoint_id: str, *, actor: str = "operator") -> SourceEndpoint:
        endpoint = self.get_endpoint(endpoint_id)
        endpoint.enabled = False
        endpoint.scheduling_state = "PAUSED"
        self._state["endpoints"][endpoint.id] = endpoint.to_dict()
        self._save()
        self._admin_event(actor, "DISABLE_ENDPOINT", endpoint.source_account_id, endpoint.id, "OK")
        return endpoint

    def mark_reauth_required(self, account_id: str, *, actor: str = "hunter-runtime") -> SourceAccount:
        item = self._state["accounts"].get(account_id)
        if item is None:
            raise KeyError("source account not found")
        account = SourceAccount(**item)
        account.status = "AUTH_REQUIRED"
        account.last_auth_failure_at = datetime.now(UTC).isoformat()
        account.updated_at = datetime.now(UTC).isoformat()
        self._state["accounts"][account.id] = account.to_dict()
        self._save()
        self._admin_event(actor, "REAUTH_REQUIRED", account_id, None, "OK")
        return account

    def mark_rate_limited(self, account_id: str, *, actor: str = "hunter-runtime") -> SourceAccount:
        item = self._state["accounts"].get(account_id)
        if item is None:
            raise KeyError("source account not found")
        account = SourceAccount(**item)
        account.status = "RATE_LIMITED"
        account.last_error = "RATE_LIMITED"
        account.updated_at = datetime.now(UTC).isoformat()
        self._state["accounts"][account.id] = account.to_dict()
        self._save()
        self._admin_event(actor, "RATE_LIMITED", account_id, None, "OK")
        return account

    def change_schedule(self, endpoint_id: str, scheduling_state: str, *, actor: str = "operator") -> SourceEndpoint:
        if scheduling_state not in {"FAST", "NORMAL", "SLOW", "PAUSED"}:
            raise ValueError("invalid scheduling state")
        endpoint = self.get_endpoint(endpoint_id)
        endpoint.scheduling_state = scheduling_state
        endpoint.enabled = scheduling_state != "PAUSED"
        self._state["endpoints"][endpoint.id] = endpoint.to_dict()
        self._save()
        self._admin_event(actor, "CHANGE_SCHEDULE", endpoint.source_account_id, endpoint.id, "OK", {"scheduling_state": scheduling_state})
        return endpoint

    def record_metrics(self, endpoint_id: str, metrics: dict[str, Any]) -> SourceEndpoint:
        endpoint = self.get_endpoint(endpoint_id)
        endpoint.metrics = {**endpoint.metrics, **metrics}
        endpoint.last_scan_at = datetime.now(UTC).isoformat()
        if metrics.get("last_seen_message_id") is not None:
            endpoint.last_seen_message_id = str(metrics["last_seen_message_id"])
        if metrics.get("last_cursor") is not None:
            endpoint.last_cursor = str(metrics["last_cursor"])
        self._state["endpoints"][endpoint.id] = endpoint.to_dict()
        self._save()
        return endpoint

    def get_metrics(self, endpoint_id: str) -> dict[str, Any]:
        return dict(self.get_endpoint(endpoint_id).metrics)

    def block_write(self, action: str, *, actor: str = "hunter-runtime", account_id: str | None = None, endpoint_id: str | None = None) -> None:
        block_outbound(action, actor=actor, source_account_id=account_id, endpoint_id=endpoint_id, audit_sink=self._audit)
