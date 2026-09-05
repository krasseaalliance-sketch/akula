from __future__ import annotations

import difflib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user, require_perm
from .db import get_db
from .human_writing.engine import HumanWritingEngine
from .human_writing.personas import PERSONAS
from .models import (
    Community,
    HumanWritingRun,
    HumanWritingVariant,
    StyleEvolutionEvent,
    StyleMemory,
    User,
)
from .services import accessible_workspace_ids, audit

router = APIRouter(prefix="/api/human-writing", tags=["human-writing"])
engine = HumanWritingEngine()


class StyleFeedbackRequest(BaseModel):
    variant_id: str
    edited_content: str = Field(min_length=1, max_length=10000)


def _run_response(db: Session, run: HumanWritingRun) -> dict[str, Any]:
    selected = db.get(HumanWritingVariant, run.selected_variant_id) if run.selected_variant_id else None
    return {"run": run, "selected": selected, "variant_count": 3, "operator_visible_variants": 1}


@router.get("/personas")
def personas(user: User = Depends(current_user)):
    return [{"id": persona.id, "name": persona.name, "speech_speed": persona.speech_speed, "message_length": persona.message_length, "emoji_level": persona.emoji_level, "friendliness": persona.friendliness, "formality": persona.formality, "rhythm": persona.rhythm} for persona in PERSONAS]


@router.get("/runs")
def runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_run_response(db, run) for run in db.scalars(select(HumanWritingRun).where(HumanWritingRun.workspace_id.in_(accessible_workspace_ids(db, user.id))).order_by(HumanWritingRun.created_at.desc())).all()]


@router.get("/runs/{run_id}")
def run_detail(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(HumanWritingRun, run_id)
    if run is None or run.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Human writing run not found")
    return _run_response(db, run)


@router.post("/communities/{community_id}/style/analyze")
def analyze_style(community_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    community = db.get(Community, community_id)
    if community is None or community.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Community not found")
    require_perm(db, user, community.workspace_id, "lead.edit")
    profile, snapshot = engine.style_profile(db, community=community)
    db.commit()
    return {"profile": profile, "snapshot": snapshot}


@router.post("/feedback")
def style_feedback(payload: StyleFeedbackRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    variant = db.get(HumanWritingVariant, payload.variant_id)
    if variant is None or variant.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Writing variant not found")
    require_perm(db, user, variant.workspace_id, "message.approve")
    changes = {"ratio": round(difflib.SequenceMatcher(None, variant.content, payload.edited_content).ratio(), 4), "original_length": len(variant.content), "edited_length": len(payload.edited_content)}
    event = StyleEvolutionEvent(workspace_id=variant.workspace_id, community_id=variant.community_id, variant_id=variant.id, created_by=user.id, original_content=variant.content, edited_content=payload.edited_content, changes=changes)
    db.add(event)
    memory = db.scalar(select(StyleMemory).where(StyleMemory.workspace_id == variant.workspace_id, StyleMemory.community_id == variant.community_id))
    if memory is None:
        memory = StyleMemory(workspace_id=variant.workspace_id, community_id=variant.community_id, used_openings=[], used_endings=[], used_structures=[], rejected_patterns=[], accepted_patterns=[])
        db.add(memory)
    memory.operator_preferences = {**(memory.operator_preferences or {}), "last_edit_ratio": changes["ratio"], "last_edit_length_delta": changes["edited_length"] - changes["original_length"]}
    memory.accepted_patterns = list(dict.fromkeys([*(memory.accepted_patterns or []), "operator_edit"]))[-100:]
    db.flush()
    audit(db, workspace_id=variant.workspace_id, actor_id=user.id, action="human_writing.style_evolved", entity_type="StyleEvolutionEvent", entity_id=event.id, after=changes)
    db.commit()
    return {"status": "RECORDED", "event_id": event.id, "changes": changes}
