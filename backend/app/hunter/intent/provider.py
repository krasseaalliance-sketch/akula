from __future__ import annotations

from typing import Protocol

from ..models import IntentResult, NormalizedSignal
from .rules import RulesIntentProvider


class IntentProvider(Protocol):
    def analyze(self, signal: NormalizedSignal) -> IntentResult: ...


class FallbackIntentProvider:
    """Provider-neutral boundary with a deterministic offline fallback."""

    def __init__(self, primary: IntentProvider, fallback: IntentProvider | None = None):
        self.primary = primary
        self.fallback = fallback or RulesIntentProvider()

    def analyze(self, signal: NormalizedSignal) -> IntentResult:
        try:
            result = self.primary.analyze(signal)
            if not isinstance(result, IntentResult):
                raise TypeError("INTENT_PROVIDER_MALFORMED_OUTPUT")
            return result
        except (TimeoutError, ValueError, RuntimeError, TypeError, KeyError):
            return self.fallback.analyze(signal)
