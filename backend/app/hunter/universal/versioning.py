from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .audit import ModelAuditEvent
from .contracts import ModelVersion, OperatorOverride, new_model_version


class ModelVersionStore:
    """Small append-only local ledger for Stage 3 model snapshots and audit events."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"models": [], "audit": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    def append(self, *, workspace_id: str, business_id: str, model: dict[str, Any], version: ModelVersion, audit_event: ModelAuditEvent) -> None:
        if not workspace_id or not business_id:
            raise ValueError("workspace_id and business_id are required")
        payload = self._read()
        payload["models"].append({"workspace_id": workspace_id, "business_id": business_id, "version": asdict(version), "model": model})
        payload["audit"].append({"workspace_id": workspace_id, **asdict(audit_event)})
        self._write(payload)

    def history(self, *, workspace_id: str, business_id: str) -> list[dict[str, Any]]:
        payload = self._read()
        return [row for row in payload["models"] if row["workspace_id"] == workspace_id and row["business_id"] == business_id]

    def override(self, *, workspace_id: str, override: OperatorOverride, model: dict[str, Any], new_version: str, audit_event: ModelAuditEvent) -> None:
        version = new_model_version("BusinessModel", new_version, (f"override:{override.field}",), supersedes=override.supersedes_version, reason=override.reason, manual_override=True)
        self.append(workspace_id=workspace_id, business_id=override.business_id, model=model, version=version, audit_event=audit_event)
