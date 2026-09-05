from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class FreshnessInfo:
    bucket: str
    age_hours: float | None
    confidence: str
    score_cap: int
    within_72h: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "bucket": self.bucket,
            "age_hours": self.age_hours,
            "age_days": round(self.age_hours / 24, 3) if self.age_hours is not None else None,
            "freshness_confidence": self.confidence,
            "score_cap": self.score_cap,
            "within_72h": self.within_72h,
        }


def classify_freshness(published_at: datetime | None, now: datetime) -> FreshnessInfo:
    if published_at is None:
        return FreshnessInfo("UNKNOWN", None, "LOW", 69, False)
    published = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    current = now if now.tzinfo else now.replace(tzinfo=UTC)
    age_hours = max(0.0, (current - published).total_seconds() / 3600)
    if age_hours <= 6:
        bucket, cap = "ULTRA_FRESH", 100
    elif age_hours <= 24:
        bucket, cap = "FRESH", 100
    elif age_hours <= 72:
        bucket, cap = "RECENT", 100
    elif age_hours <= 168:
        bucket, cap = "AGING", 69
    elif age_hours <= 720:
        bucket, cap = "STALE", 49
    else:
        bucket, cap = "DEAD", 39
    return FreshnessInfo(bucket, round(age_hours, 3), "HIGH", cap, age_hours <= 72)


def freshness_score(info: FreshnessInfo) -> int:
    if info.age_hours is None:
        return 0
    return max(0, round(100 - min(100, info.age_hours / (30 * 24) * 100)))


def apply_freshness_cap(score: int, info: FreshnessInfo) -> int:
    return min(score, info.score_cap)
