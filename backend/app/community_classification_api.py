from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user, require_perm
from .community_classification import CommunityClassificationEngine
from .db import get_db
from .models import Community, CommunityCollection, CommunityCollectionMembership, User
from .services import accessible_workspace_ids

router = APIRouter(prefix="/api/community-collections", tags=["community-classification"])
engine = CommunityClassificationEngine()


class ClassificationRunRequest(BaseModel):
    workspace_id: str


class ManualClassificationRequest(BaseModel):
    region: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None
    collection_slugs: list[str] = Field(default_factory=list)


def _workspace_ids(db: Session, user: User) -> list[str]:
    return accessible_workspace_ids(db, user.id)


@router.get("")
def list_collections(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(CommunityCollection).where(CommunityCollection.workspace_id.in_(_workspace_ids(db, user))).order_by(CommunityCollection.parent_id, CommunityCollection.name)).all())


@router.get("/dashboard")
def collection_dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    result: list[dict[str, Any]] = []
    for workspace_id in _workspace_ids(db, user):
        result.extend(engine.dashboard(db, workspace_id=workspace_id))
    db.commit()
    return result


@router.post("/classify")
def classify_workspace(payload: ClassificationRunRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.workspace_id not in _workspace_ids(db, user):
        raise HTTPException(status_code=404, detail="Workspace not found")
    require_perm(db, user, payload.workspace_id, "lead.edit")
    return engine.classify_workspace(db, workspace_id=payload.workspace_id, actor_id=user.id)


@router.get("/{slug}/communities")
def collection_communities(slug: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    collection = db.scalar(select(CommunityCollection).where(
        CommunityCollection.slug == slug,
        CommunityCollection.workspace_id.in_(_workspace_ids(db, user)),
    ))
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return list(db.scalars(select(Community).join(CommunityCollectionMembership, CommunityCollectionMembership.community_id == Community.id).where(CommunityCollectionMembership.collection_id == collection.id).order_by(Community.title)).all())


@router.patch("/communities/{community_id}")
def manual_classification(community_id: str, payload: ManualClassificationRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    community = db.get(Community, community_id)
    if community is None or community.workspace_id not in _workspace_ids(db, user):
        raise HTTPException(status_code=404, detail="Community not found")
    require_perm(db, user, community.workspace_id, "lead.edit")
    collections = engine.ensure_system_collections(db, community.workspace_id)
    community.manual_classification_override = True
    community.classification_source = "MANUAL"
    community.classification_status = "MANUAL_OVERRIDE"
    if payload.region is not None:
        community.region = payload.region
    if payload.category is not None:
        community.category = payload.category
    if payload.tags is not None:
        community.ai_tags = sorted(set(payload.tags))
    wanted = {slug for slug in payload.collection_slugs if slug in collections}
    system_ids = {collection.id for collection in collections.values()}
    for existing_membership in db.scalars(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)):
        if existing_membership.assignment_source == "AUTO" and existing_membership.collection_id in system_ids:
            db.delete(existing_membership)
    for slug in wanted:
        collection = collections[slug]
        membership: CommunityCollectionMembership | None = db.scalar(select(CommunityCollectionMembership).where(CommunityCollectionMembership.collection_id == collection.id, CommunityCollectionMembership.community_id == community.id))
        if membership is None:
            db.add(CommunityCollectionMembership(collection_id=collection.id, community_id=community.id, assignment_source="MANUAL", confidence=1.0, reason="Operator override", assigned_by=user.id))
        else:
            membership.assignment_source, membership.confidence, membership.assigned_by = "MANUAL", 1.0, user.id
    if not wanted:
        other = collections["other"]
        db.add(CommunityCollectionMembership(collection_id=other.id, community_id=community.id, assignment_source="MANUAL", confidence=1.0, reason="Operator override", assigned_by=user.id))
    db.commit()
    db.refresh(community)
    return community
