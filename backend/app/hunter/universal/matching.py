from __future__ import annotations

from typing import Any

from .models import MatchingProfile


def match_signal(profile: MatchingProfile, signal: dict[str, Any]) -> MatchingProfile:
    text = " ".join(str(signal.get(key) or "") for key in ("title", "text", "request"))
    blocking = list(profile.blocking_reasons)
    reasons = list(profile.matching_reasons)
    if any(token in text.casefold() for token in ("vacancy", "ищу работу", "продаю услугу")):
        blocking.append("negative intent pattern")
    else:
        reasons.append("signal does not match known negative patterns")
    penalty = 25 if blocking else 0
    return MatchingProfile(profile.business_id, max(0, profile.match_score - penalty), profile.intent_score, max(0, profile.commercial_fit_score - penalty), max(0, profile.priority_score - penalty), tuple(reasons), tuple(blocking), profile.confidence, profile.version)
