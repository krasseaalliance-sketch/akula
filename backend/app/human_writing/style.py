from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .personas import WritingPersona

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
GREETING_TERMS = ("привет", "добрый", "здравствуйте", "hello", "hi", "доброе утро")
SLANG_TERMS = ("вайб", "топ", "класс", "ребят", "имхо", "лол", "жиза", "ну такое", "апдейт")


@dataclass(frozen=True)
class CommunityStyleSnapshot:
    sample_size: int
    average_message_length: float
    average_paragraphs: float
    emoji_rate: float
    greeting_rate: float
    question_rate: float
    abbreviation_rate: float
    english_rate: float
    slang_rate: float
    directness_score: float
    emotion_score: float
    dominant_language: str
    style_summary: dict[str, object]


def _rate(hits: int, total: int) -> float:
    return round(hits / max(1, total), 4)


def analyze_messages(messages: list[str]) -> CommunityStyleSnapshot:
    clean = [message.strip() for message in messages if message and message.strip()]
    total = len(clean)
    if not clean:
        return CommunityStyleSnapshot(0, 0, 1, 0, 0, 0, 0, 0, 0, .5, .5, "ru", {"mode": "unknown", "tone": "neutral"})
    lengths = [len(message) for message in clean]
    paragraphs = [max(1, len(re.split(r"\n\s*\n", message))) for message in clean]
    emoji_rate = _rate(sum(bool(EMOJI_RE.search(message)) for message in clean), total)
    greeting_rate = _rate(sum(any(term in message.casefold() for term in GREETING_TERMS) for message in clean), total)
    question_rate = _rate(sum("?" in message for message in clean), total)
    abbreviation_rate = _rate(sum(bool(re.search(r"\b[а-яa-z]{1,4}\.", message.casefold())) or "т.е." in message.casefold() for message in clean), total)
    english_rate = _rate(sum(bool(LATIN_RE.search(message)) for message in clean), total)
    slang_rate = _rate(sum(any(term in message.casefold() for term in SLANG_TERMS) for message in clean), total)
    directness = sum(1 - min(1, len(message.split()) / 80) for message in clean) / total
    emotion = sum(min(1, (message.count("!") + len(EMOJI_RE.findall(message))) / 4) for message in clean) / total
    cyrillic = sum(len(CYRILLIC_RE.findall(message)) for message in clean)
    latin = sum(len(LATIN_RE.findall(message)) for message in clean)
    language = "ru" if cyrillic >= latin else "en"
    return CommunityStyleSnapshot(
        sample_size=total,
        average_message_length=round(sum(lengths) / total, 2),
        average_paragraphs=round(sum(paragraphs) / total, 2),
        emoji_rate=emoji_rate,
        greeting_rate=greeting_rate,
        question_rate=question_rate,
        abbreviation_rate=abbreviation_rate,
        english_rate=english_rate,
        slang_rate=slang_rate,
        directness_score=round(directness, 4),
        emotion_score=round(emotion, 4),
        dominant_language=language,
        style_summary={
            "mode": "chatty" if sum(lengths) / total < 220 else "detailed",
            "tone": "emotional" if emotion > .35 else "calm",
            "pace": "quick" if directness > .7 else "deliberate",
            "paragraphs": "single" if sum(paragraphs) / total < 1.5 else "multi",
        },
    )


def persona_fit(snapshot: CommunityStyleSnapshot, persona: WritingPersona) -> float:
    length_score = {
        "short": 1 - min(1, snapshot.average_message_length / 180),
        "medium": 1 - abs(snapshot.average_message_length - 220) / 400,
        "long": min(1, snapshot.average_message_length / 360),
    }.get(persona.message_length, .5)
    speed_score = 1 if (snapshot.directness_score > .65) == (persona.speech_speed == "fast") else .55
    emoji_score = 1 - abs(snapshot.emoji_rate - persona.emoji_level)
    formality_score = 1 - abs((1 - snapshot.slang_rate) - persona.formality)
    humor_score = 1 - abs(snapshot.emotion_score - persona.humor)
    return round(max(0, length_score * .3 + speed_score * .2 + emoji_score * .2 + formality_score * .2 + humor_score * .1), 4)


def snapshot_dict(snapshot: CommunityStyleSnapshot) -> dict[str, object]:
    return asdict(snapshot)
