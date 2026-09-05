from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Publication, PublicationJob


def enqueue_publication(
    db: Session, publication: Publication, *, max_attempts: int = 3
) -> PublicationJob:
    job = db.scalar(select(PublicationJob).where(PublicationJob.publication_id == publication.id))
    if job is None:
        job = PublicationJob(
            publication_id=publication.id,
            idempotency_key=publication.idempotency_key or uuid4().hex,
            max_attempts=max_attempts,
        )
        db.add(job)
    publication.status = "QUEUED"
    publication.queued_at = datetime.utcnow()
    return job


def claim_next_job(db: Session) -> PublicationJob | None:
    job = db.scalar(
        select(PublicationJob)
        .where(PublicationJob.status == "QUEUED", PublicationJob.available_at <= datetime.utcnow())
        .order_by(PublicationJob.created_at)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "RUNNING"
    job.attempts += 1
    db.commit()
    return job


def notify_publication(job_id: str) -> None:
    """Announce a persisted job to Redis; the DB remains the source of truth."""
    from redis import Redis

    Redis.from_url(get_settings().redis_url, decode_responses=True).rpush("lead_hunter:publication_jobs", job_id)
