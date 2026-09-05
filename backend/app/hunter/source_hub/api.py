from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .hub import SourceHub
from .models import SourceAccount, SourceEndpoint


class SourceHubAdminAPI:
    """Internal service interface; intentionally not mounted as a public API router."""

    def __init__(self, hub: SourceHub):
        self.hub = hub

    def list_source_accounts(self) -> list[SourceAccount]:
        return self.hub.list_accounts()

    def list_endpoints(self, platform: str | None = None) -> list[SourceEndpoint]:
        return self.hub.list_endpoints(platform=platform)

    def add_endpoint(self, endpoint: SourceEndpoint, actor: str = "operator") -> SourceEndpoint:
        return self.hub.add_endpoint(endpoint, actor=actor)

    def enable(self, endpoint_id: str, actor: str = "operator") -> SourceEndpoint:
        return self.hub.enable_endpoint(endpoint_id, actor=actor)

    def disable(self, endpoint_id: str, actor: str = "operator") -> SourceEndpoint:
        return self.hub.disable_endpoint(endpoint_id, actor=actor)

    def test_read(self, endpoint_id: str, reader: Callable[[SourceEndpoint], dict[str, Any]] | None = None, actor: str = "operator") -> SourceEndpoint:
        return self.hub.test_read(endpoint_id, reader=reader, actor=actor)

    def endpoint_metrics(self, endpoint_id: str) -> dict[str, Any]:
        return self.hub.get_metrics(endpoint_id)
