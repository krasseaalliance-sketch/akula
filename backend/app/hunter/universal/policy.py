from __future__ import annotations

from .engine import BusinessUnderstandingEngine
from .models import BusinessInput, PolicyDecision


def evaluate_business_policy(input_data: BusinessInput) -> PolicyDecision:
    return BusinessUnderstandingEngine().understand(input_data).policy_decision
