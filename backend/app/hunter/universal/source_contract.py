from __future__ import annotations

from dataclasses import dataclass

from .models import DemandModel, SourceStrategy


@dataclass(frozen=True)
class SourceHubDemandContract:
    business_id: str
    demand_model_id: str
    preferred_source_classes: tuple[str, ...]
    freshness_required: str
    cadence_minutes: int
    activation: str = "READ_ONLY_CONTRACT_ONLY"
    writes_allowed: bool = False


def to_source_hub_contract(demand: DemandModel, strategy: SourceStrategy) -> SourceHubDemandContract:
    return SourceHubDemandContract(demand.business_id, demand.demand_model_id, strategy.preferred, strategy.freshness_required, strategy.cadence_minutes)
