from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CriticResult:
    naturalness_score: float
    flags: tuple[str, ...]
    reasons: tuple[str, ...]
    rewrite_required: bool


BOT_PATTERNS = (
    "уважаемый пользователь", "рад предложить", "уникальная возможность", "не упустите",
    "свяжитесь со мной", "я помогу вам", "как ai", "как искусственный интеллект",
    "всем привет", "подводя итог", "будем рады предложить",
)
SALES_PATTERNS = ("купить", "закажите", "скидка", "выгодное предложение", "оставьте заявку", "продам")
FORMAL_PATTERNS = ("настоящим сообщением", "в рамках", "осуществляется", "предлагается рассмотреть")


def structure_key(content: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    blocks: list[str] = []
    for paragraph in paragraphs:
        if "?" in paragraph:
            blocks.append("question")
        elif any(word in paragraph.casefold() for word in ("могу", "есть вариант", "можно", "рядом")):
            blocks.append("value")
        else:
            blocks.append("context")
    return "-".join(blocks) or "empty"


def opening_of(content: str) -> str:
    return content.strip().split("\n", 1)[0][:500]


def ending_of(content: str) -> str:
    parts = [part.strip() for part in re.split(r"\n\s*\n|\n", content) if part.strip()]
    return (parts[-1] if parts else content.strip())[:500]


def critic_message(content: str, *, similarity_score: float = 0, style_flags: list[str] | None = None) -> CriticResult:
    normalized = " ".join(content.casefold().split())
    flags: list[str] = list(style_flags or [])
    reasons: list[str] = []
    score = 98.0
    if len(content.strip()) < 18:
        flags.append("TOO_THIN")
        reasons.append("Message has too little context.")
        score -= 8
    if len(content) > 700:
        flags.append("TOO_LONG")
        reasons.append("Message is longer than a natural first reply.")
        score -= 10
    if any(pattern in normalized for pattern in BOT_PATTERNS):
        flags.append("BOT_LIKE")
        reasons.append("Contains a recognizable bot or broadcast phrase.")
        score -= 18
    if any(pattern in normalized for pattern in SALES_PATTERNS):
        flags.append("TOO_SALESY")
        reasons.append("Contains direct sales language before context is established.")
        score -= 15
    if any(pattern in normalized for pattern in FORMAL_PATTERNS):
        flags.append("TOO_FORMAL")
        reasons.append("Uses official or bureaucratic wording.")
        score -= 10
    if content.count("!") > 2 or content.count("🙂") > 2:
        flags.append("TOO_EMOTIONAL")
        reasons.append("Emotional markers are overused.")
        score -= 7
    if re.search(r"\b(мы|наша команда|наш сервис)\b", normalized):
        flags.append("PROMOTIONAL")
        reasons.append("Brand voice appears before a human conversation exists.")
        score -= 8
    if similarity_score >= .82:
        flags.append("TOO_SIMILAR")
        reasons.append("Message is too close to a previous message.")
        score -= 14
    if len(re.findall(r"[.!?]", content)) == 0:
        flags.append("FLAT_RHYTHM")
        score -= 3
    unique_flags = tuple(dict.fromkeys(flags))
    return CriticResult(round(max(0, min(100, score)), 2), unique_flags, tuple(reasons), bool(unique_flags and score < 90))
