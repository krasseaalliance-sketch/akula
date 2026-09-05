from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..lead_intelligence.engine import token_cosine
from ..lead_intelligence.provider import OpenAIHumanWritingProvider
from ..models import (
    Campaign,
    Community,
    CommunityStyleProfile,
    HumanWritingRun,
    HumanWritingVariant,
    Lead,
    Offer,
    StyleMemory,
    TelegramMessageRecord,
)
from ..services import audit
from .critic import critic_message, ending_of, opening_of, structure_key
from .personas import ENDINGS, OPENINGS, PERSONAS, STRUCTURE_LIBRARY, WritingPersona
from .style import CommunityStyleSnapshot, analyze_messages, persona_fit, snapshot_dict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HumanWritingResult:
    run: HumanWritingRun
    selected: HumanWritingVariant
    variants: tuple[HumanWritingVariant, ...]
    style: CommunityStyleSnapshot
    persona: WritingPersona


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return round(dot / denominator, 4) if denominator else 0.0


class HumanWritingEngine:
    """Persona + community style + simulator + critic pipeline.

    The engine is deliberately draft-only. It creates operator-reviewable message
    variants and never calls a platform send method.
    """

    def style_profile(self, db: Session, *, community: Community) -> tuple[CommunityStyleProfile, CommunityStyleSnapshot]:
        messages = list(db.scalars(select(TelegramMessageRecord.text).where(
            TelegramMessageRecord.community_id == community.id,
            TelegramMessageRecord.text.is_not(None),
        ).order_by(TelegramMessageRecord.sent_at.desc()).limit(200)).all())
        snapshot = analyze_messages([message for message in messages if message])
        profile = db.scalar(select(CommunityStyleProfile).where(CommunityStyleProfile.community_id == community.id))
        values = snapshot_dict(snapshot)
        if profile is None:
            profile = CommunityStyleProfile(workspace_id=community.workspace_id, community_id=community.id)
            db.add(profile)
        for key in (
            "sample_size", "average_message_length", "average_paragraphs", "emoji_rate", "greeting_rate",
            "question_rate", "abbreviation_rate", "english_rate", "slang_rate", "directness_score",
            "emotion_score", "dominant_language", "style_summary",
        ):
            setattr(profile, key, values[key])
        profile.source_message_count = snapshot.sample_size
        profile.analyzed_at = datetime.utcnow()
        db.flush()
        return profile, snapshot

    def choose_persona(self, snapshot: CommunityStyleSnapshot, *, community_id: str, source_text: str) -> WritingPersona:
        ranked = sorted(PERSONAS, key=lambda persona: (-persona_fit(snapshot, persona), persona.id))
        seed = int(hashlib.sha256(f"{community_id}:{source_text}".encode()).hexdigest()[:8], 16)
        top = ranked[: min(8, len(ranked))]
        return top[seed % len(top)]

    def _memory(self, db: Session, *, workspace_id: str, community_id: str | None) -> StyleMemory:
        memory = db.scalar(select(StyleMemory).where(StyleMemory.workspace_id == workspace_id, StyleMemory.community_id == community_id))
        if memory is None:
            memory = StyleMemory(workspace_id=workspace_id, community_id=community_id, used_openings=[], used_endings=[], used_structures=[], rejected_patterns=[], accepted_patterns=[])
            db.add(memory)
            db.flush()
        return memory

    @staticmethod
    def _next(values: tuple[str, ...], used: list[str], offset: int) -> str:
        for index in range(len(values)):
            candidate = values[(offset + index) % len(values)]
            if candidate not in used:
                return candidate
        return values[offset % len(values)]

    def _local_simulation(self, snapshot: CommunityStyleSnapshot, persona: WritingPersona) -> dict[str, Any]:
        return {
            "style": f"{snapshot.dominant_language}; {snapshot.style_summary.get('tone')}; {snapshot.style_summary.get('pace')}; {snapshot.style_summary.get('paragraphs')}",
            "do": ["start from context", "use one clear thought", "leave room for a reply"],
            "dont": ["broadcast greetings", "hard sell", "over-explain"],
            "structure": ["opening", "context", "useful_detail", "question"],
            "persona": persona.name,
        }

    def _local_variant(self, *, opening: str, ending: str, structure: tuple[str, ...], facts: dict[str, Any], persona: WritingPersona, index: int) -> dict[str, Any]:
        topic = facts.get("lead_text") or facts.get("objective") or facts.get("campaign") or "этой темы"
        topic = " ".join(str(topic).split())[:180].rstrip(".")
        offer = facts.get("offer")
        offer_facts = facts.get("offer_facts") if isinstance(facts.get("offer_facts"), dict) else {}
        if offer_facts:
            route = ", ".join(str(item) for item in offer_facts.get("program", []))
            detail = (
                f"Ищем попутчиков на двухдневную поездку по северу Бали "
                f"{offer_facts.get('dates', '29–30 июля')}. В программе: {route}. "
                f"Есть {offer_facts.get('available_seats', 4)} свободных места в машине."
            )
            content = f"{opening}.\n\n{detail}\n\n{ending}"
        else:
            detail = f" По делу: {offer}." if offer and index == 1 else " Можно начать с небольшого шага." if index == 2 else ""
            content = f"{opening}.\n\nСмотрю на тему так: {topic}{detail}\n\n{ending}"
        if persona.message_length == "short":
            content = f"{opening}. {detail or topic}\n\n{ending}"
        return {"content": content, "opening": opening, "ending": ending, "structure": list(structure)}

    def _similarity(self, db: Session, *, workspace_id: str, community_id: str | None, content: str, use_embeddings: bool, provider: OpenAIHumanWritingProvider | None) -> tuple[float, str]:
        previous = list(db.scalars(select(HumanWritingVariant.content).where(
            HumanWritingVariant.workspace_id == workspace_id,
            HumanWritingVariant.community_id == community_id,
        ).order_by(HumanWritingVariant.created_at.desc()).limit(40)).all())
        if not previous:
            return 0.0, "TOKEN_COSINE"
        if use_embeddings and provider is not None:
            try:
                current_embedding = provider.embedding(content)
                previous_embedding = provider.embedding(previous[0])
                return _cosine(current_embedding, previous_embedding), "EMBEDDING"
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
                logger.warning("Human writing embeddings fell back to token cosine")
        return max(token_cosine(content, other) for other in previous), "TOKEN_COSINE"

    def generate(self, db: Session, *, workspace_id: str, campaign: Campaign, community: Community | None, lead: Lead | None, actor_id: str, use_llm: bool | None = None) -> HumanWritingResult:
        settings = get_settings()
        use_llm = settings.human_writing_llm_enabled if use_llm is None else use_llm
        style_profile = None
        style = analyze_messages([])
        if community is not None:
            style_profile, style = self.style_profile(db, community=community)
        source_text = lead.raw_text if lead else campaign.objective
        persona = self.choose_persona(style, community_id=community.id if community else "workspace", source_text=source_text)
        memory = self._memory(db, workspace_id=workspace_id, community_id=community.id if community else None)
        facts = {
            "campaign": campaign.name,
            "objective": campaign.objective,
            "offer": None,
            "lead_text": lead.raw_text if lead else None,
            "verified": True,
        }
        if campaign.offer_id:
            offer = db.get(Offer, campaign.offer_id)
            facts["offer"] = offer.name if offer else None
            facts["offer_facts"] = offer.facts if offer else None
        community_data = {
            "title": community.title if community else None,
            "description": community.description if community else None,
            "region": community.region if community else None,
            "category": community.category if community else None,
            "tags": community.ai_tags if community else [],
            "style": snapshot_dict(style),
        }
        provider: OpenAIHumanWritingProvider | None = None
        simulation = self._local_simulation(style, persona)
        generated: list[dict[str, Any]] = []
        provider_name, model = "RULES", "human-writing-rules-v1"
        if use_llm and settings.openai_enabled and settings.openai_api_key:
            try:
                provider = OpenAIHumanWritingProvider()
                simulation_output = provider.simulate(community=community_data, persona=persona.__dict__, facts=facts)
                simulation = simulation_output.data
                generated = list(provider.generate_variants(simulation=simulation, community=community_data, persona=persona.__dict__, facts=facts).data.get("variants", []))
                provider_name, model = simulation_output.provider, simulation_output.model
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
                logger.warning("Human writing LLM pipeline fell back to deterministic writer")
                provider = None
        if len(generated) != 3:
            generated = []
            for index in range(3):
                opening = self._next(OPENINGS, memory.used_openings or [], index * 97)
                ending = self._next(ENDINGS, memory.used_endings or [], index * 113)
                structure = STRUCTURE_LIBRARY[index * 17]
                generated.append(self._local_variant(opening=opening, ending=ending, structure=structure, facts=facts, persona=persona, index=index))

        llm_critiques: list[dict[str, Any]] = []
        if provider is not None:
            try:
                llm_critiques = list(provider.critic(variants=generated, community=community_data, simulation=simulation).data.get("critiques", []))
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
                logger.warning("Human writing LLM critic fell back to deterministic critic")
        run = HumanWritingRun(
            workspace_id=workspace_id,
            campaign_id=campaign.id,
            community_id=community.id if community else None,
            lead_id=lead.id if lead else None,
            created_by=actor_id,
            persona_id=persona.id,
            style_profile_id=style_profile.id if style_profile else None,
            provider=provider_name,
            model=model,
            simulator_context=simulation,
            status="SUCCEEDED",
        )
        db.add(run)
        db.flush()
        variants: list[HumanWritingVariant] = []
        for index, candidate in enumerate(generated[:3]):
            content = str(candidate.get("content", "")).strip()
            similarity, similarity_method = self._similarity(db, workspace_id=workspace_id, community_id=community.id if community else None, content=content, use_embeddings=provider is not None, provider=provider)
            deterministic = critic_message(content, similarity_score=similarity)
            llm = llm_critiques[index] if index < len(llm_critiques) else {}
            llm_score = float(llm.get("naturalness_score", deterministic.naturalness_score)) if llm else deterministic.naturalness_score
            score = min(deterministic.naturalness_score, llm_score)
            flags = tuple(dict.fromkeys([*deterministic.flags, *(str(item) for item in llm.get("flags", []))]))
            reasons = tuple(dict.fromkeys([*deterministic.reasons, *(str(item) for item in llm.get("reasons", []))]))
            if score < settings.human_writing_min_naturalness or similarity >= settings.human_writing_similarity_threshold:
                fallback_opening = self._next(OPENINGS, memory.used_openings or [], 401 + index * 31)
                fallback_ending = self._next(ENDINGS, memory.used_endings or [], 503 + index * 37)
                candidate = self._local_variant(opening=fallback_opening, ending=fallback_ending, structure=STRUCTURE_LIBRARY[300 + index], facts=facts, persona=persona, index=index)
                content = candidate["content"]
                similarity, similarity_method = self._similarity(db, workspace_id=workspace_id, community_id=community.id if community else None, content=content, use_embeddings=False, provider=None)
                repaired = critic_message(content, similarity_score=similarity)
                score, flags, reasons = repaired.naturalness_score, repaired.flags, repaired.reasons
            variant = HumanWritingVariant(
                run_id=run.id,
                workspace_id=workspace_id,
                community_id=community.id if community else None,
                variant_index=index,
                content=content,
                opening=str(candidate.get("opening") or opening_of(content)),
                ending=str(candidate.get("ending") or ending_of(content)),
                structure=list(candidate.get("structure") or simulation.get("structure") or ["context", "question"]),
                structure_key=structure_key(content),
                naturalness_score=score,
                similarity_score=similarity,
                similarity_method=similarity_method,
                critic_flags=list(flags),
                critic_reasons=list(reasons),
                status="DRAFT",
                provider=provider_name,
                model=model,
            )
            db.add(variant)
            variants.append(variant)
        db.flush()
        selected = max(variants, key=lambda item: (item.naturalness_score - item.similarity_score * 20, -item.variant_index))
        selected.status = "SELECTED"
        run.selected_variant_id = selected.id
        run.naturalness_score = selected.naturalness_score
        run.structure_memory_key = selected.structure_key
        run.critic_summary = {"selected": selected.id, "variant_scores": [item.naturalness_score for item in variants], "rejected_flags": selected.critic_flags or []}
        memory.used_openings = [*(memory.used_openings or []), selected.opening][-1000:]
        memory.used_endings = [*(memory.used_endings or []), selected.ending][-1000:]
        memory.used_structures = [*(memory.used_structures or []), selected.structure_key][-1000:]
        memory.accepted_patterns = list(dict.fromkeys([*(memory.accepted_patterns or []), selected.structure_key]))[-100:]
        memory.version += 1
        audit(db, workspace_id=workspace_id, actor_id=actor_id, action="human_writing.generated", entity_type="HumanWritingRun", entity_id=run.id, after={"provider": provider_name, "persona": persona.id, "naturalness": selected.naturalness_score, "variants": 3})
        db.flush()
        return HumanWritingResult(run=run, selected=selected, variants=tuple(variants), style=style, persona=persona)
