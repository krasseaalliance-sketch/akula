from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import get_settings


@dataclass(frozen=True)
class ProviderOutput:
    data: dict[str, Any]
    provider: str
    model: str


class OpenAIResponsesProvider:
    """Small Responses API boundary; it is never constructed unless enabled."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_enabled or not settings.openai_api_key:
            raise RuntimeError("OPENAI_PROVIDER_DISABLED")
        self.settings = settings

    def _request_payload(self, *, model: str, input_data: Any, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": model,
            "input": input_data,
            "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
            "max_output_tokens": self.settings.ai_max_tokens,
        }
        # GPT-5.6 reasoning models reject the legacy temperature parameter.
        if not model.startswith("gpt-5"):
            payload["temperature"] = self.settings.ai_temperature
        return payload

    def classify(self, *, text: str, context: dict[str, Any]) -> ProviderOutput:
        schema = {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "pain": {"type": "string"},
                "need": {"type": "string"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
                "recommendation": {"type": "string"},
            },
            "required": ["intent", "pain", "need", "confidence", "reason", "recommendation"],
            "additionalProperties": False,
        }
        payload = self._request_payload(
            model=self.settings.openai_model,
            input_data=[
                {
                    "role": "system",
                    "content": "Classify lead intent, pain, need and safe first-contact recommendation. Return only JSON matching the schema. Never invent facts.",
                },
                {"role": "user", "content": json.dumps({"text": text, "context": context}, ensure_ascii=False)},
            ],
            schema_name="lead_intelligence",
            schema=schema,
        )
        response = httpx.post(
            f"{self.settings.openai_base_url.rstrip('/')}/responses",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if response.is_error:
            raise RuntimeError(f"OPENAI_HTTP_{response.status_code}: {response.text[:1000]}")
        body = response.json()
        output_text = body.get("output_text")
        if not output_text:
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        output_text = content.get("text")
                        break
                if output_text:
                    break
        if not output_text:
            raise RuntimeError("OPENAI_EMPTY_RESPONSE")
        return ProviderOutput(json.loads(output_text), "OPENAI_RESPONSES", self.settings.openai_model)

    def analyze_audience(self, *, answers: dict[str, Any]) -> ProviderOutput:
        schema = {
            "type": "object",
            "properties": {
                "audience_segments": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "intent_signals": {"type": "array", "items": {"type": "string"}},
                "exclusions": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
            },
            "required": ["audience_segments", "intent_signals", "exclusions", "summary"],
            "additionalProperties": False,
        }
        payload = self._request_payload(
            model=self.settings.openai_model,
            input_data=[
                {"role": "system", "content": "Infer the genuinely relevant audience for a campaign. Return concise segments, intent signals and exclusions. Do not suggest spam, unsolicited DMs or policy bypasses. Return only JSON."},
                {"role": "user", "content": json.dumps(answers, ensure_ascii=False)},
            ],
            schema_name="campaign_audience",
            schema=schema,
        )
        response = httpx.post(f"{self.settings.openai_base_url.rstrip('/')}/responses", headers={"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}, json=payload, timeout=45)
        if response.is_error:
            raise RuntimeError(f"OPENAI_HTTP_{response.status_code}: {response.text[:1000]}")
        body = response.json()
        output_text = body.get("output_text")
        if not output_text:
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        output_text = content.get("text")
                        break
                if output_text:
                    break
        if not output_text:
            raise RuntimeError("OPENAI_EMPTY_RESPONSE")
        return ProviderOutput(json.loads(output_text), "OPENAI_RESPONSES", self.settings.openai_model)


class OpenAIHumanWritingProvider:
    """Structured simulator, writer and critic calls for Stage 3.1."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_enabled or not settings.openai_api_key:
            raise RuntimeError("OPENAI_PROVIDER_DISABLED")
        self.settings = settings

    def _call(self, *, name: str, system: str, payload: dict[str, Any], schema: dict[str, Any]) -> ProviderOutput:
        response = httpx.post(
            f"{self.settings.openai_base_url.rstrip('/')}/responses",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"},
            json={
                "model": self.settings.openai_model,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
                "temperature": self.settings.ai_temperature,
                "max_output_tokens": self.settings.ai_max_tokens,
            },
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        output_text = body.get("output_text")
        if not output_text:
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        output_text = content.get("text")
                        break
                if output_text:
                    break
        if not output_text:
            raise RuntimeError("OPENAI_EMPTY_RESPONSE")
        return ProviderOutput(json.loads(output_text), "OPENAI_RESPONSES", self.settings.openai_model)

    def simulate(self, *, community: dict[str, Any], persona: dict[str, Any], facts: dict[str, Any]) -> ProviderOutput:
        return self._call(
            name="community_simulator",
            system=("Act as a normal participant of the specific online community. "
                    "Describe how people there write, what they avoid and which structure would feel native. "
                    "Do not suggest spam, evasion, unsolicited direct messages or policy bypasses. Return JSON only."),
            payload={"community": community, "persona": persona, "facts": facts},
            schema={"type": "object", "properties": {"style": {"type": "string"}, "do": {"type": "array", "items": {"type": "string"}}, "dont": {"type": "array", "items": {"type": "string"}}, "structure": {"type": "array", "items": {"type": "string"}}}, "required": ["style", "do", "dont", "structure"], "additionalProperties": False},
        )

    def generate_variants(self, *, simulation: dict[str, Any], community: dict[str, Any], persona: dict[str, Any], facts: dict[str, Any]) -> ProviderOutput:
        return self._call(
            name="human_writing_variants",
            system=("Write three genuinely different, short community-native message variants. "
                    "Use only verified facts supplied by the user. Sound like a participant, not a brand or bot. "
                    "No mass greeting, no hard sell, no unsolicited DM language, no invented claims. Return JSON only."),
            payload={"simulation": simulation, "community": community, "persona": persona, "facts": facts},
            schema={"type": "object", "properties": {"variants": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {"content": {"type": "string"}, "structure": {"type": "array", "items": {"type": "string"}}, "opening": {"type": "string"}, "ending": {"type": "string"}}, "required": ["content", "structure", "opening", "ending"], "additionalProperties": False}}}, "required": ["variants"], "additionalProperties": False},
        )

    def critic(self, *, variants: list[dict[str, Any]], community: dict[str, Any], simulation: dict[str, Any]) -> ProviderOutput:
        return self._call(
            name="human_writing_critic",
            system=("Critique each message as a strict editor for natural community conversation. "
                    "Flag broadcast, advertising, bot-like, too-perfect, too-formal, too-long, emotional, salesy or templated writing. "
                    "A message is acceptable only at naturalness 90 or above. Return JSON only."),
            payload={"variants": variants, "community": community, "simulation": simulation},
            schema={"type": "object", "properties": {"critiques": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {"naturalness_score": {"type": "number"}, "flags": {"type": "array", "items": {"type": "string"}}, "reasons": {"type": "array", "items": {"type": "string"}}}, "required": ["naturalness_score", "flags", "reasons"], "additionalProperties": False}}}, "required": ["critiques"], "additionalProperties": False},
        )

    def embedding(self, text: str) -> list[float]:
        response = httpx.post(
            f"{self.settings.openai_base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"},
            json={"model": self.settings.openai_embedding_model, "input": text},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        if not data or not data[0].get("embedding"):
            raise RuntimeError("OPENAI_EMPTY_EMBEDDING")
        return [float(value) for value in data[0]["embedding"]]
