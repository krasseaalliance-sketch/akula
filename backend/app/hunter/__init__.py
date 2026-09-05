"""Revenue-first Lead Hunter bounded context.

This package deliberately has no import path to the legacy publication or
Telegram sending adapters. It reads approved public signal captures and emits
tenant-neutral, explainable result records.
"""

from .pipeline import HunterPipeline
from .profiles.vitrina_services import VITRINA_SERVICES_V1

__all__ = ["VITRINA_SERVICES_V1", "HunterPipeline"]
